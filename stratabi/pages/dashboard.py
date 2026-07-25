import dash
from dash import html, dcc, register_page, Input, Output, State, MATCH, ALL, ctx, callback
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import Patch
import os
import boto3

from ..core.s3_loader import (
    dashboard_id_from_value,
    load_dashboard_json,
    list_dashboards_from_s3,
    load_module_json,
    record_dashboard_recent,
    parse_s3_location,
    s3_uri,
)
from ..core.runner import execute_tile
from ..core.renderer import render_block
from ..core.status_store import get_dashboard_statuses
import time
from datetime import date
from copy import deepcopy
from ..core.source_resolver import SourceResolver


register_page(__name__, path="/dashboard")
source_resolver = SourceResolver()
ACTIVE_TILE_STATUSES = {"REQUESTED", "QUEUED", "PENDING", "RUNNING", "PROCESSING"}
TERMINAL_TILE_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}
FAILED_TILE_STATUSES = {"FAILED", "CANCELLED"}

# Default look for generated/unspecified tile cards.
DEFAULT_CARD_COLOR = "primary"
DEFAULT_CARD_OUTLINE = True
# Solid (non-outline) Bootstrap fills that are light and need DARK text for contrast.
_LIGHT_FILL_COLORS = {"light", "warning", "info"}


def status_text_class(tile: dict, semantic: str) -> str:
    """Choose a text-* class for an in-card status message that stays visible.

    Outline cards (incl. the default) have a transparent fill, so the message's
    semantic color (info for 'Processing', danger for errors, etc.) reads fine
    against the page background. On a SOLID card whose fill equals the message's
    own semantic color the text would be invisible (e.g. an info message on an
    info card), so fall back to a contrasting color.
    """
    card = tile.get("card") or {}
    fill = card.get("color", DEFAULT_CARD_COLOR)
    outline = card.get("outline", DEFAULT_CARD_OUTLINE)
    if outline:
        return f"text-{semantic}"
    if fill == semantic:
        return "text-dark" if fill in _LIGHT_FILL_COLORS else "text-white"
    return f"text-{semantic}"


s3 = boto3.client("s3")

# -----------------------------------------------
# HELPERS
# -----------------------------------------------
def presign_s3_location(
    location: str,
    bucket: str | None = None,
    filename: str | None = None,
    expires_in: int = 3600,
) -> str | None:
    resolved_bucket, key = parse_s3_location(location, bucket)

    filename = filename or os.path.basename(key) or "artifact"

    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": resolved_bucket,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=expires_in,
    )

def artifact_download_enabled(tile: dict) -> bool:
    return bool((tile.get("artifact") or {}).get("download", False))


def presign_artifact_url(status_or_context: dict, filename: str | None = None, expires_in: int = 3600) -> str | None:
    bucket = status_or_context.get("system_bucket")
    key = status_or_context.get("result_s3_key")

    if not bucket or not key:
        return None

    filename = filename or os.path.basename(key) or "artifact"

    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=expires_in,
    )

def get_tile_artifact_presigned_url(tile, dashboard_key, runtime_session_id):
    exec_cfg = tile.get("exec") or {}
    artifact_cfg = tile.get("artifact") or {}

    if exec_cfg.get("type") == "cache":
        location = exec_cfg.get("cache_s3_uri")
        filename = artifact_cfg.get("filename")
        return presign_s3_location(location, filename=filename)


def get_tile_by_id(config, tile_id):
    if not config:
        return None

    return next(
        (tile for tile in config.get("layout", []) if tile.get("id") == tile_id),
        None
    )

def patch_tile_status(tile_id: str, status: str):
    patched = Patch()
    patched[tile_id] = status
    return patched

def parse_app_module_id(pathname: str) -> str | None:
    prefix = "/dashboard/apps/"
    if not pathname or not pathname.startswith(prefix):
        return None

    module_id = pathname.removeprefix(prefix).strip("/")
    return module_id or None


def is_app_route(pathname: str) -> bool:
    return parse_app_module_id(pathname) is not None


def build_page_config(module: dict, page: dict) -> dict:
    page_config_id = f"{module.get('module_id')}::{page.get('page_id')}"
    return {
        "id": page_config_id,
        "_dashboard_key": page_config_id,
        "name": page.get("label") or module.get("label"),
        "layout": page.get("layout", []),
        "settings": module.get("settings", {}),
    }


