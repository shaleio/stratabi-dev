'''
app.py

This file defines the app object and app layout
'''

'''Imports'''
import os
import json
import dash
import flask
import boto3
from dash import html, dcc, Input, Output, State, callback, ctx, no_update, clientside_callback
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
from dash.exceptions import PreventUpdate
from stratabi.components.navbar import navbar
from stratabi.core.registry import *
from stratabi.core.s3_loader import resolve_actor_token
import logging
from dotenv import load_dotenv

# Load AWS creds + STRATABI_* config from a local .env if present (dev convenience).
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Quiet werkzeug's per-request access log (a line per _dash-update-component POST);
# keep WARNING+ so real problems still surface. Override with STRATABI_ACCESS_LOG=1.
if os.getenv("STRATABI_ACCESS_LOG", "").strip().lower() not in ("1", "true", "yes", "on"):
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

logger.info("Starting StrataBI")
logger.info("STRATABI_SYSTEM_BUCKET=%s", os.getenv("STRATABI_SYSTEM_BUCKET"))
logger.info("STRATABI_THEME_PREFIX=%s", os.getenv("STRATABI_THEME_PREFIX"))
logger.info("STRATABI_DASHBOARD_PREFIX=%s", os.getenv("STRATABI_DASHBOARD_PREFIX"))
logger.info("STRATABI_ATHENA_OUTPUT=%s", os.getenv("STRATABI_ATHENA_OUTPUT"))


#dynamo declaration
dynamodb = boto3.resource("dynamodb")

#define server
server = flask.Flask(__name__)

@server.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


'''module_utils'''
def get_module_registry_table():
    table_name = os.getenv("STRATABI_MODULE_REGISTRY_TABLE")
    if not table_name:
        return None

    return dynamodb.Table(table_name)


def scan_app_modules() -> list[dict]:
    table = get_module_registry_table()

    if table is None:
        return []

    items = []
    last_key = None

    while True:
        kwargs = {}

        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        response = table.scan(**kwargs)

        for item in response.get("Items", []):
            module_type = item.get("module_type")

            if module_type in {"app", "multi_page_app"}:
                items.append(item)

        last_key = response.get("LastEvaluatedKey")

        if not last_key:
            break

    items.sort(key=lambda item: str(item.get("label") or item.get("module_id") or "").lower())

    return items

'''App Call'''
# ---------------------------------------------------------------------
# Theme delivery
# ---------------------------------------------------------------------
# The selected theme (a full Bootstrap/Bootswatch stylesheet) is bundled into
# the container image at stratabi/themes/ and served from this app's OWN origin
# at /stratabi-theme.css. Nothing is fetched at runtime -- no S3, no public CDN
# -- so styling works in a fully air-gapped enclave and cannot fail due to
# network/IAM. One image carries every theme; STRATABI_THEME just selects which
# bundled file to serve.
#
# Set STRATABI_THEME_URL to a literal URL (a public S3 object, a CloudFront
# distribution, etc.) to load the theme from there instead, if air-gapping is
# not a concern.
STRATABI_THEME = os.getenv("STRATABI_THEME", "guildmaster")
STRATABI_THEME_URL = os.getenv("STRATABI_THEME_URL", "").strip()
_THEMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")
_theme_css_cache = {}


def _resolve_theme_filename(name):
    # Registry first (handles guildmaster.css vs <name>.min.css), then fall back
    # to whichever bundled file actually exists.
    try:
        with open(os.path.join(_THEMES_DIR, "themes.json"), encoding="utf-8") as f:
            reg = json.load(f)
        fn = reg.get(name)
        if fn and os.path.exists(os.path.join(_THEMES_DIR, fn)):
            return fn
    except Exception:
        pass
    for candidate in (f"{name}.min.css", f"{name}.css"):
        if os.path.exists(os.path.join(_THEMES_DIR, candidate)):
            return candidate
    return f"{name}.min.css"


def _load_theme_css(name):
    if name in _theme_css_cache:
        return _theme_css_cache[name]
    css = ""
    try:
        path = os.path.join(_THEMES_DIR, _resolve_theme_filename(name))
        with open(path, encoding="utf-8", errors="replace") as f:
            css = f.read()
    except Exception as e:
        logger.warning("Theme load failed for %s: %s", name, e)
    _theme_css_cache[name] = css
    return css


@server.route("/stratabi-theme.css")
def stratabi_theme_css():
    return flask.Response(_load_theme_css(STRATABI_THEME), mimetype="text/css")


THEME_STYLESHEET = STRATABI_THEME_URL or "/stratabi-theme.css"

# Monaco editor uses its built-in light ("vs") / dark ("vs-dark") themes.
# Derive from the app theme so a dark Bootswatch theme gets a dark editor;
# STRATABI_EDITOR_THEME ("vs" | "vs-dark") forces it explicitly.
_DARK_THEMES = {"guildmaster", "cyborg", "darkly", "slate", "solar", "superhero", "vapor"}
STRATABI_EDITOR_THEME = os.getenv("STRATABI_EDITOR_THEME", "").strip() or (
    "vs-dark" if STRATABI_THEME in _DARK_THEMES else "vs"
)


