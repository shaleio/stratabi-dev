"""AWS-native dashboard funnel for the Developer Edition.

Validate dashboard JSON against the packaged schema, then push/list/remove it in
the system bucket under the dashboard prefix (`analyst/dashboards/`), which is where
the app loads dashboards from in `STRATABI_MODE=aws`. There is deliberately no local
dashboard mode — everything lives in your own data plane.

Used by `stratabi dashboards {push,ls,rm}` (see cli.py).
"""

from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path

import boto3


class DashboardError(RuntimeError):
    pass


def _bucket() -> str:
    b = os.getenv("STRATABI_SYSTEM_BUCKET") or os.getenv("STRATABI_BUCKET")
    if not b:
        raise DashboardError(
            "STRATABI_SYSTEM_BUCKET is not set. Make sure your .env is present "
            "(`stratactl dev configure-local`) — run `stratabi --check` to confirm.")
    return b


def _prefix() -> str:
    return (os.getenv("STRATABI_DASHBOARD_PREFIX") or "analyst/dashboards").strip("/")


def _schema() -> dict:
    return json.loads(
        files("stratabi.data.schemas").joinpath("dashboard.schema.json").read_text())


def _validate(doc: dict, label: str) -> None:
    """Validate against the packaged schema. jsonschema is a declared dependency;
    if it is somehow unavailable we warn rather than block the upload."""
    try:
        import jsonschema
    except Exception:
        print(f"  ! jsonschema unavailable — pushing {label} WITHOUT validation")
        return
    try:
        jsonschema.validate(doc, _schema())
    except jsonschema.ValidationError as e:  # type: ignore[attr-defined]
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        raise DashboardError(f"{label}: schema invalid at {loc}: {e.message}") from None


def _iter_json(paths):
    for p in paths:
        pth = Path(p)
        if pth.is_dir():
            found = sorted(pth.glob("*.json"))
            if not found:
                raise DashboardError(f"no .json files in directory: {p}")
            yield from found
        elif pth.is_file():
            yield pth
        else:
            raise DashboardError(f"no such file or directory: {p}")


def push(paths, *, name: str | None = None) -> int:
    """Validate + upload one or more dashboards. `name` overrides the key (single file)."""
    bucket, prefix = _bucket(), _prefix()
    files_ = list(_iter_json(paths))
    if name and len(files_) != 1:
        raise DashboardError("--name can only be used when pushing a single file.")
    s3 = boto3.client("s3")
    for f in files_:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise DashboardError(f"{f.name}: not valid JSON ({e})") from None
        _validate(doc, f.name)
        key = f"{prefix}/{name or f.stem}.json"
        s3.put_object(Bucket=bucket, Key=key,
                      Body=json.dumps(doc, indent=2).encode("utf-8"),
                      ContentType="application/json")
        print(f"  pushed {f.name}  →  s3://{bucket}/{key}")
    print(f"{len(files_)} dashboard(s) pushed to s3://{bucket}/{prefix}/")
    return 0


def ls() -> int:
    """List dashboard keys under the prefix (name relative to the prefix, no .json)."""
    bucket, prefix = _bucket(), _prefix()
    s3 = boto3.client("s3")
    names = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix + "/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                names.append(key[len(prefix) + 1:-len(".json")])
    if not names:
        print(f"(no dashboards in s3://{bucket}/{prefix}/)")
        return 0
    print(f"dashboards in s3://{bucket}/{prefix}/:")
    for n in sorted(names):
        print(f"  {n}")
    return 0


def rm(name: str) -> int:
    bucket, prefix = _bucket(), _prefix()
    key = f"{prefix}/{name.removesuffix('.json')}.json"
    boto3.client("s3").delete_object(Bucket=bucket, Key=key)
    print(f"removed s3://{bucket}/{key}")
    return 0