def resolve_sources_in_config(value):
    """
    Recursively resolve {"?source": "..."} anywhere in the dashboard config.

    MVP behavior:
      - If a dict is exactly/primarily a source ref, replace it with the resolved value.
      - Otherwise recursively resolve children.
    """
    if source_resolver.is_source_ref(value):
        return source_resolver.resolve_value(value)

    if isinstance(value, dict):
        return {
            key: resolve_sources_in_config(child)
            for key, child in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_sources_in_config(item)
            for item in value
        ]

    return value


def tile_is_async(tile: dict) -> bool:
    exec_cfg = tile.get("exec") or {}
    exec_type = exec_cfg.get("type")

    if exec_type == "lambda":
        return True

    if exec_type == "athena" and exec_cfg.get("async", False):
        return True

    return False

def get_tile_client_status(tile_status: str | None) -> str | None:
    return tile_status

def should_check_tile(tile, trigger, tile_status):
    if trigger != "dashboard-interval":
        return False

    if not tile_is_async(tile):
        return False

    return tile_status in ACTIVE_TILE_STATUSES

def should_execute_tile(tile, trigger, trigger_data=None, tile_status=None, run_data=None):
    mode = tile.get("load", {}).get("mode", "load_once")

    client_status = tile_status
    triggered_by = tile.get("triggered_by", []) or []

    latest_trigger_tile_id = None

    if isinstance(trigger_data, dict):
        latest_trigger_tile_id = trigger_data.get("trigger_tile_id")

    # If async tile is already running, do not create new work.
    # Polling is handled by should_check_tile().
    if client_status in ACTIVE_TILE_STATUSES:
        return False

    # Per-tile run button (▷) writes a dedicated run store carrying target_tile_id.
    # Kept separate from dashboard-trigger-store so the trigger bus stays dedicated
    # to input changes and full-page refresh.
    if trigger == "dashboard-run-store":
        return isinstance(run_data, dict) and run_data.get("target_tile_id") == tile.get("id")

    # If tile already succeeded, load_once should not execute again unless
    # there is an explicit refresh/trigger policy that permits it.
    if client_status == "SUCCEEDED" and mode == "load_once":
        if trigger == "dashboard-refresh-store":
            return False
        if trigger == "dashboard-interval":
            return False

    # Initial dashboard load.
    # If previous client status was FAILED, allow retry on reload/config load.
    if trigger in (None, "dashboard-config-store"):
        if mode == "manual":
            return False
        if client_status in FAILED_TILE_STATUSES:
            return True
        if client_status == "SUCCEEDED":
            return True  # rehydrate existing result, not start new work
        return True

    # Dependency/input trigger.
    if trigger == "dashboard-trigger-store":
        if triggered_by and latest_trigger_tile_id:
            return latest_trigger_tile_id in triggered_by
        return mode in {"always", "input"}

    # Global refresh.
    # This should retry FAILED load_once tiles, but not rerun already SUCCEEDED load_once tiles.
    if trigger == "dashboard-refresh-store":
        if client_status in ACTIVE_TILE_STATUSES:
            return False
        if client_status == "SUCCEEDED" and mode == "load_once":
            return False
        if client_status in FAILED_TILE_STATUSES:
            return mode in {"manual", "interval", "input", "load_once", "always"}
        return mode in {"always", "manual", "interval", "input"}

    # Interval creates new work only for always/interval.
    # Existing RUNNING async work is handled by should_check_tile().
    if trigger == "dashboard-interval":
        if client_status in ACTIVE_TILE_STATUSES:
            return False
        if client_status == "SUCCEEDED":
            return False
        if client_status in FAILED_TILE_STATUSES:
            return False
        return mode in {"always", "interval"}

    if mode == "always":
        return client_status not in ACTIVE_TILE_STATUSES

    if mode == "load_once":
        return client_status in FAILED_TILE_STATUSES

    return False

