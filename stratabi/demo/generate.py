"""Deterministic ForgeWorks data generation — pure standard library.

Uses a single seeded `random.Random` so the same release + seed produce logically
identical rows. Returns plain rows (`list[dict]`) keyed by table name, in the
canonical column order from `schemas.py`. CSV export uses the stdlib `csv` module
(UTF-8, header row, safe quoting, ISO-8601 dates, no formula-injection).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import random
from pathlib import Path

from . import FORGEWORKS_DEMO_SEED, model as M
from .schemas import SCHEMAS, columns

# Characters that make a CSV cell a spreadsheet-formula-injection risk.
_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _iso(d: dt.date) -> str:
    return d.isoformat()


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


def _month_dates() -> list[dt.date]:
    return [dt.date(M.START_DATE.year + (M.START_DATE.month - 1 + i) // 12,
                    (M.START_DATE.month - 1 + i) % 12 + 1, 1)
            for i in range(12)]


def generate() -> dict[str, list[dict]]:
    """Generate all ForgeWorks tables deterministically. Returns {table: [rows]}."""
    rng = random.Random(FORGEWORKS_DEMO_SEED)
    months = _month_dates()

    # ---- customers ----
    customers = []
    for i in range(1, M.N_CUSTOMERS + 1):
        seg = rng.choices(M.CUSTOMER_SEGMENTS, weights=[5, 2, 3, 1])[0]
        region = rng.choice(M.REGIONS)
        signup = M.START_DATE - dt.timedelta(days=rng.randint(30, 900))
        customers.append({
            "customer_id": f"CUST-{i:05d}",
            "customer_name": f"ForgeWorks Customer {i:04d}",
            "segment": seg,
            "region": region,
            "signup_date": _iso(signup),
        })
    cust_region = {c["customer_id"]: c["region"] for c in customers}
    cust_segment = {c["customer_id"]: c["segment"] for c in customers}
    cust_ids = [c["customer_id"] for c in customers]

    # ---- products ----
    products = []
    cat_names = list(M.CATEGORIES.keys())
    for i in range(1, M.N_PRODUCTS + 1):
        cat = cat_names[i % len(cat_names)]
        base_margin = M.CATEGORIES[cat]
        unit_cost = _round2(rng.uniform(4, 240))
        margin = min(0.8, max(0.05, rng.gauss(base_margin, 0.05)))
        unit_price = _round2(unit_cost / (1 - margin))
        products.append({
            "product_id": f"PROD-{i:03d}",
            "product_name": f"{cat} Item {i:03d}",
            "category": cat,
            "unit_cost": unit_cost,
            "unit_price": unit_price,
        })
    prod_by_cat = {}
    for p in products:
        prod_by_cat.setdefault(p["category"], []).append(p)
    prod_lookup = {p["product_id"]: p for p in products}

    # ---- orders + order_items + fulfillment_events ----
    orders, items, fulfillment = [], [], []
    month_weights = [M.MONTHLY_SEASONALITY[i] for i in range(12)]
    today = M.END_DATE
    item_seq = 0
    event_seq = 0

    for n in range(1, M.N_ORDERS + 1):
        month = rng.choices(months, weights=month_weights)[0]
        # day within month
        if month.month == 12:
            nxt = dt.date(month.year + 1, 1, 1)
        else:
            nxt = dt.date(month.year, month.month + 1, 1)
        span = (min(nxt, M.END_DATE + dt.timedelta(days=1)) - month).days
        order_date = month + dt.timedelta(days=rng.randrange(max(span, 1)))

        cust = rng.choice(cust_ids)
        region = cust_region[cust]
        fc = rng.choice(M.FULFILLMENT_CENTERS)

        # Supply-shock revenue dip: drop ~20% of shock-FC orders in the shock month.
        if (month == M.ANOMALY_SUPPLY_SHOCK_MONTH and fc == M.ANOMALY_SUPPLY_SHOCK_FC
                and rng.random() < (1 - M.ANOMALY_SUPPLY_SHOCK_REVENUE_MULT)):
            continue

        # status: canceled / open (recent) / completed
        r = rng.random()
        recent = (today - order_date).days <= 45
        if r < M.BASELINE_CANCEL_RATE:
            status = "canceled"
        elif recent and rng.random() < M.OPEN_ORDER_RATE / 1.0:
            status = "open"
        else:
            status = "completed"

        order_id = f"ORD-{n:06d}"
        seg_w = M.SEGMENT_ORDER_WEIGHT[cust_segment[cust]]
        n_lines = rng.randint(1, 5)
        order_total = 0.0
        for _ in range(n_lines):
            prod = rng.choice(products)
            qty = max(1, int(round(rng.uniform(1, 8) * seg_w)))
            # Promo spike: boost promo-category volume in the promo month.
            if (month == M.ANOMALY_PROMO_MONTH
                    and prod["category"] == M.ANOMALY_PROMO_CATEGORY):
                qty = int(round(qty * M.ANOMALY_PROMO_VOLUME_MULT)) or 1
            line_rev = _round2(prod["unit_price"] * qty)
            line_margin = _round2((prod["unit_price"] - prod["unit_cost"]) * qty)
            item_seq += 1
            items.append({
                "order_item_id": f"OI-{item_seq:07d}",
                "order_id": order_id,
                "product_id": prod["product_id"],
                "category": prod["category"],
                "quantity": qty,
                "unit_price": prod["unit_price"],
                "unit_cost": prod["unit_cost"],
                "line_revenue": line_rev,
                "line_margin": line_margin,
            })
            order_total += line_rev

        orders.append({
            "order_id": order_id,
            "customer_id": cust,
            "order_date": _iso(order_date),
            "region": region,
            "fulfillment_center": fc,
            "status": status,
            "order_total": _round2(order_total),
        })

        # fulfillment for shipped (completed/open) orders
        if status != "canceled":
            skew = M.FC_LATE_SKEW[fc]
            late_rate = M.BASELINE_LATE_RATE * skew
            if month == M.ANOMALY_SUPPLY_SHOCK_MONTH and fc == M.ANOMALY_SUPPLY_SHOCK_FC:
                late_rate = M.ANOMALY_SUPPLY_SHOCK_LATE_RATE
            shipped = order_date + dt.timedelta(days=rng.randint(1, 4))
            promised = order_date + dt.timedelta(days=5)
            is_late = rng.random() < late_rate
            days_late = rng.randint(1, 9) if is_late else 0
            delivered = shipped + dt.timedelta(days=2 + days_late)
            event_seq += 1
            fulfillment.append({
                "event_id": f"FE-{event_seq:07d}",
                "order_id": order_id,
                "fulfillment_center": fc,
                "shipped_date": _iso(shipped) if status == "completed" else "",
                "promised_date": _iso(promised),
                "delivered_date": _iso(delivered) if status == "completed" else "",
                "days_late": days_late,
                "late": bool(is_late),
            })

    # ---- daily_inventory (monthly snapshots per product × FC subset) ----
    inventory = []
    for snap in months:
        for p in products:
            fc = rng.choice(M.FULFILLMENT_CENTERS)
            reorder = rng.randint(20, 80)
            on_hand = rng.randint(0, 200)
            # Stockout risk elevated for shock FC in the shock month.
            if snap == M.ANOMALY_SUPPLY_SHOCK_MONTH and fc == M.ANOMALY_SUPPLY_SHOCK_FC:
                on_hand = rng.randint(0, reorder)
            inventory.append({
                "snapshot_date": _iso(snap),
                "product_id": p["product_id"],
                "fulfillment_center": fc,
                "on_hand": on_hand,
                "reorder_point": reorder,
                "stockout_risk": bool(on_hand < reorder),
            })

    tables = {
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_items": items,
        "fulfillment_events": fulfillment,
        "daily_inventory": inventory,
    }
    # Enforce canonical column order on every row.
    for name, rows in tables.items():
        cols = columns(name)
        tables[name] = [{c: row.get(c, "") for c in cols} for row in rows]
    return tables


def _sanitize(value) -> str:
    """Stringify a cell and neutralize spreadsheet-formula injection."""
    if isinstance(value, bool):
        return "true" if value else "false"
    s = "" if value is None else str(value)
    if s and s[0] in _INJECTION_PREFIXES:
        s = "'" + s
    return s


def to_csv_string(table: str, rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    cols = columns(table)
    w.writerow(cols)
    for row in rows:
        w.writerow([_sanitize(row.get(c)) for c in cols])
    return buf.getvalue()


def export_csvs(tables: dict[str, list[dict]], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, rows in tables.items():
        path = out_dir / f"{name}.csv"
        path.write_text(to_csv_string(name, rows), encoding="utf-8")
        written[name] = path
    return written
