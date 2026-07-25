"""ForgeWorks Distribution — the first-party synthetic demonstration for StrataBI
Developer Edition.

ForgeWorks Distribution is **fictional**. All data is **synthetic**, generated
deterministically by Shaleio. Any resemblance to real entities or records is
coincidental. This package ships under the same Shaleio Guild Community License
(SGCL) as the rest of StrataBI Developer Edition.

One canonical demo model (schemas, generator, metrics, dashboard intent) is rendered
through two data-source adapters:

* **Embedded** (Quick Demo) — deterministic in-memory data baked into static blocks.
  No AWS, no credentials, no network.
* **Athena** (AWS Demo) — the same dataset uploaded to the customer's StrataBI Dev
  data plane and queried through Athena.

Nothing here creates AWS resources or incurs cost on import or on Quick Demo.
"""

from __future__ import annotations

import os
from pathlib import Path

# Deterministic seed — the same release + seed produce logically identical data.
FORGEWORKS_DEMO_SEED = 20260702

DEMO_ID = "forgeworks"
DEMO_VERSION = "1"
DEMO_TITLE = "ForgeWorks Distribution"

# Namespaced dashboard ids (never collide with user dashboards).
QUICK_DASHBOARD_ID = "forgeworks_quick_demo"
ATHENA_DASHBOARD_ID = "forgeworks_athena_demo"

# AWS namespacing — everything the AWS demo creates is isolated under these.
S3_DEMO_PREFIX = "demo/forgeworks/v1/"
GLUE_DEMO_DATABASE = "stratabi_dev_demo"

DATA_SOURCE_EMBEDDED = "embedded"
DATA_SOURCE_ATHENA = "athena"

SYNTHETIC_NOTICE = (
    "ForgeWorks Distribution is fictional. All data is synthetic. "
    "Any resemblance to real entities or records is coincidental."
)

# Logical tables, in dependency order.
TABLES = [
    "customers",
    "products",
    "orders",
    "order_items",
    "fulfillment_events",
    "daily_inventory",
]


def cache_dir() -> Path:
    """Application cache dir for generated demo assets. Uses platformdirs when
    available; falls back to ~/.cache. Never writes into the installed package."""
    try:
        from platformdirs import user_cache_dir
        base = Path(user_cache_dir("stratabi"))
    except Exception:
        base = Path(os.path.expanduser("~")) / ".cache" / "stratabi"
    return base / "demo" / DEMO_ID / f"v{DEMO_VERSION}"


def data_dir() -> Path:
    """Where generated CSVs live."""
    return cache_dir() / "data"


def dashboards_dir() -> Path:
    """Where the generated Quick Demo dashboard JSON lives (the app can be pointed
    here via STRATABI_LOCAL_DASHBOARD_DIR without touching the user's registry)."""
    return cache_dir() / "dashboards"