def load_indicator(tile: dict, dashboard_polling_enabled: bool) -> str:
    load_cfg = tile.get("load", {}) or {}
    explicit = load_cfg.get("indicator")

    # "auto" means use StrataBI's default decision tree.
    if explicit and explicit != "auto":
        return explicit

    exec_cfg = tile.get("exec") or {}
    exec_type = exec_cfg.get("type")

    # Async tiles already render status messages inside tile content.
    if exec_type == "lambda":
        return "status"

    if exec_type == "athena" and exec_cfg.get("async", False):
        return "status"

    # Sync Athena + dashboard interval is the known dcc.Loading flicker case.
    if exec_type == "athena" and dashboard_polling_enabled:
        return "none"

    # Cache/static generally don't need a spinner when polling is enabled.
    if exec_type in {"cache", None} and dashboard_polling_enabled:
        return "none"

    return "spinner"


def hidden_module_controls():
    return html.Div(
        [
            dbc.Tabs(id="module-tabs", active_tab=None, children=[]),
            dbc.Pagination(id="module-pagination", max_value=1, active_page=1),
            dbc.Button("Previous", id="module-prev-btn", n_clicks=0),
            dbc.Button("Next", id="module-next-btn", n_clicks=0),
        ],
        style={"display": "none"},
    )

# -----------------------------------------------
# TILE RENDERING
# -----------------------------------------------
def render_tile_card(tile, polling_enabled=False):
    tile_id = tile.get("id")

    if not tile_id:
        return dbc.Alert("Tile missing id.", color="danger")

    header = None
    if tile.get("title") and tile.get("card", {}).get("show_header", True):
        header = dbc.CardHeader(tile["title"])

    indicator = load_indicator(tile, dashboard_polling_enabled=polling_enabled)

    tile_content = html.Div(
        id={"type": "tile-content", "tile_id": tile_id}
    )

    tile_status_store = dcc.Store(
        id={"type": "tile-status-store", "tile_id": tile_id},
        storage_type="session",
    )

    if indicator == "loading":
        body_child = dcc.Loading(
            id={"type": "tile-loading", "tile_id": tile_id},
            type="default",
            children=tile_content,
        )
    elif indicator == "spinner":
        _card = tile.get("card", {}) or {}
        _solid_primary = _card.get("color", DEFAULT_CARD_COLOR) == "primary" and not _card.get("outline", DEFAULT_CARD_OUTLINE)
        spinner_color = "secondary" if _solid_primary else "primary"
        body_child = dbc.Spinner(
            id={"type": "tile-loading", "tile_id": tile_id},
            color=spinner_color,
            children=tile_content,
        )
    else:
        body_child = tile_content

    # Per-tile control buttons (run ▷ and/or artifact download ⤓), right-aligned.
    tile_controls = tile.get("controls") or {}
    artifact_cfg = tile.get("artifact") or {}

    # By default the run/download buttons appear on tiles that actually execute
    # (have an exec) and aren't input/control blocks — those are the only tiles
    # where re-running or downloading a result is meaningful. Static, markdown,
    # and input tiles get no buttons unless explicitly enabled. Explicit
    # controls.run_button / artifact.download always override this default.
    _block_type = (tile.get("block") or {}).get("type")
    _is_control_block = _block_type in {"input_select", "input_range", "dropdown"}
    _buttons_default = bool(tile.get("exec")) and not _is_control_block

    control_buttons = []

    if tile_controls.get("run_button", _buttons_default):
        control_buttons.append(
            dbc.Button(
                "▷",
                id={"type": "tile-run", "tile_id": tile_id},
                color="primary",
                size="sm",
                outline=True,
                n_clicks=0,
                title="Run tile",
                className="me-1",
            )
        )

    if artifact_cfg.get("download", _buttons_default):
        control_buttons.append(
            dbc.Button(
                artifact_cfg.get("label", "⤓"),
                id={"type": "tile-artifact-download", "tile_id": tile_id},
                color="secondary",
                size="sm",
                outline=True,
                n_clicks=0,
                title="Download artifact",
            )
        )

    controls_row = None
    if control_buttons:
        controls_row = html.Div(
            control_buttons,
            className="mt-2 d-flex justify-content-end gap-1",
        )

    body_children = [
        tile_status_store,
        body_child,
    ]

    if controls_row:
        body_children.append(controls_row)

    return dbc.Card(
        [
            header,
            dbc.CardBody(body_children),
        ],
        color=tile.get("card", {}).get("color", DEFAULT_CARD_COLOR),
        outline=tile.get("card", {}).get("outline", DEFAULT_CARD_OUTLINE),
        className="mb-3 h-100",
    )


