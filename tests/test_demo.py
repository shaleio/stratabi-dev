"""ForgeWorks demo tests — generation, Quick Demo, dashboards, and AWS (mocked).

Pure-stdlib + jsonschema; no AWS credentials, no network. AWS calls are exercised
through an in-memory fake session.
"""

import io
import json
import os
import re
from pathlib import Path

import pytest

from stratabi.demo import generate as G
from stratabi.demo import dashboard as D
from stratabi.demo import metrics as MX
from stratabi.demo import model as M

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "stratabi" / "data" / "schemas"
     / "dashboard.schema.json").read_text())


# ---------------- data generation ----------------
def test_generation_is_deterministic():
    a = G.generate(); b = G.generate()
    ja = "".join(G.to_csv_string(n, a[n]) for n in a)
    jb = "".join(G.to_csv_string(n, b[n]) for n in b)
    assert ja == jb


def test_row_counts_in_range():
    t = G.generate()
    assert len(t["customers"]) == M.N_CUSTOMERS
    assert len(t["products"]) == M.N_PRODUCTS
    assert 15000 <= len(t["orders"]) <= 30000
    assert len(t["order_items"]) > len(t["orders"])
    assert len(t["daily_inventory"]) == 12 * M.N_PRODUCTS


def test_foreign_keys_are_valid():
    t = G.generate()
    cust = {c["customer_id"] for c in t["customers"]}
    prod = {p["product_id"] for p in t["products"]}
    orders = {o["order_id"] for o in t["orders"]}
    assert all(o["customer_id"] in cust for o in t["orders"])
    assert all(i["order_id"] in orders for i in t["order_items"])
    assert all(i["product_id"] in prod for i in t["order_items"])
    assert all(f["order_id"] in orders for f in t["fulfillment_events"])


def test_no_realistic_pii():
    t = G.generate()
    assert all(re.fullmatch(r"ForgeWorks Customer \d{4}", c["customer_name"])
               for c in t["customers"])


def test_anomaly_supply_shock_present():
    t = G.generate()
    ofc = {o["order_id"]: (o["order_date"], o["fulfillment_center"]) for o in t["orders"]}
    m = M.ANOMALY_SUPPLY_SHOCK_MONTH.isoformat()[:7]
    shock = [f for f in t["fulfillment_events"]
             if ofc.get(f["order_id"]) and ofc[f["order_id"]][1] == M.ANOMALY_SUPPLY_SHOCK_FC
             and ofc[f["order_id"]][0][:7] == m]
    rate = sum(1 for f in shock if f["late"]) / max(len(shock), 1)
    assert rate > 0.35  # baseline is ~0.12


def test_csv_is_safe_and_well_formed():
    t = G.generate()
    csv = G.to_csv_string("orders", t["orders"])
    lines = csv.splitlines()
    assert lines[0] == "order_id,customer_id,order_date,region,fulfillment_center,status,order_total"
    # ISO dates
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", t["orders"][0]["order_date"])
    # no formula injection: sanitized cells never start with = + - @
    for row in t["orders"]:
        for v in row.values():
            s = str(v)
            assert not s[:1] in ("=", "+", "@") or s.startswith("'")


def test_generation_idempotent_export(tmp_path):
    t = G.generate()
    a = G.export_csvs(t, tmp_path / "a")
    b = G.export_csvs(t, tmp_path / "b")
    for name in a:
        assert Path(a[name]).read_bytes() == Path(b[name]).read_bytes()


# ---------------- dashboards ----------------
def test_embedded_dashboard_is_schema_valid():
    jsonschema = pytest.importorskip("jsonschema")
    d = D.build_embedded_dashboard(G.generate())
    jsonschema.validate(d, SCHEMA)
    assert d["name"] == "ForgeWorks Quick Demo"
    assert "Embedded synthetic data" in json.dumps(d)  # visible badge


def test_athena_dashboard_is_schema_valid_and_uses_athena():
    jsonschema = pytest.importorskip("jsonschema")
    d = D.build_athena_dashboard("stratabi_dev_demo")
    jsonschema.validate(d, SCHEMA)
    execs = [t.get("exec", {}).get("type") for t in d["layout"] if t.get("exec")]
    assert execs and set(execs) == {"athena"}
    assert "Amazon Athena" in json.dumps(d)


def test_embedded_bakes_data_athena_uses_refs():
    emb = D.build_embedded_dashboard(G.generate())
    ath = D.build_athena_dashboard("db")
    et = next(t for t in emb["layout"] if t["id"] == "revenue_trend")
    at = next(t for t in ath["layout"] if t["id"] == "revenue_trend")
    assert isinstance(et["block"]["config"]["figure"]["data"][0]["x"], list)
    assert at["block"]["config"]["figure"]["data"][0]["x"] == "@x"


