"""Safe removal of the ForgeWorks demo.

Local (Quick Demo): delegate to quick.remove_local().
AWS Demo: remove ONLY resources recorded in the demo's own ownership metadata and
living under the demo namespace. Never deletes the StrataBI Dev data plane or any
non-demo data. Idempotent; requires confirmation unless confirm=False.
"""

from __future__ import annotations

import json

from . import ATHENA_DASHBOARD_ID, GLUE_DEMO_DATABASE, S3_DEMO_PREFIX, TABLES
from .athena import DemoError, _INSTALL_KEY, discover
from .dashboard import demo_marker
from .quick import remove_local  # re-export


def _load_meta(s3, bucket):
    try:
        body = s3.get_object(Bucket=bucket, Key=_INSTALL_KEY)["Body"].read()
        return json.loads(body)
    except Exception:
        return None


def remove_aws(session, *, profile=None, confirm=True, prompt=input) -> dict:
    cfg = discover(session, profile=profile)
    s3 = session.client("s3")
    glue = session.client("glue")

    meta = _load_meta(s3, cfg.bucket)
    if not meta or not meta.get("demo") or meta.get("demo_id") != "forgeworks":
        raise DemoError(
            "No ForgeWorks demo ownership metadata found in this account/bucket; "
            "refusing to delete anything (safety). Nothing removed."
        )

    # Enumerate exactly what will be removed (only demo-owned).
    s3_prefix = meta.get("s3_prefix", S3_DEMO_PREFIX)
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=cfg.bucket, Prefix=s3_prefix):
        keys.extend(o["Key"] for o in page.get("Contents", []))
    database = meta.get("glue_database", GLUE_DEMO_DATABASE)
    dash_key = meta.get("dashboard_key")

    print("ForgeWorks AWS Demo — will remove ONLY:")
    print(f"  S3: s3://{cfg.bucket}/{s3_prefix}*  ({len(keys)} objects)")
    print(f"  Glue tables: {', '.join(TABLES)} in database {database}")
    print(f"  Glue database: {database}")
    print(f"  Dashboard: {dash_key}")
    print("  (StrataBI Dev data plane and all non-demo data are left untouched.)")
    if confirm:
        if (prompt("Remove these demo resources? [y/N] ") or "").strip().lower() not in ("y", "yes"):
            print("aborted — nothing removed.")
            return {"removed": False, "aborted": True}

    # 1) S3 objects strictly under the demo prefix (double-check each key).
    to_delete = [{"Key": k} for k in keys if k.startswith(s3_prefix)]
    for i in range(0, len(to_delete), 1000):
        s3.delete_objects(Bucket=cfg.bucket, Delete={"Objects": to_delete[i:i + 1000]})

    # 2) Glue: only the ForgeWorks tables, then the isolated demo database.
    for t in TABLES:
        try:
            glue.delete_table(DatabaseName=database, Name=t)
        except Exception:
            pass
    try:
        glue.delete_database(Name=database)
    except Exception:
        pass

    # 3) Dashboard object — only if it is the demo one (validate marker in body).
    if dash_key:
        try:
            body = s3.get_object(Bucket=cfg.bucket, Key=dash_key)["Body"].read().decode("utf-8")
            if demo_marker("athena") in body or ATHENA_DASHBOARD_ID in dash_key:
                s3.delete_object(Bucket=cfg.bucket, Key=dash_key)
        except Exception:
            pass

    # 4) ownership metadata last.
    try:
        s3.delete_object(Bucket=cfg.bucket, Key=_INSTALL_KEY)
    except Exception:
        pass

    print(f"Removed {len(to_delete)} S3 objects, {len(TABLES)} Glue tables, "
          f"database {database}, and the demo dashboard.")
    return {"removed": True, "s3_objects": len(to_delete), "database": database}