def build_dashboard_grid(dashboard_config):
    tiles_by_row = {}
    settings = dashboard_config.get("settings")
    if settings:
        polling_enabled = settings.get("interval_enabled", False)
    else:
        polling_enabled = False

    for tile in dashboard_config.get("layout", []):
        position = tile.get("position", {})
        row_num = position.get("row", 0)
        tiles_by_row.setdefault(row_num, []).append(tile)

    rows = []
    for row_num in sorted(tiles_by_row.keys()):
        row_tiles = sorted(
            tiles_by_row[row_num],
            key=lambda tile: tile.get("position", {}).get("order", 0)
        )

        cols = [
            dbc.Col(
                render_tile_card(tile, polling_enabled=polling_enabled),
                width=tile.get("position", {}).get("width", 12)
            )
            for tile in row_tiles
        ]

        rows.append(dbc.Row(cols, className="mb-3"))

    return rows

# -----------------------------------------------
# Module Controls
# -----------------------------------------------

def render_module_controls(module: dict, active_page_id: str):
    pages = module.get("pages", [])
    navigation_type = module.get("navigation_type")
    label = module.get("label", "App")

    active_index = next(
        (i for i, p in enumerate(pages) if p.get("page_id") == active_page_id),
        0,
    )

    return html.Div(
        [
            html.H4(label),

            html.Div(
                dbc.Tabs(
                    id="module-tabs",
                    active_tab=active_page_id,
                    children=[
                        dbc.Tab(label=p.get("label"), tab_id=p.get("page_id"))
                        for p in pages
                    ],
                ),
                style={} if navigation_type == "tabs" else {"display": "none"},
            ),

            html.Div(
                dbc.Pagination(
                    id="module-pagination",
                    max_value=max(len(pages), 1),
                    active_page=active_index + 1,
                    first_last=True,
                    previous_next=True,
                ),
                style={} if navigation_type == "pagination" else {"display": "none"},
            ),

            html.Div(
                [
                    dbc.Button(
                        "Previous",
                        id="module-prev-btn",
                        color="secondary",
                        n_clicks=0,
                        disabled=active_index == 0,
                    ),
                    html.Span(
                        f" {active_index + 1} / {len(pages)} ",
                        className="mx-3 text-muted",
                    ),
                    dbc.Button(
                        "Next",
                        id="module-next-btn",
                        color="secondary",
                        n_clicks=0,
                        disabled=active_index >= len(pages) - 1,
                    ),
                ],
                style={} if navigation_type == "next_previous" else {"display": "none"},
            ),
        ]
    )

# -----------------------------------------------
# LAYOUT
# -----------------------------------------------
def layout():
    return html.Div(
        className="p-3",
        children=[
            # ---------- TOP CONTROL BAR ----------
            html.Div(
                id="dashboard-controls-row",
                children=[
                    dbc.Row(
                        [
                        dbc.Col(
                            [
                                dcc.DatePickerRange(
                                    id="dashboard-date-picker-range",
                                    initial_visible_month=date.today(),
                                    className="dash-date-range",
                                ),
                                dcc.Dropdown(
                                    id="dashboard-selector",
                                    options=[],
                                    clearable=False,
                                    className="dash-dropdown",
                                ),
                            ],
                            width=4,
                        ),
                        dbc.Col(
                            dbc.Button(
                                "Refresh",
                                id="dashboard-refresh-btn",
                                color="primary",
                                n_clicks=0,
                            ),
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Button(
                                "Status",
                                id="dashboard-status-btn",
                                color="secondary",
                                n_clicks=0,
                            ),
                            width="auto",
                        ),
                        dbc.Col(
                            html.Div(id="dashboard-status-text", className="text-muted"),
                            width=True,
                        ),
                    ],
                    className="align-items-center mb-4",
                    ),

                ]
            ),
            html.Div(
                id="module-controls-row",
                className="mb-4",
                children=hidden_module_controls(),
            ),
            # ---------- DASHBOARD GRID ----------
            html.Div(id="dashboard-grid"),

            # ---------- STATUS MODAL ----------
            dbc.Modal(
                [
                    dbc.ModalHeader("Tile Execution Status"),
                    dbc.ModalBody(
                        html.Div(id="dashboard-status-modal-content")
                    ),
                    dbc.ModalFooter(
                        dbc.Button("Close", id="dashboard-status-close", className="ms-auto")
                    ),
                ],
                id="dashboard-status-modal",
                is_open=False,
                size="xl",
            ),

            # ---------- DOWNLOAD MODAL ----------
            dbc.Modal(
                [
                    dbc.ModalHeader("Artifact Download"),
                    dbc.ModalBody(html.Div(id="artifact-download-modal-content")),
                    dbc.ModalFooter(
                        dbc.Button("Close", id="artifact-download-close", className="ms-auto")
                    ),
                ],
                id="artifact-download-modal",
                is_open=False,
            )
        ],
    )