# ---------------- Quick Demo orchestration ----------------
def test_quick_demo_no_aws(monkeypatch, tmp_path):
    monkeypatch.setattr("stratabi.demo.cache_dir", lambda: tmp_path / "c")
    monkeypatch.setattr("stratabi.demo.data_dir", lambda: tmp_path / "c" / "data")
    monkeypatch.setattr("stratabi.demo.dashboards_dir", lambda: tmp_path / "c" / "dash")
    from stratabi.demo import quick
    # ensure the module-level references resolve to patched fns
    monkeypatch.setattr(quick, "cache_dir", lambda: tmp_path / "c")
    monkeypatch.setattr(quick, "data_dir", lambda: tmp_path / "c" / "data")
    monkeypatch.setattr(quick, "dashboards_dir", lambda: tmp_path / "c" / "dash")
    for k in ("AWS_ACCESS_KEY_ID", "AWS_PROFILE"):
        monkeypatch.delenv(k, raising=False)
    meta = quick.generate_demo(force=True)
    assert Path(meta["dashboard_path"]).exists()
    assert quick.status()["installed"] is True
    removed = quick.remove_local()
    assert removed and quick.remove_local() == []  # idempotent


# ---------------- AWS Demo (mocked) ----------------
class _Client:
    def __init__(self, name, log, meta):
        self.name, self.log, self.meta = name, log, meta
    class exceptions:  # noqa: N801
        class AlreadyExistsException(Exception): ...
    def get_paginator(self, _):
        outer = self
        class P:
            def paginate(self, **kw):
                return [{"Contents": [{"Key": "demo/forgeworks/v1/orders/orders.csv"},
                                      {"Key": "demo/forgeworks/v1/_demo_install.json"}]}]
        return P()
    def __getattr__(self, m):
        def call(**kw):
            self.log.append((self.name, m, kw))
            if self.name == "sts" and m == "get_caller_identity":
                return {"Account": "000000000000"}
            if self.name == "athena" and m == "start_query_execution":
                return {"QueryExecutionId": "q"}
            if self.name == "athena" and m == "get_query_execution":
                return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}
            if self.name == "s3" and m == "get_object":
                return {"Body": io.BytesIO(json.dumps(self.meta[0]).encode())}
            return {}
        return call


class _Session:
    def __init__(self, log, meta):
        self.region_name = "us-east-1"; self.log = log; self.meta = meta
    def client(self, name):
        return _Client(name, self.log, self.meta)


@pytest.fixture()
def aws_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STRATABI_SYSTEM_BUCKET", "cust-bucket")
    monkeypatch.setenv("STRATABI_ATHENA_OUTPUT", "s3://cust-bucket/athena/")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setattr("stratabi.demo.data_dir", lambda: tmp_path / "d")
    monkeypatch.setattr("stratabi.demo.cache_dir", lambda: tmp_path / "c")
    from stratabi.demo import athena, cleanup
    monkeypatch.setattr(athena, "data_dir", lambda: tmp_path / "d")
    monkeypatch.setattr(athena, "cache_dir", lambda: tmp_path / "c")
    return athena, cleanup


def test_aws_install_namespaced_and_no_hq(aws_env):
    athena, _ = aws_env
    log, meta = [], [None]
    res = athena.install(_Session(log, meta), confirm=False)
    assert res["installed"]
    puts = [c[2]["Key"] for c in log if c[0] == "s3" and c[1] == "put_object"]
    assert all(k.startswith("demo/forgeworks/v1/") or k.startswith("analyst/dashboards/")
               for k in puts)
    ddls = [c[2]["QueryString"] for c in log
            if c[0] == "athena" and "CREATE EXTERNAL" in c[2].get("QueryString", "")]
    assert len(ddls) == 6 and all("`stratabi_dev_demo`" in d for d in ddls)
    assert not any("entitle" in str(c).lower() for c in log)  # no StrataHQ


def test_aws_missing_data_plane_errors(monkeypatch):
    from stratabi.demo import athena
    monkeypatch.delenv("STRATABI_SYSTEM_BUCKET", raising=False)
    monkeypatch.delenv("STRATABI_ATHENA_OUTPUT", raising=False)
    with pytest.raises(athena.DemoNotReadyError) as e:
        athena.discover(_Session([], [None]), profile="demo")
    assert "stratacli dev install" in str(e.value)


def test_aws_remove_only_demo_namespace(aws_env):
    athena, cleanup = aws_env
    log, meta = [], [None]
    meta[0] = athena.install(_Session([], meta), confirm=False)
    res = cleanup.remove_aws(_Session(log, meta), confirm=False)
    assert res["removed"]
    deleted = []
    for c in log:
        if c[1] == "delete_objects":
            deleted += [o["Key"] for o in c[2]["Delete"]["Objects"]]
        if c[1] == "delete_object":
            deleted.append(c[2]["Key"])
    assert all(k.startswith("demo/forgeworks/v1/") or "forgeworks_athena_demo" in k
               for k in deleted)
    assert any(c[1] == "delete_database" and c[2]["Name"] == "stratabi_dev_demo" for c in log)
