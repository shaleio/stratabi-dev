"""Canonical ForgeWorks metrics — computed over plain rows (pure stdlib).

These are the single definitions of each business metric, used by the embedded
adapter to bake figures. The Athena adapter expresses the same metrics as SQL
(see athena.py / dashboard.py) so both data sources answer the same questions.

Revenue counts non-canceled orders. Margin uses order_items.line_margin.
"""

from __future__ import annotations

from collections import defaultdict


def _revenue_rows(tables):
    live = {o["order_id"] for o in tables["orders"] if o["status"] != "canceled"}
    return [it for it in tables["order_items"] if it["order_id"] in live]


def kpis(tables) -> dict:
    orders = tables["orders"]
    live = [o for o in orders if o["status"] != "canceled"]
    revenue = sum(o["order_total"] for o in live)
    items = _revenue_rows(tables)
    margin = sum(i["line_margin"] for i in items)
    fe = tables["fulfillment_events"]
    late = sum(1 for f in fe if f["late"])
    late_rate = late / len(fe) if fe else 0.0
    backlog = sum(1 for o in orders if o["status"] == "open")
    n = len(live)
    return {
        "revenue": round(revenue, 2),
        "gross_margin": round(margin, 2),
        "gross_margin_pct": round(100 * margin / revenue, 1) if revenue else 0.0,
        "orders": n,
        "avg_order_value": round(revenue / n, 2) if n else 0.0,
        "late_shipment_rate_pct": round(100 * late_rate, 1),
        "open_backlog": backlog,
    }


def revenue_by_month(tables):
    agg = defaultdict(float)
    for o in tables["orders"]:
        if o["status"] != "canceled":
            agg[o["order_date"][:7]] += o["order_total"]
    return [{"month": m, "revenue": round(v, 2)} for m, v in sorted(agg.items())]


def revenue_by_region(tables):
    agg = defaultdict(float)
    for o in tables["orders"]:
        if o["status"] != "canceled":
            agg[o["region"]] += o["order_total"]
    return [{"region": r, "revenue": round(v, 2)}
            for r, v in sorted(agg.items(), key=lambda kv: -kv[1])]


def margin_by_category(tables):
    rev = defaultdict(float)
    mar = defaultdict(float)
    for i in _revenue_rows(tables):
        rev[i["category"]] += i["line_revenue"]
        mar[i["category"]] += i["line_margin"]
    out = []
    for c in sorted(rev, key=lambda k: -mar[k]):
        out.append({"category": c, "revenue": round(rev[c], 2),
                    "margin": round(mar[c], 2),
                    "margin_pct": round(100 * mar[c] / rev[c], 1) if rev[c] else 0.0})
    return out


def fulfillment_performance(tables):
    total = defaultdict(int)
    late = defaultdict(int)
    for f in tables["fulfillment_events"]:
        total[f["fulfillment_center"]] += 1
        if f["late"]:
            late[f["fulfillment_center"]] += 1
    out = []
    for fc in sorted(total, key=lambda k: -(late[k] / total[k] if total[k] else 0)):
        out.append({"fulfillment_center": fc, "shipments": total[fc],
                    "late": late[fc],
                    "late_rate_pct": round(100 * late[fc] / total[fc], 1) if total[fc] else 0.0})
    return out


def inventory_risk(tables, limit=15):
    at_risk = [r for r in tables["daily_inventory"] if r["stockout_risk"]]
    # latest snapshot per product
    latest = {}
    for r in at_risk:
        k = r["product_id"]
        if k not in latest or r["snapshot_date"] > latest[k]["snapshot_date"]:
            latest[k] = r
    rows = sorted(latest.values(), key=lambda r: (r["on_hand"] - r["reorder_point"]))
    prod = {p["product_id"]: p for p in tables["products"]}
    out = []
    for r in rows[:limit]:
        p = prod.get(r["product_id"], {})
        out.append({"product_id": r["product_id"],
                    "product_name": p.get("product_name", ""),
                    "fulfillment_center": r["fulfillment_center"],
                    "on_hand": r["on_hand"], "reorder_point": r["reorder_point"]})
    return out


def delayed_orders(tables, limit=15):
    late = [f for f in tables["fulfillment_events"] if f["late"]]
    late.sort(key=lambda f: -f["days_late"])
    o_by = {o["order_id"]: o for o in tables["orders"]}
    out = []
    for f in late[:limit]:
        o = o_by.get(f["order_id"], {})
        out.append({"order_id": f["order_id"], "region": o.get("region", ""),
                    "fulfillment_center": f["fulfillment_center"],
                    "promised_date": f["promised_date"], "days_late": f["days_late"]})
    return out


def top_customers(tables, limit=10):
    agg = defaultdict(float)
    for o in tables["orders"]:
        if o["status"] != "canceled":
            agg[o["customer_id"]] += o["order_total"]
    seg = {c["customer_id"]: c["segment"] for c in tables["customers"]}
    rows = sorted(agg.items(), key=lambda kv: -kv[1])[:limit]
    return [{"customer_id": cid, "segment": seg.get(cid, ""), "revenue": round(v, 2)}
            for cid, v in rows]
