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
    s3 = get_s3_client()
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