app = dash.Dash(
    __name__,
    prevent_initial_callbacks = "initial_duplicate",
    use_pages = True,
    # THEME_STYLESHEET first (Bootstrap). dag.themes load the legacy AG Grid CSS
    # (BASE + ALPINE => ag-theme-alpine + ag-theme-alpine-dark) needed by v33
    # legacy themes (see blocks/table.py theme:"legacy").
    external_stylesheets=[THEME_STYLESHEET, dag.themes.BASE, dag.themes.ALPINE],
    suppress_callback_exceptions=True,
    update_title="Building...",
    server = server
)
app.title = "ShaleIO StrataBI"

'''App Layout'''
url_bar_navbar_content = html.Div([
    dcc.Location(id='url'),
    html.Div(
        children=[
            navbar
        ]
    ),
    html.Div(id="bootstrap-vars", style={"display": "none"})
])

app.layout = html.Div([
    url_bar_navbar_content,
    dash.page_container,
    html.Div(id="stratabi-editor-theme",
             **{"data-theme": STRATABI_EDITOR_THEME},
             style={"display": "none"}),
    dcc.Store(id="dashboard-input-store"),    # Stores input tile values (future)
    dcc.Store(id="dashboard-status-store"),   # Stores Dynamo/Lambda statuses
    dcc.Store(id="dashboard-trigger-store"),  # Stores most recent input tile triggered
    dcc.Store(id="dashboard-run-store"),      # Per-tile run (▷) button target; separate from the trigger bus
    dcc.Store(id="dashboard-selector-store"),
    dcc.Store(id="current-user-id-store"),
    dcc.Store(id="active-dashboard-key-store"),  
    dcc.Store(id="module-active-page-store"),
    dcc.Store(id="builder-selected-module-context-store", data=[]),
    dcc.Store(id="dashboard-config-store"),   # Stores parsed dashboard JSON
    dcc.Store(id="dashboard-refresh-store"),
    dcc.Store(id="dashboard-runtime-session-store", storage_type="session"),
    dcc.Store(id="tile-runtime-store", storage_type="session"),
    dcc.Interval(
        id="dashboard-interval",
        interval=60_000,
        disabled=True,
        n_intervals=0,
    ),
    dbc.Modal(
    [
        dbc.ModalHeader(dbc.ModalTitle("Apps")),
        dbc.ModalBody(html.Div(id="apps-modal-body")),
    ],
    id="apps-modal",
    is_open=False,
    size="lg",
    ),
])

@callback(
    Output("apps-modal", "is_open"),
    Output("apps-modal-body", "children"),
    Input("navbar-apps-button", "n_clicks"),
    Input("url", "pathname"),
    State("apps-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_apps_modal(n_clicks, pathname, is_open):
    if ctx.triggered_id == "url":
        return False, no_update

    if not n_clicks:
        raise PreventUpdate

    modules = scan_app_modules()

    if not modules:
        body = dbc.Alert(
            "No apps found in the module registry.",
            color="warning",
            className="mb-0",
        )
        return True, body

    rows = []

    for module in modules:
        module_id = module.get("module_id")
        label = module.get("label") or module_id
        description = module.get("description", "")
        module_type = module.get("module_type", "app")
        version = module.get("version", "")

        if not module_id:
            continue

        rows.append(
            dbc.ListGroupItem(
                dcc.Link(
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span(label, className="fw-bold"),
                                    html.Span(
                                        f" {version}" if version else "",
                                        className="text-muted small ms-2",
                                    ),
                                ]
                            ),
                            html.Div(
                                description,
                                className="small text-muted",
                            ) if description else None,
                            html.Div(
                                module_type,
                                className="small text-info mt-1",
                            ),
                        ]
                    ),
                    href=f"/dashboard/apps/{module_id}",
                    className="text-decoration-none",
                ),
                action=True,
            )
        )

    body = dbc.ListGroup(rows) if rows else dbc.Alert(
        "Module registry returned no valid app modules.",
        color="warning",
        className="mb-0",
    )

    return True, body

    
@callback(
    Output("current-user-id-store", "data"),
    Input("url", "pathname"),
)
def hydrate_current_user(_):
    return resolve_actor_token() or "anonymous"


clientside_callback(
    """
    function(pathname, currentSession) {
        if (currentSession && currentSession.runtime_session_id) {
            return currentSession;
        }

        const randomPart = (
            window.crypto && window.crypto.randomUUID
        )
            ? window.crypto.randomUUID()
            : Math.random().toString(36).slice(2) + Date.now().toString(36);

        return {
            runtime_session_id: randomPart,
            created_at: new Date().toISOString(),
            pathname: pathname
        };
    }
    """,
    Output("dashboard-runtime-session-store", "data"),
    Input("url", "pathname"),
    State("dashboard-runtime-session-store", "data"),
)

if __name__=='__main__':
    app.run(host="0.0.0.0", port=8050, debug=True)