# -----------------------------------------------
# Status Modal Rows
# -----------------------------------------------

def render_status_rows(statuses):
    if not statuses:
        return html.Div("No tile statuses found.", className="text-muted")

    rows = []

    for tile_id, status_data in statuses.items():
        if isinstance(status_data, dict):
            status = status_data.get("status", "UNKNOWN")
            message = status_data.get("message", "")
            updated_at = status_data.get("updated_at", "")
            run_id = status_data.get("run_id", "")
            exec_type = status_data.get("exec_type", "")
        else:
            status = str(status_data)
            message = ""
            updated_at = ""
            run_id = ""
            exec_type = ""

        rows.append(
            html.Tr(
                [
                    html.Td(tile_id),
                    html.Td(status),
                    html.Td(exec_type),
                    html.Td(updated_at),
                    html.Td(message),
                    html.Td(run_id[:10] + "…" if run_id else ""),
                ]
            )
        )

    return dbc.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Tile"),
                        html.Th("Status"),
                        html.Th("Exec"),
                        html.Th("Updated"),
                        html.Th("Message"),
                        html.Th("Run"),
                    ]
                )
            ),
            html.Tbody(rows),
        ],
        bordered=True,
        hover=True,
        responsive=True,
        striped=True,
        color="info",
        className="mb-0",
    )


# -----------------------------------------------
# DASHBOARD SELECTION
# -----------------------------------------------

@callback(
    Output("dashboard-selector-store", "data"),
    Input("dashboard-selector", "value"),
    prevent_initial_call=True,
)
def sync_dashboard_selector_store(dashboard_key):
    return dashboard_key

@callback(
    Output("dashboard-config-store", "data"),
    Output("module-controls-row", "children"),
    Input("url", "pathname"),
    Input("dashboard-selector-store", "data"),
    Input("module-active-page-store", "data"),
    State("current-user-id-store", "data"),
)
def load_dashboard_config(pathname, dashboard_key, active_page_id, user_id):
    module_id = parse_app_module_id(pathname)

    if module_id:
        try:
            module = load_module_json(module_id)
        except Exception as e:
            return {}, dbc.Alert(f"Failed to load module `{module_id}`: {e}", color="danger")

        module_type = module.get("module_type")
        pages = module.get("pages", [])

        if module_type != "multi_page_app":
            module_config_id = module.get("module_id") or module_id
            return (
                {
                    "id": module_config_id,
                    "_dashboard_key": module_config_id,
                    "name": module.get("label"),
                    "layout": module.get("layout", []),
                    "settings": module.get("settings", {}),
                },
                html.H5(module.get("label", module_id)),
            )

        if not pages:
            return {}, dbc.Alert("Module has no pages.", color="warning")

        if not active_page_id:
            active_page_id = module.get("overrides", {}).get("default_page") or pages[0].get("page_id")

        page = next((p for p in pages if p.get("page_id") == active_page_id), pages[0])
        controls = render_module_controls(module, active_page_id)

        return resolve_sources_in_config(build_page_config(module, page)), controls

    if not dashboard_key:
        raise PreventUpdate

    config = load_dashboard_json(dashboard_key)
    config = deepcopy(config)
    config["_dashboard_key"] = dashboard_key

    try:
        record_dashboard_recent(
            user_id=user_id,
            dashboard_key=dashboard_key,
            label=config.get("name") or config.get("label"),
        )
    except Exception:
        pass

    return resolve_sources_in_config(config), hidden_module_controls()

