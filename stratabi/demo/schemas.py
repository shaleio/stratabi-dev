"""Canonical ForgeWorks table schemas — the single source of truth for column
order, types, and Athena/Glue DDL. Both adapters (embedded + Athena) use these so
the CSV header, the Glue table, and the in-memory dataframe always agree.

Types are expressed once and mapped to Athena/Glue types. Dates are ISO-8601.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    type: str          # logical type: string|int|double|date|timestamp|bool

    @property
    def athena_type(self) -> str:
        return {
            "string": "string",
            "int": "bigint",
            "double": "double",
            "date": "date",
            "timestamp": "timestamp",
            "bool": "boolean",
        }[self.type]


# Column order here is the canonical CSV column order.
SCHEMAS: dict[str, list[Column]] = {
    "customers": [
        Column("customer_id", "string"),
        Column("customer_name", "string"),
        Column("segment", "string"),
        Column("region", "string"),
        Column("signup_date", "date"),
    ],
    "products": [
        Column("product_id", "string"),
        Column("product_name", "string"),
        Column("category", "string"),
        Column("unit_cost", "double"),
        Column("unit_price", "double"),
    ],
    "orders": [
        Column("order_id", "string"),
        Column("customer_id", "string"),
        Column("order_date", "date"),
        Column("region", "string"),
        Column("fulfillment_center", "string"),
        Column("status", "string"),          # completed|open|canceled
        Column("order_total", "double"),
    ],
    "order_items": [
        Column("order_item_id", "string"),
        Column("order_id", "string"),
        Column("product_id", "string"),
        Column("category", "string"),
        Column("quantity", "int"),
        Column("unit_price", "double"),
        Column("unit_cost", "double"),
        Column("line_revenue", "double"),
        Column("line_margin", "double"),
    ],
    "fulfillment_events": [
        Column("event_id", "string"),
        Column("order_id", "string"),
        Column("fulfillment_center", "string"),
        Column("shipped_date", "date"),
        Column("promised_date", "date"),
        Column("delivered_date", "date"),
        Column("days_late", "int"),
        Column("late", "bool"),
    ],
    "daily_inventory": [
        Column("snapshot_date", "date"),
        Column("product_id", "string"),
        Column("fulfillment_center", "string"),
        Column("on_hand", "int"),
        Column("reorder_point", "int"),
        Column("stockout_risk", "bool"),
    ],
}


def columns(table: str) -> list[str]:
    return [c.name for c in SCHEMAS[table]]


def athena_ddl(table: str, database: str, location: str) -> str:
    """External Athena/Glue table over CSV (skip header). Explicit — no crawler."""
    cols = ",\n  ".join(f"`{c.name}` {c.athena_type}" for c in SCHEMAS[table])
    return (
        f"CREATE EXTERNAL TABLE IF NOT EXISTS `{database}`.`{table}` (\n"
        f"  {cols}\n"
        ")\n"
        "ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'\n"
        "WITH SERDEPROPERTIES ("
        "'separatorChar'=',','quoteChar'='\"','escapeChar'='\\\\')\n"
        f"LOCATION '{location}'\n"
        "TBLPROPERTIES ('skip.header.line.count'='1','has_encrypted_data'='false');"
    )
