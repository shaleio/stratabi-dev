"""Canonical ForgeWorks dashboard — one intent, two adapters.

`build_embedded_dashboard(tables)` bakes computed figures into **static** blocks
(Plotly figures + Plotly `table` figures + Markdown) — renders with no AWS.
`build_athena_dashboard(database)` produces the same panels as **Athena-backed**
tiles (`exec.type = athena` + SQL); Plotly `@column` refs bind to query results.

Both are schema-valid StrataBI dashboards. Demo identity is encoded in a parseable
`description` marker (the dashboard schema forbids extra top-level keys) and mirrored
in a sidecar metadata file for status/removal.
"""

from __future__ import annotations

from . import (ATHENA_DASHBOARD_ID, DATA_SOURCE_ATHENA, DATA_SOURCE_EMBEDDED,
               DEMO_ID, DEMO_VERSION, QUICK_DASHBOARD_ID, SYNTHETIC_NOTICE)
from . import metrics as MX

BADGE = {
    DATA_SOURCE_EMBEDDED: "ForgeWorks Quick Demo — Embedded synthetic data",
    DATA_SOURCE_ATHENA: "ForgeWorks AWS Demo — Amazon Athena",
}


def demo_marker(data_source: str) -> str:
    """Machine-parseable marker embedded in the dashboard description."""
    return f"[stratabi-demo {DEMO_ID} v{DEMO_VERSION} {data_source}]"


def _pos(row, order, width):
    return {"row": row, "order": order, "width": width}


def _notice_block(data_source):
    return {"type": "markdown", "config": {"content":
            f"### {BADGE[data_source]}\n\n_{SYNTHETIC_NOTICE}_"}}


def _line_fig(x, y, ytitle, refs=False):
    return {
        "data": [{"type": "scatter", "mode": "lines+markers",
                  "x": "@x" if refs else x, "y": "@y" if refs else y}],
        "layout": {"margin": {"t": 10, "l": 60, "r": 10, "b": 40},
                   "yaxis": {"title": ytitle}, "xaxis": {"title": ""}},
    }


def _bar_fig(x, y, ytitle, refs=False):
    return {
        "data": [{"type": "bar", "x": "@x" if refs else x, "y": "@y" if refs else y}],
        "layout": {"margin": {"t": 10, "l": 60, "r": 10, "b": 60},
                   "yaxis": {"title": ytitle}, "xaxis": {"title": ""}},
    }


def _table_fig(headers, columns):
    """A static Plotly `table` figure (column-major cell values)."""
    return {
        "data": [{"type": "table",
                  "header": {"values": headers, "align": "left"},
                  "cells": {"values": columns, "align": "left"}}],
        "layout": {"margin": {"t": 10, "l": 5, "r": 5, "b": 5}},
    }


def _plotly_tile(tid, title, pos, figure, exec_cfg=None, query=None):
    tile = {"id": tid, "title": title, "position": pos,
            "block": {"type": "plotly", "config": {"figure": figure, "height": "340px"}}}
    if exec_cfg:
        tile["exec"] = exec_cfg
        tile["load"] = {"mode": "load_once"}
    if query:
        tile["query"] = query
    return tile


def _table_block_tile(tid, title, pos, exec_cfg, sql):
    return {"id": tid, "title": title, "position": pos,
            "exec": exec_cfg, "load": {"mode": "load_once"},
            "query": {"sql": sql},
            "block": {"type": "table", "config": {"page_size": 15}}}


# ---------------------------------------------------------------------------
# Embedded (Quick Demo) — baked static figures
# ---------------------------------------------------------------------------
def build_embedded_dashboard(tables) -> dict:
    k = MX.kpis(tables)
    trend = MX.revenue_by_month(tables)
    region = MX.revenue_by_region(tables)
    margin = MX.margin_by_category(tables)
    fulfil = MX.fulfillment_performance(tables)
    risk = MX.inventory_risk(tables)
    delayed = MX.delayed_orders(tables)

    kpi_md = (
        "| Metric | Value |\n|---|---|\n"
        f"| Revenue | ${k['revenue']:,.0f} |\n"
        f"| Gross margin | ${k['gross_margin']:,.0f} ({k['gross_margin_pct']}%) |\n"
        f"| Orders | {k['orders']:,} |\n"
        f"| Avg order value | ${k['avg_order_value']:,.0f} |\n"
        f"| Late-shipment rate | {k['late_shipment_rate_pct']}% |\n"
        f"| Open-order backlog | {k['open_backlog']:,} |\n"
    )

    layout = [
        {"id": "notice", "position": _pos(0, 0, 12), "block": _notice_block(DATA_SOURCE_EMBEDDED)},
        {"id": "kpis", "title": "Key metrics", "position": _pos(1, 0, 12),
         "block": {"type": "markdown", "config": {"content": kpi_md}}},
        _plotly_tile("revenue_trend", "Revenue trend", _pos(2, 0, 8),
                     _line_fig([r["month"] for r in trend], [r["revenue"] for r in trend], "Revenue ($)")),
        _plotly_tile("revenue_by_region", "Revenue by region", _pos(2, 1, 4),
                     _bar_fig([r["region"] for r in region], [r["revenue"] for r in region], "Revenue ($)")),
        _plotly_tile("margin_by_category", "Gross margin % by category", _pos(3, 0, 6),
                     _bar_fig([r["category"] for r in margin], [r["margin_pct"] for r in margin], "Margin %")),
        _plotly_tile("fulfillment_performance", "Late-shipment rate by fulfillment center", _pos(3, 1, 6),
                     _bar_fig([r["fulfillment_center"] for r in fulfil], [r["late_rate_pct"] for r in fulfil], "Late %")),
        _plotly_tile("inventory_risk", "Inventory stock-out risk", _pos(4, 0, 6),
                     _table_fig(["Product", "Name", "FC", "On hand", "Reorder"],
                                [[r["product_id"] for r in risk], [r["product_name"] for r in risk],
                                 [r["fulfillment_center"] for r in risk], [r["on_hand"] for r in risk],
                                 [r["reorder_point"] for r in risk]])),
        _plotly_tile("delayed_orders", "Most delayed orders", _pos(4, 1, 6),
                     _table_fig(["Order", "Region", "FC", "Promised", "Days late"],
                                [[r["order_id"] for r in delayed], [r["region"] for r in delayed],
                                 [r["fulfillment_center"] for r in delayed], [r["promised_date"] for r in delayed],
                                 [r["days_late"] for r in delayed]])),
    ]
    return {
        "name": "ForgeWorks Quick Demo",
        "description": f"{demo_marker(DATA_SOURCE_EMBEDDED)} ForgeWorks Distribution — "
                       "synthetic demonstration (embedded data, no AWS). " + SYNTHETIC_NOTICE,
        "version": "1.0.0",
        "layout": layout,
    }