@callback(
    Output("dashboard-grid", "children"),
    Input("dashboard-config-store", "data"),
)
def render_dashboard_grid(config):
    if not config:
        return html.Div("Select a dashboard.", className="text-muted")

    try:
        return build_dashboard_grid(config)
    except Exception as e:
        return html.Div(
            [
                html.Div("Dashboard grid render failed.", className="text-danger fw-bold"),
                html.Pre(str(e), className="small text-danger"),
            ]
        )
# -----------------------------------------------
# TILE UPDATE ENGINE (THIN)
# -----------------------------------------------
@callback(
    Output("dashboard-refresh-store", "data"),
    Input("dashboard-refresh-btn", "n_clicks"),
    State("current-user-id-store", "data"),
    State("active-dashboard-key-store", "data"),
    prevent_initial_call=True,
)
def sync_dashboard_refresh_store(n_clicks, user_id, dashboard_key):
    if not n_clicks:
        raise PreventUpdate

    return {
        "event": "manual_refresh",
        "n_clicks": n_clicks,
        "ts": time.time(),
        "user_id": user_id,
        "dashboard_key": dashboard_key,
    }

@callback(
    Output({"type": "tile-content", "tile_id": MATCH}, "children"),
    Output({"type": "tile-status-store", "tile_id": MATCH}, "data"),
    Input("dashboard-config-store", "data"),
    Input("dashboard-refresh-store", "data"),
    Input("dashboard-interval", "n_intervals"),
    Input("dashboard-trigger-store", "data"),
    Input("dashboard-run-store", "data"),
    State("dashboard-input-store", "data"),
    State("active-dashboard-key-store", "data"),
    State("dashboard-runtime-session-store", "data"),
    State({"type": "tile-status-store", "tile_id": MATCH}, "data"),
    State({"type": "tile-content", "tile_id": MATCH}, "id")
)
def update_tile(config, _refresh, _tick, trigger_data, run_data, inputs, active_dashboard, runtime_session, tile_status_store, tile_component_id):
    if not config:
        return html.Div("Dashboard config not loaded", className="text-muted"), dash.no_update
    
    runtime_session_id = None
    if isinstance(runtime_session, dict):
        runtime_session_id = runtime_session.get("runtime_session_id")

    tile = get_tile_by_id(config, tile_component_id["tile_id"])

    if not tile:
        return html.Div("Tile not found", className="text-danger"), dash.no_update

    _exec = tile.get("exec") or {}

    trigger = ctx.triggered_id

    should_start_or_reload = should_execute_tile(
        tile,
        trigger,
        trigger_data,
        tile_status=tile_status_store,
        run_data=run_data,
    )
    should_poll_existing = should_check_tile(tile, trigger, tile_status_store)

    if not should_start_or_reload and not should_poll_existing:
        return dash.no_update, dash.no_update
    
    dashboard_key = config.get("_dashboard_key") or active_dashboard


    result = execute_tile(
        tile,
        inputs or {},
        dashboard_key=dashboard_key,
        runtime_session_id=runtime_session_id,
    )

    if isinstance(result, dict):
        status = str(result.get("status", "RUNNING")).upper()

        if status in ACTIVE_TILE_STATUSES:
            return html.Div("Processing…", className=status_text_class(tile, "info")), status

        if status == "FAILED":
            return html.Div(
                result.get("message", "Tile execution failed."),
                className=status_text_class(tile, "danger"),
            ), status

        if status == "CANCELLED":
            return html.Div("Tile execution cancelled.", className=status_text_class(tile, "muted")), status

        
    block = tile.get("block")

    if not block:
        return html.Div("Tile missing block config.", className=status_text_class(tile, "danger")), dash.no_update
    
    try:
        rendered = render_block(block, result, tile_id=tile.get("id"))

        if tile_is_async(tile):
            return rendered, "SUCCEEDED"

        return rendered, dash.no_update

    except Exception as e:
        error = html.Div(
            [
                html.Div("Block render failed.", className=status_text_class(tile, "danger") + " fw-bold"),
                html.Pre(str(e), className="small " + status_text_class(tile, "danger")),
            ]
        )

        if tile_is_async(tile):
            return error, "FAILED"

        return error, dash.no_update


