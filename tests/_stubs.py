"""Minimal stand-ins for dash / dbc / boto3 so page logic can be unit-tested without the UI
stack or AWS. Only what the modules touch at import time is stubbed; the functions under test
are pure Python. Tests that need ctx set `stub_ctx(...)`."""
import sys
import types
from unittest.mock import MagicMock


class _Ctx:
    triggered_id = None
    triggered = []
    inputs_list = []


ctx = _Ctx()


def stub_ctx(triggered_id=None, value=None):
    ctx.triggered_id = triggered_id
    ctx.triggered = [{"prop_id": "x.n_clicks", "value": value}]


class PreventUpdate(Exception):
    pass


def _passthrough(*a, **k):
    def deco(fn):
        return fn
    return deco


class _Comp:
    def __init__(self, *children, **kw):
        self.children = children[0] if len(children) == 1 else list(children)
        self.kw = kw
        for k, v in kw.items():
            setattr(self, k, v)

    def __repr__(self):
        return f"<{type(self).__name__} {self.kw.get('id', '')}>"


class _NS(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = type(name, (_Comp,), {})
        setattr(self, name, cls)
        return cls


def install():
    if getattr(sys.modules.get("dash"), "_stratabi_stub", False):
        return
    dash = types.ModuleType("dash")
    dash._stratabi_stub = True
    dash.html = _NS("dash.html")
    dash.dcc = _NS("dash.dcc")
    dash.register_page = lambda *a, **k: None
    dash.callback = _passthrough
    dash.clientside_callback = lambda *a, **k: None
    for n in ("Input", "Output", "State", "ClientsideFunction"):
        setattr(dash, n, lambda *a, **k: None)
    dash.MATCH, dash.ALL, dash.ALLSMALLER = "MATCH", "ALL", "ALLSMALLER"
    dash.ctx = ctx
    dash.callback_context = ctx
    dash.no_update = "__no_update__"
    dash.Patch = MagicMock
    dash.get_app = MagicMock()
    exc = types.ModuleType("dash.exceptions")
    exc.PreventUpdate = PreventUpdate
    dash.exceptions = exc
    sys.modules.update({"dash": dash, "dash.html": dash.html, "dash.dcc": dash.dcc,
                        "dash.exceptions": exc})
    sys.modules["dash_bootstrap_components"] = _NS("dash_bootstrap_components")
    for name in ("boto3", "botocore", "botocore.config", "botocore.exceptions",
                 "boto3.dynamodb", "boto3.dynamodb.conditions", "plotly", "plotly.graph_objects",
                 "plotly.io", "plotly.express", "pandas", "awswrangler", "dash_ag_grid",
                 "plotly_resampler", "markdown", "pyarrow", "pyarrow.parquet", "pyarrow.csv", "numpy", "requests", "flask_login", "pyarrow.fs"):
        if name not in sys.modules:
            m = MagicMock()
            m.__name__ = name
            sys.modules[name] = m
    sys.modules["botocore.exceptions"].ClientError = type("ClientError", (Exception,), {})
