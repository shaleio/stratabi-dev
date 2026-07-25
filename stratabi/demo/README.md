# ForgeWorks Distribution — StrataBI demo

**ForgeWorks Distribution is fictional. All data is synthetic. Any resemblance to
real entities or records is coincidental.** This package ships under the same Shaleio
Guild Community License (SGCL) as StrataBI Developer Edition.

One canonical demo model, two data-source adapters:

| | Quick Demo (embedded) | AWS Demo (Athena) |
|---|---|---|
| Data | deterministic, in-memory, baked into static blocks | same data uploaded to your S3 + Glue |
| AWS | none | your StrataBI Dev data plane |
| Badge | *ForgeWorks Quick Demo — Embedded synthetic data* | *ForgeWorks AWS Demo — Amazon Athena* |
| Dashboard id | `forgeworks_quick_demo` | `forgeworks_athena_demo` |

## Module map

- `model.py` — business parameters + **documented anomalies** (supply shock, promo spike).
- `schemas.py` — canonical column order/types + Athena DDL (no crawler).
- `generate.py` — deterministic generator (seed `20260702`, pure stdlib) + CSV export.
- `metrics.py` — canonical metric definitions (revenue, margin, late rate, backlog, …).
- `dashboard.py` — one dashboard intent → `build_embedded_dashboard` / `build_athena_dashboard`.
- `quick.py` — Quick Demo orchestration + `EmbeddedForgeWorksDataSource`.
- `athena.py` — AWS install (S3 → Glue → Athena verify) + `AthenaForgeWorksDataSource`.
- `cleanup.py` — ownership-validated removal (local + AWS).

## Data model

Tables: `customers` (1,200), `products` (100), `orders` (~18,000), `order_items`
(derived), `fulfillment_events` (per shipped order), `daily_inventory` (12 monthly
snapshots × products). Fixed seed → logically identical data every run.

## Documented anomalies (reproducible)

1. **Supply shock** — `FC-CRONOS`, January: late-shipment rate rises to ~55% and
   revenue dips ~20%.
2. **Promo spike** — `Power Tools`, October: order volume up ~40%.

## Determinism

`FORGEWORKS_DEMO_SEED = 20260702`. The generator uses a single seeded `random.Random`;
CSV bytes are stable across runs of the same release.

## No AWS on import or Quick Demo

Importing this package and running the Quick Demo never touches AWS. The AWS Demo
requires explicit confirmation and only creates resources under the isolated demo
namespace (`s3://<bucket>/demo/forgeworks/v1/`, Glue database `stratabi_dev_demo`).
