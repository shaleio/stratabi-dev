"""ForgeWorks Distribution — canonical business model.

Fixed, documented parameters that drive deterministic generation. The intended
patterns and anomalies are declared here so screenshots, tests, and user
observations are reproducible.

Fictional company: **ForgeWorks Distribution**, a made-up industrial-supply
distributor. All values are invented.
"""

from __future__ import annotations

import datetime as dt

# 12-month window (inclusive of start, exclusive of end+1 day handled in generate).
START_DATE = dt.date(2025, 6, 1)
END_DATE = dt.date(2026, 5, 31)

REGIONS = ["Northeast", "Southeast", "Midwest", "Mountain", "Pacific"]

# Product categories with baseline gross-margin targets (fraction of price).
CATEGORIES = {
    "Fasteners": 0.42,
    "Power Tools": 0.28,
    "Safety Gear": 0.51,
    "Abrasives": 0.36,
    "Adhesives": 0.44,
    "Measuring": 0.33,
}

FULFILLMENT_CENTERS = ["FC-ATLAS", "FC-BOREAS", "FC-CRONOS", "FC-DELOS"]

CUSTOMER_SEGMENTS = ["Contractor", "Enterprise", "Reseller", "Government"]

# ---- Scale (kept small for a Developer Edition demo) ----------------------------
N_CUSTOMERS = 1200
N_PRODUCTS = 100
N_ORDERS = 18000

# ---- Seasonality: multiplicative monthly factor (Jun..May), peak in autumn. -----
# index 0 = START_DATE month. Documented so the "revenue trend" is interpretable.
MONTHLY_SEASONALITY = [
    0.92, 0.95, 1.02, 1.18, 1.25, 1.10,   # Jun Jul Aug Sep Oct Nov
    0.98, 0.90, 0.97, 1.05, 1.08, 1.00,   # Dec Jan Feb Mar Apr May
]

# ---- Documented anomalies (reproducible) ----------------------------------------
# 1) SUPPLY SHOCK: in this month, one FC has a spike in late shipments + stockouts,
#    and revenue dips ~20% vs its seasonal expectation.
ANOMALY_SUPPLY_SHOCK_MONTH = dt.date(2026, 1, 1)   # January
ANOMALY_SUPPLY_SHOCK_FC = "FC-CRONOS"
ANOMALY_SUPPLY_SHOCK_REVENUE_MULT = 0.80
ANOMALY_SUPPLY_SHOCK_LATE_RATE = 0.55              # vs baseline ~0.12

# 2) PROMO SPIKE: a promotion lifts one category's volume ~40% for one month.
ANOMALY_PROMO_MONTH = dt.date(2025, 10, 1)         # October
ANOMALY_PROMO_CATEGORY = "Power Tools"
ANOMALY_PROMO_VOLUME_MULT = 1.40

# ---- Baseline operational rates -------------------------------------------------
BASELINE_LATE_RATE = 0.12
BASELINE_CANCEL_RATE = 0.05
OPEN_ORDER_RATE = 0.10          # fraction of recent orders still open (backlog)

# Per-FC baseline late-rate skew (before anomalies) — documented so "which FC has the
# most delays" has a stable answer outside the anomaly window.
FC_LATE_SKEW = {"FC-ATLAS": 0.9, "FC-BOREAS": 1.0, "FC-CRONOS": 1.15, "FC-DELOS": 1.05}

# Segment revenue weighting — Enterprise + Government skew larger orders.
SEGMENT_ORDER_WEIGHT = {"Contractor": 1.0, "Enterprise": 1.8, "Reseller": 1.3,
                        "Government": 1.6}


def month_index(d: dt.date) -> int:
    """0-based month offset from START_DATE (0..11)."""
    return (d.year - START_DATE.year) * 12 + (d.month - START_DATE.month)


def seasonality_for(d: dt.date) -> float:
    idx = month_index(d)
    if 0 <= idx < len(MONTHLY_SEASONALITY):
        return MONTHLY_SEASONALITY[idx]
    return 1.0


ANOMALY_NOTES = [
    f"Supply shock — {ANOMALY_SUPPLY_SHOCK_FC} in "
    f"{ANOMALY_SUPPLY_SHOCK_MONTH:%B %Y}: late-shipment rate rises to "
    f"~{int(ANOMALY_SUPPLY_SHOCK_LATE_RATE*100)}% and revenue dips ~20%.",
    f"Promo spike — {ANOMALY_PROMO_CATEGORY} in {ANOMALY_PROMO_MONTH:%B %Y}: "
    f"order volume up ~{int((ANOMALY_PROMO_VOLUME_MULT-1)*100)}%.",
]
