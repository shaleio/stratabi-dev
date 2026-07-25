"""Quick Demo orchestration — embedded, no AWS.

Generates the deterministic ForgeWorks dataset, exports CSVs, bakes the static
Quick Demo dashboard, and writes both into the application cache directory (never
into the installed package or the user's dashboard registry). Idempotent.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Protocol

from . import (DATA_SOURCE_EMBEDDED, DEMO_ID, DEMO_VERSION, QUICK_DASHBOARD_ID,
               cache_dir, dashboards_dir, data_dir)
from . import dashboard as DASH
from . import generate as GEN
from . import metrics as MX

_INSTALL_META = "install.json"


class ForgeWorksDataSource(Protocol):
    """Narrow abstraction: both adapters answer the same demo questions."""
    def kpis(self) -> dict: ...
    def revenue_by_month(self) -> list: ...
    def revenue_by_region(self) -> list: ...
    def margin_by_category(self) -> list: ...
    def fulfillment_performance(self) -> list: ...
    def inventory_risk(self) -> list: ...
    def delayed_orders(self) -> list: ...


class EmbeddedForgeWorksDataSource:
    """Embedded adapter — computes metrics from the deterministic in-memory dataset."""
    def __init__(self, tables=None):
        self._t = tables or GEN.generate()

    def kpis(self): return MX.kpis(self._t)
    def revenue_by_month(self): return MX.revenue_by_month(self._t)
    def revenue_by_region(self): return MX.revenue_by_region(self._t)
    def margin_by_category(self): return MX.margin_by_category(self._t)
    def fulfillment_performance(self): return MX.fulfillment_performance(self._t)
    def inventory_risk(self): return MX.inventory_risk(self._t)
    def delayed_orders(self): return MX.delayed_orders(self._t)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def generate_demo(force: bool = False, write_csv: bool = True) -> dict:
    """Generate the Quick Demo assets into the cache dir. Idempotent."""
    dash_path = dashboards_dir() / f"{QUICK_DASHBOARD_ID}.json"
    meta_path = cache_dir() / _INSTALL_META
    if dash_path.exists() and not force:
        return json.loads(meta_path.read_text()) if meta_path.exists() else _meta(dash_path, [])

    tables = GEN.generate()
    csvs = {}
    if write_csv:
        written = GEN.export_csvs(tables, data_dir())
        csvs = {k: str(v) for k, v in written.items()}

    dashboards_dir().mkdir(parents=True, exist_ok=True)
    dash = DASH.build_embedded_dashboard(tables)
    dash_path.write_text(json.dumps(dash, indent=2), encoding="utf-8")

    meta = _meta(dash_path, list(csvs), rows={k: len(v) for k, v in tables.items()})
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _meta(dash_path, csvs, rows=None) -> dict:
    return {
        "demo": True, "demo_id": DEMO_ID, "demo_version": DEMO_VERSION,
        "data_source": DATA_SOURCE_EMBEDDED, "dashboard_id": QUICK_DASHBOARD_ID,
        "dashboard_path": str(dash_path), "csv_tables": csvs,
        "rows": rows or {}, "generated_at": _now(),
    }


def status() -> dict:
    meta_path = cache_dir() / _INSTALL_META
    dash_path = dashboards_dir() / f"{QUICK_DASHBOARD_ID}.json"
    installed = dash_path.exists()
    out = {"installed": installed, "data_source": DATA_SOURCE_EMBEDDED,
           "cache_dir": str(cache_dir()), "dashboard_installed": installed}
    if meta_path.exists():
        try:
            out.update({"meta": json.loads(meta_path.read_text())})
        except Exception:
            pass
    return out


def remove_local() -> list[str]:
    """Remove only the local Quick Demo cache (data + dashboard + metadata)."""
    removed = []
    root = cache_dir()
    if root.exists():
        for p in sorted(root.rglob("*"), reverse=True):
            try:
                if p.is_file():
                    p.unlink(); removed.append(str(p))
                elif p.is_dir():
                    p.rmdir()
            except OSError:
                pass
        try:
            root.rmdir()
        except OSError:
            pass
    return removed


def launch_env() -> dict:
    """Environment overrides that make the app render the Quick Demo with NO AWS:
    local mode + point the local dashboard dir at the demo cache + a default region
    so boto3 client *construction* (not calls) succeeds for static tiles."""
    import os
    env = dict(os.environ)
    env.setdefault("AWS_REGION", "us-east-1")
    env.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    env["STRATABI_MODE"] = "local"
    env["STRATABI_LOCAL_DASHBOARD_DIR"] = str(dashboards_dir())
    return env
