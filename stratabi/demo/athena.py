"""AWS Demo adapter — upload ForgeWorks to the customer's StrataBI Dev data plane
and query it through Athena.

Everything created is isolated under a demo namespace:
  * S3:   s3://<STRATABI_SYSTEM_BUCKET>/demo/forgeworks/v1/<table>/<table>.csv
  * Glue: database `stratabi_dev_demo`, explicit external tables (no crawler)
  * Athena: bounded verification queries

Real boto3 is used, but nothing runs on import and installation requires explicit
confirmation (or --yes). Clients are injectable so the flow is unit-testable with
mocks. No StrataHQ contact anywhere.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from dataclasses import dataclass, field

from . import (ATHENA_DASHBOARD_ID, DEMO_ID, DEMO_VERSION, GLUE_DEMO_DATABASE,
               S3_DEMO_PREFIX, TABLES, cache_dir, data_dir)
from . import dashboard as DASH
from . import generate as GEN
from . import schemas as SCH

_INSTALL_KEY = f"{S3_DEMO_PREFIX}_demo_install.json"   # ownership metadata in S3


class DemoError(RuntimeError):
    pass


class DemoNotReadyError(DemoError):
    """Raised when the StrataBI Dev data plane isn't discoverable."""


@dataclass
class DemoConfig:
    region: str
    account_id: str
    bucket: str
    athena_output: str
    dashboard_prefix: str
    demo_database: str = GLUE_DEMO_DATABASE
    profile: str | None = None
    resources: dict = field(default_factory=dict)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def discover(session, profile: str | None = None) -> DemoConfig:
    """Resolve config from the standard AWS chain + the StrataBI Dev install output.
    Fails with a precise, actionable error if the data plane isn't found."""
    region = session.region_name or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    bucket = os.getenv("STRATABI_SYSTEM_BUCKET") or os.getenv("STRATABI_BUCKET") or ""
    athena_output = os.getenv("STRATABI_ATHENA_OUTPUT") or ""
    dashboard_prefix = os.getenv("STRATABI_DASHBOARD_PREFIX") or "analyst/dashboards"

    if not (bucket and athena_output and region):
        prof = profile or os.getenv("AWS_PROFILE") or "default"
        raise DemoNotReadyError(
            f'The StrataBI Dev AWS data plane was not found for profile "{prof}".\n'
            "Run:\n\n"
            f"    stratacli dev install --profile {prof} --region {region or '<region>'}\n\n"
            "before installing the AWS demo. (Missing: "
            + ", ".join(k for k, v in {
                "STRATABI_SYSTEM_BUCKET": bucket,
                "STRATABI_ATHENA_OUTPUT": athena_output,
                "region": region}.items() if not v) + ")"
        )

    try:
        account_id = session.client("sts").get_caller_identity()["Account"]
    except Exception as exc:  # noqa: BLE001
        raise DemoError(f"could not validate AWS credentials: {exc}") from exc

    return DemoConfig(region=region, account_id=account_id, bucket=bucket,
                      athena_output=athena_output.rstrip("/") + "/",
                      dashboard_prefix=dashboard_prefix.strip("/"),
                      profile=profile)


def _s3_key(table: str) -> str:
    # one prefix per table so each is its own external-table LOCATION
    return f"{S3_DEMO_PREFIX}{table}/{table}.csv"


def _table_location(bucket: str, table: str) -> str:
    return f"s3://{bucket}/{S3_DEMO_PREFIX}{table}/"