# -----------------------------------------------
# INPUT STATE
# -----------------------------------------------
@callback(
    Output("dashboard-input-store", "data"),
    Output("dashboard-trigger-store", "data"),
    Input({"type": "tile-input", "tile_id": ALL}, "value"),
    State({"type": "tile-input", "tile_id": ALL}, "id"),
    State("current-user-id-store", "data"),
    State("active-dashboard-key-store", "data"),
    prevent_initial_call=True,
)
def store_inputs(values, ids, user_id, dashboard_key):
    input_values = {}

    for value, ident in zip(values, ids):
        input_key = ident.get("input_id") or ident["tile_id"]
        input_values[input_key] = value

    data = {
        "_meta": {
            "user_id": user_id,
            "dashboard_key": dashboard_key,
        },
        "inputs": input_values,
    }

    trigger_id = ctx.triggered_id

    trigger_store = None
    if isinstance(trigger_id, dict):
        trigger_store = {
            "trigger_type": "input",
            "trigger_tile_id": trigger_id.get("tile_id"),
            "input_id": trigger_id.get("input_id"),
            "ts": time.time(),
            "user_id": user_id,
            "dashboard_key": dashboard_key,
        }

    return data, trigger_store

# -----------------------------------------------
# TILE RUN BUTTON (per-tile ▷ trigger)
# -----------------------------------------------
@callback(
    Output("dashboard-run-store", "data"),
    Input({"type": "tile-run", "tile_id": ALL}, "n_clicks"),
    State("current-user-id-store", "data"),
    State("active-dashboard-key-store", "data"),
    prevent_initial_call=True,
)
def run_tile_button(n_clicks_list, user_id, dashboard_key):
    triggered = ctx.triggered_id

    # Ignore component-registration fires and zero-click activations.
    if not isinstance(triggered, dict) or not any(n or 0 for n in (n_clicks_list or [])):
        return dash.no_update

    return {
        "target_tile_id": triggered.get("tile_id"),
        "ts": time.time(),
        "user_id": user_id,
        "dashboard_key": dashboard_key,
    }


# -----------------------------------------------
# STATUS MODAL
# -----------------------------------------------
@callback(
    Output("dashboard-status-modal", "is_open"),
    Output("dashboard-status-modal-content", "children"),
    Input("dashboard-status-btn", "n_clicks"),
    Input("dashboard-status-close", "n_clicks"),
    State("dashboard-status-modal", "is_open"),
    State("dashboard-status-store", "data"),
    prevent_initial_call=True,
)
def toggle_status_modal(btn, close, is_open, statuses):
    if ctx.triggered_id == "dashboard-status-btn":
        return True, render_status_rows(statuses)

    if ctx.triggered_id == "dashboard-status-close":
        return False, dash.no_update

    return is_open, dash.no_update


# -----------------------------------------------
# INTERVAL CONFIG
# -----------------------------------------------
@callback(
    Output("dashboard-interval", "interval"),
    Output("dashboard-interval", "disabled"),
    Input("dashboard-config-store", "data"),
)
def configure_interval(config):
    if not config:
        return dash.no_update, True

    settings = config.get("settings", {})
    return (
        settings.get("interval_ms", 60_000),
        not settings.get("interval_enabled", False),
    )

# -----------------------------------------------
# Populate Dropdown
# -----------------------------------------------