# ---------------------------------------------------------------------------
# Athena (AWS Demo) — same panels, real SQL
# ---------------------------------------------------------------------------
def build_athena_dashboard(database: str) -> dict:
    ex = {"type": "athena", "database": database}

    def q(sql):  # collapse whitespace
        return " ".join(sql.split())

    trend_sql = q("""SELECT substr(cast(order_date as varchar),1,7) AS x,
        round(sum(order_total),2) AS y FROM orders WHERE status <> 'canceled'
        GROUP BY 1 ORDER BY 1""")
    region_sql = q("""SELECT region AS x, round(sum(order_total),2) AS y FROM orders
        WHERE status <> 'canceled' GROUP BY 1 ORDER BY 2 DESC""")
    margin_sql = q("""SELECT i.category AS x,
        round(100.0*sum(i.line_margin)/sum(i.line_revenue),1) AS y
        FROM order_items i JOIN orders o ON i.order_id = o.order_id
        WHERE o.status <> 'canceled' GROUP BY 1 ORDER BY 2 DESC""")
    fc_sql = q("""SELECT fulfillment_center AS x,
        round(100.0*sum(cast(late as integer))/count(*),1) AS y
        FROM fulfillment_events GROUP BY 1 ORDER BY 2 DESC""")
    risk_sql = q("""SELECT product_id, fulfillment_center, on_hand, reorder_point
        FROM daily_inventory WHERE stockout_risk ORDER BY on_hand - reorder_point ASC LIMIT 15""")
    delayed_sql = q("""SELECT order_id, fulfillment_center, promised_date, days_late
        FROM fulfillment_events WHERE late ORDER BY days_late DESC LIMIT 15""")
    kpi_sql = q("""SELECT round(sum(order_total),2) AS revenue, count(*) AS orders,
        round(avg(order_total),2) AS avg_order_value
        FROM orders WHERE status <> 'canceled'""")

    layout = [
        {"id": "notice", "position": _pos(0, 0, 12), "block": _notice_block(DATA_SOURCE_ATHENA)},
        _table_block_tile("kpis", "Key metrics", _pos(1, 0, 12), ex, kpi_sql),
        _plotly_tile("revenue_trend", "Revenue trend", _pos(2, 0, 8),
                     _line_fig(None, None, "Revenue ($)", refs=True), exec_cfg=ex, query={"sql": trend_sql}),
        _plotly_tile("revenue_by_region", "Revenue by region", _pos(2, 1, 4),
                     _bar_fig(None, None, "Revenue ($)", refs=True), exec_cfg=ex, query={"sql": region_sql}),
        _plotly_tile("margin_by_category", "Gross margin % by category", _pos(3, 0, 6),
                     _bar_fig(None, None, "Margin %", refs=True), exec_cfg=ex, query={"sql": margin_sql}),
        _plotly_tile("fulfillment_performance", "Late-shipment rate by fulfillment center", _pos(3, 1, 6),
                     _bar_fig(None, None, "Late %", refs=True), exec_cfg=ex, query={"sql": fc_sql}),
        _table_block_tile("inventory_risk", "Inventory stock-out risk", _pos(4, 0, 6), ex, risk_sql),
        _table_block_tile("delayed_orders", "Most delayed orders", _pos(4, 1, 6), ex, delayed_sql),
    ]
    return {
        "name": "ForgeWorks AWS Demo",
        "description": f"{demo_marker(DATA_SOURCE_ATHENA)} ForgeWorks Distribution — "
                       "synthetic demonstration (Amazon Athena). " + SYNTHETIC_NOTICE,
        "version": "1.0.0",
        "layout": layout,
    }
