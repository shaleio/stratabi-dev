from pathlib import Path
import json
from .config import config


ROOT = Path(__file__).resolve().parents[2]    # /app
BOOTSTRAP = ROOT / "bootstrap"


def _local_dashboard_dir():
    """Local dashboards live at: /app/bootstrap/dashboards.

    STRATABI_LOCAL_DASHBOARD_DIR overrides this (used by the ForgeWorks Quick Demo
    to render from the app cache dir without touching the user's registry)."""
    import os
    override = os.getenv("STRATABI_LOCAL_DASHBOARD_DIR", "").strip()
    if override:
        return Path(override)
    return BOOTSTRAP / "dashboards"


def load_dashboards_local():
    dashboards = {}
    folder = _local_dashboard_dir()

    if not folder.exists():
        return dashboards

    for file in folder.glob("*.json"):
        dashboards[file.stem] = json.loads(file.read_text())

    return dashboards


def load_dashboards_s3():
    import boto3
    s3 = boto3.client("s3")
    prefix = config.DASHBOARD_PREFIX

    resp = s3.list_objects_v2(
        Bucket=config.BUCKET,
        Prefix=prefix
    )

    dashboards = {}
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".json"):
            continue
        name = key.split("/")[-1].replace(".json", "")
        body = s3.get_object(Bucket=config.BUCKET, Key=key)["Body"].read()
        dashboards[name] = json.loads(body)

    return dashboards


def load_all_dashboards():
    return load_dashboards_s3() if config.MODE == "aws" else load_dashboards_local()


def load_dashboard_by_s3_key(key: str):
    """Read one dashboard JSON from an EXPLICIT system-bucket key (not the dashboards prefix).

    Used by the module-page `dashboard_source` seam so a module can render a per-session, generated
    dashboard. Caller is responsible for building an owner-isolated key. Returns the dict, or None if
    missing/unreadable (callers degrade to an empty state rather than erroring)."""
    if config.MODE != "aws":
        return None
    import boto3
    try:
        # The system bucket (STRATABI_SYSTEM_BUCKET) — the same bucket modules write to. Reading
        # config.BUCKET (STRATABI_BUCKET) here meant Bucket=None on standard installs, so every
        # session dashboard (StrataChat's Workspace) silently fell back to the empty layout.
        from stratabi.core.s3_loader import get_system_bucket
        from stratabi.core.config import aws_region
        body = boto3.client("s3", region_name=aws_region()).get_object(
            Bucket=get_system_bucket(), Key=key)["Body"].read()
        return json.loads(body)
    except Exception as exc:  # noqa: BLE001 — missing/denied/corrupt -> caller's empty state
        import logging
        logging.getLogger(__name__).info("dashboard_source %s unavailable: %s", key, exc)
        return None


def load_dashboard_json(name=None):
    dashboards = load_all_dashboards()
    if not dashboards:
        print("WARNING: No dashboards found in local or S3.")
        return {}

    if name is None:
        return next(iter(dashboards.values()))

    if name not in dashboards:
        raise KeyError(f"Dashboard '{name}' not found.")

    return dashboards[name]