@callback(
    Output("dashboard-selector", "options"),
    Output("dashboard-selector", "value"),
    Input("dashboard-selector", "id"),
    Input("current-user-id-store", "data"),
    Input("dashboard-date-picker-range", "start_date"),
    Input("dashboard-date-picker-range", "end_date"),
    State("dashboard-selector", "value"),
    prevent_initial_call=False,
)
def populate_dashboard_selector(_, user_id, start_date, end_date, current_value):
    options = list_dashboards_from_s3(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    if not options:
        return [], None

    values = {opt["value"] for opt in options}

    if current_value in values:
        return options, current_value

    default_value = next(
        (
            opt["value"]
            for opt in options
            if dashboard_id_from_value(opt["value"]) == "default"
        ),
        None,
    )

    if default_value:
        return options, default_value

    return options, options[0]["value"]

# -----------------------------------------------
# Store Updates
# -----------------------------------------------

@callback(
    Output("dashboard-status-store", "data"),
    Input("dashboard-interval", "n_intervals"),
    Input("dashboard-refresh-store", "data"),
    Input("dashboard-config-store", "data"),
    State("dashboard-runtime-session-store", "data")
)
def poll_dashboard_statuses(_tick, _refresh, config, runtime_session):
    if not config:
        raise PreventUpdate
    
    runtime_session_id = None
    if isinstance(runtime_session, dict):
        runtime_session_id = runtime_session.get("runtime_session_id")

    return get_dashboard_statuses(config, runtime_session_id=runtime_session_id)


@callback(
    Output("active-dashboard-key-store", "data", allow_duplicate=True),
    Input("url", "pathname"),
    Input("dashboard-selector-store", "data"),
    prevent_initial_call=True,
)
def sync_active_dashboard(pathname, dashboard_key):
    if pathname and pathname.startswith("/dashboard"):
        if is_app_route(pathname):
            return None
    else:
        return dash.no_update

    return dashboard_key


# -----------------------------------------------
# DASHBOARD CONTROLS
# -----------------------------------------------
@callback(
    Output("dashboard-controls-row", "hidden"),
    Input("url", "pathname"),
)
def toggle_dashboard_controls(pathname):
    if pathname and pathname.startswith("/dashboard"):
        if is_app_route(pathname):
            return True
        else:
            return False
    return dash.no_update

@callback(
    Output("module-active-page-store", "data"),
    Input("url", "pathname"),
    Input("module-tabs", "active_tab"),
    Input("module-pagination", "active_page"),
    Input("module-prev-btn", "n_clicks"),
    Input("module-next-btn", "n_clicks"),
    State("module-active-page-store", "data"),
    prevent_initial_call=True,
)
def update_module_page(pathname, active_tab, active_page, prev_clicks, next_clicks, current_page_id):
    module_id = parse_app_module_id(pathname)
    if not module_id:
        return None

    module = load_module_json(module_id)
    pages = module.get("pages", [])
    if not pages:
        return None

    trigger = ctx.triggered_id

    if trigger == "module-tabs":
        return active_tab

    if trigger == "module-pagination":
        index = max(0, int(active_page or 1) - 1)
        return pages[index].get("page_id")

    current_index = next(
        (i for i, p in enumerate(pages) if p.get("page_id") == current_page_id),
        0,
    )

    if trigger == "module-prev-btn":
        return pages[max(0, current_index - 1)].get("page_id")

    if trigger == "module-next-btn":
        return pages[min(len(pages) - 1, current_index + 1)].get("page_id")

    return current_page_id or pages[0].get("page_id")


@callback(
    Output("artifact-download-modal", "is_open"),
    Output("artifact-download-modal-content", "children"),
    Input({"type": "tile-artifact-download", "tile_id": ALL}, "n_clicks"),
    State({"type": "tile-artifact-download", "tile_id": ALL}, "id"),
    State("dashboard-config-store", "data"),
    State("active-dashboard-key-store", "data"),
    State("dashboard-runtime-session-store", "data"),
    prevent_initial_call=True,
)
def download_tile_artifact(n_clicks_list, ids, config, active_dashboard, runtime_session):
    trigger_id = ctx.triggered_id

    if not isinstance(trigger_id, dict):
        raise PreventUpdate

    # Pattern-matched buttons also fire when first rendered (n_clicks initialises
    # 0 -> set), which would pop the modal on page load. Only proceed on a real
    # click (the triggering input's value must be a positive click count).
    triggered = ctx.triggered or []
    if not triggered or not triggered[0].get("value"):
        raise PreventUpdate

    tile_id = trigger_id.get("tile_id")
    if not tile_id:
        raise PreventUpdate

    tile = get_tile_by_id(config, tile_id)
    if not tile:
        return True, html.Div("Tile not found.", className="text-danger")


    # call helper that looks up latest/expected artifact and presigns it
    url = get_tile_artifact_presigned_url(
        tile=tile,
        dashboard_key=config.get("_dashboard_key") or active_dashboard,
        runtime_session_id=(runtime_session or {}).get("runtime_session_id"),
    )

    if not url:
        return True, html.Div(
            "No downloadable artifact found for this tile yet.",
            className="text-muted",
        )

    label = (tile.get("artifact") or {}).get("label", "Download artifact")

    return True, html.A(
        label,
        href=url,
        target="_blank",
        className="btn btn-primary",
    )