def _run_athena(athena, sql: str, output: str, timeout: int = 120) -> str:
    qid = athena.start_query_execution(
        QueryString=sql,
        ResultConfiguration={"OutputLocation": output},
    )["QueryExecutionId"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
        if st in ("SUCCEEDED",):
            return qid
        if st in ("FAILED", "CANCELLED"):
            raise DemoError(f"Athena query {st}: {sql[:80]}")
        time.sleep(1.5)
    raise DemoError("Athena query timed out")


def plan(cfg: DemoConfig) -> dict:
    """What the install will create (for the confirmation prompt)."""
    return {
        "account": cfg.account_id, "region": cfg.region, "bucket": cfg.bucket,
        "s3_prefix": S3_DEMO_PREFIX, "glue_database": cfg.demo_database,
        "tables": list(TABLES), "dashboard_id": ATHENA_DASHBOARD_ID,
    }


COST_NOTICE = (
    "This demonstration will upload synthetic CSV files and create AWS Glue Catalog\n"
    "tables in your AWS account. Athena queries and AWS storage may incur small\n"
    "charges. No data is transmitted to Shaleio."
)


def install(session, *, profile=None, confirm=True, prompt=input) -> dict:
    """Generate → upload → register → verify → install dashboard → record.
    `confirm=False` skips the interactive prompt (the CLI passes --yes)."""
    cfg = discover(session, profile=profile)
    s3 = session.client("s3")
    glue = session.client("glue")
    athena = session.client("athena")

    p = plan(cfg)
    print("ForgeWorks AWS Demo — plan:")
    for k, v in p.items():
        print(f"  {k}: {v}")
    print("\n" + COST_NOTICE + "\n")
    if confirm:
        if (prompt("Proceed? [y/N] ") or "").strip().lower() not in ("y", "yes"):
            print("aborted — nothing created.")
            return {"installed": False, "aborted": True}

    # 1) deterministic CSVs
    tables = GEN.generate()
    GEN.export_csvs(tables, data_dir())

    # 2) upload under the isolated demo prefix
    uploaded = []
    for t in TABLES:
        key = _s3_key(t)
        s3.put_object(Bucket=cfg.bucket, Key=key,
                      Body=(data_dir() / f"{t}.csv").read_bytes(),
                      ContentType="text/csv")
        uploaded.append(key)

    # 3) isolated Glue database
    try:
        glue.create_database(DatabaseInput={"Name": cfg.demo_database,
                                            "Description": "ForgeWorks synthetic demo (StrataBI)."})
    except glue.exceptions.AlreadyExistsException:
        pass

    # 4) explicit external tables via Athena DDL (idempotent; no crawler)
    for t in TABLES:
        ddl = SCH.athena_ddl(t, cfg.demo_database, _table_location(cfg.bucket, t))
        _run_athena(athena, ddl, cfg.athena_output)

    # 5) bounded verification query per table
    verified = {}
    for t in TABLES:
        _run_athena(athena, f"SELECT COUNT(*) FROM \"{cfg.demo_database}\".\"{t}\" LIMIT 1",
                    cfg.athena_output)
        verified[t] = True

    # 6) install the Athena dashboard into the app's dashboard prefix
    dash = DASH.build_athena_dashboard(cfg.demo_database)
    dash_key = f"{cfg.dashboard_prefix}/{ATHENA_DASHBOARD_ID}.json"
    s3.put_object(Bucket=cfg.bucket, Key=dash_key,
                  Body=json.dumps(dash, indent=2).encode("utf-8"),
                  ContentType="application/json")

    # 7) ownership metadata (used by status + safe removal)
    meta = {
        "demo": True, "demo_id": DEMO_ID, "demo_version": DEMO_VERSION,
        "data_source": "athena", "account": cfg.account_id, "region": cfg.region,
        "bucket": cfg.bucket, "s3_prefix": S3_DEMO_PREFIX,
        "glue_database": cfg.demo_database, "tables": list(TABLES),
        "dashboard_id": ATHENA_DASHBOARD_ID, "dashboard_key": dash_key,
        "uploaded_keys": uploaded, "installed_at": _now(),
    }
    s3.put_object(Bucket=cfg.bucket, Key=_INSTALL_KEY,
                  Body=json.dumps(meta, indent=2).encode("utf-8"),
                  ContentType="application/json")
    (cache_dir()).mkdir(parents=True, exist_ok=True)
    (cache_dir() / "aws_install.json").write_text(json.dumps(meta, indent=2))

    print(f"\nInstalled. {len(uploaded)} tables uploaded, {len(verified)} verified.")
    print("Next: open the app and select 'ForgeWorks AWS Demo':\n    stratabi-dev")
    return {"installed": True, **meta}


class AthenaForgeWorksDataSource:
    """Athena adapter — runs the canonical SQL and returns rows (parity/programmatic)."""
    def __init__(self, session, cfg: DemoConfig):
        self._athena = session.client("athena")
        self._cfg = cfg

    def _query(self, sql):
        qid = _run_athena(self._athena, sql, self._cfg.athena_output)
        res = self._athena.get_query_results(QueryExecutionId=qid)
        rows = res["ResultSet"]["Rows"]
        if not rows:
            return []
        header = [c["VarCharValue"] for c in rows[0]["Data"]]
        return [dict(zip(header, [c.get("VarCharValue") for c in r["Data"]]))
                for r in rows[1:]]
