import dash
from dash import html, dcc, register_page, Input, Output, State, MATCH, ALL, ctx, callback
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import Patch
import os
import re
import json
import boto3
from importlib.resources import files

from stratabi.core.s3_loader import (
    dashboard_id_from_value,
    load_dashboard_json,
    list_dashboard_options,
    load_module_json,
    parse_s3_location,
    s3_uri,
)
from stratabi.core.runner import execute_tile
from stratabi.core.renderer import render_block
from stratabi.core.status_store import get_dashboard_statuses
import time
import zlib
from datetime import date
from copy import deepcopy
from urllib.parse import parse_qsl, unquote
from stratabi.core.source_resolver import SourceResolver


register_page(__name__, path="/dashboard")

# App-module route. Dash Pages only renders the exact registered path, so without an explicit
# template, /dashboard/apps/<module_id> 404s and every navbar "Apps" link is dead. Register the
# same dashboard layout under the template; the url-driven callbacks (parse_app_module_id /
# load_dashboard_config) render the module. `layout` is defined below, so the lambda resolves it
# at render time.
register_page(
    "stratabi_dashboard_apps",
    path_template="/dashboard/apps/<module_id>",
    layout=lambda **kw: layout(**kw),
)


# Local mode (`stratabi demo quick`, or no STRATABI_MODE=aws): dashboards come from disk and
# there is no status table, so status lookups are skipped.
def local_mode() -> bool:
    return os.getenv("STRATABI_MODE", "local") != "aws"


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
    # The normalized status row carries result_s3_key but not system_bucket, so fall back
    # to the configured system bucket.
    bucket = status_or_context.get("system_bucket") or os.getenv("STRATABI_SYSTEM_BUCKET")
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

    # Non-cache (async Athena / Lambda): the artifact is written by the tile's async run
    # and recorded in the status store. Presign the latest SUCCEEDED result object.
    from stratabi.core import status_store
    status = status_store._latest_status_for_tile(
        dashboard_key=dashboard_key,
        runtime_session_id=runtime_session_id,
        tile_id=tile.get("id"),
    )
    if status and str(status.get("status", "")).upper() == "SUCCEEDED":
        return presign_artifact_url(status, filename=artifact_cfg.get("filename"))
    return None


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


# Block types that own a global dashboard input/control value. Query parameters
# may hydrate these as their INITIAL value (see update_tile).
_HYDRATABLE_INPUT_TYPES = {"input_select", "input_range", "input_text", "dropdown"}


def parse_dashboard_key(pathname: str) -> str | None:
    """Resolve a non-app dashboard key/id from a URL path like /dashboard/<key>.

    Returns None for the bare /dashboard route, for /dashboard/apps/... module
    routes, and for nested paths — so URL-driven dashboard loading never collides
    with module/app routing. The returned key is matched against the selector
    options (by full value or dashboard id) in populate_dashboard_selector.
    """
    if not pathname or is_app_route(pathname):
        return None
    prefix = "/dashboard/"
    if not pathname.startswith(prefix):
        return None
    rest = unquote(pathname[len(prefix):]).strip("/")
    if not rest or "/" in rest:
        return None
    return rest


def parse_query_params(search: str | None) -> dict:
    """Parse a URL query string (?foo=bar&baz=qux) into a flat {name: value} dict.

    Last value wins for repeated keys. Values are strings; matching and validation
    are left to the existing input blocks, so unknown/invalid params are ignored.
    """
    if not search:
        return {}
    return {k: v for k, v in parse_qsl(search.lstrip("?"), keep_blank_values=True)}


def _module_ui(module: dict) -> dict:
    """Opt-in app settings from module.json `ui`: Refresh / Status buttons (default off) and a
    page-wide card style (default: unchanged)."""
    ui = module.get("ui") if isinstance(module.get("ui"), dict) else {}
    style = ui.get("card_style") if ui.get("card_style") in _CARD_STYLES else None
    return {"show_refresh": bool(ui.get("show_refresh")), "show_status": bool(ui.get("show_status")),
            "card_style": style}


# Module HTML (StrataMail / StrataNotebook / StrataChat pages) paints its own background with this
# palette — dark themes #0d1117, light themes #ffffff. "match" gives the app's cards the SAME fill
# (assets/module-cards.css), so an HTML tile's iframe blends into its card: no box inside a box.
_DARK_APP_THEMES = {"guildmaster", "cyborg", "darkly", "slate", "solar", "superhero", "vapor"}
_CARD_STYLES = {"match", "muted"}


def _module_surface() -> str:
    theme = os.getenv("STRATABI_THEME", "guildmaster").strip().lower()
    return "dark" if theme in _DARK_APP_THEMES else "light"


def _apply_card_style(layout: list, style: str | None) -> list:
    """Give every tile of an app the module's card look, unless the tile sets its own card color.
      match  - card fill = the module HTML background via assets/module-cards.css
               (.sbi-surface-dark #0d1117 / .sbi-surface-light #ffffff, !important) so HTML tiles
               blend into their card; text-only tiles (static markdown, no title) lose the card
               chrome entirely and read as page text.
      muted  - Bootstrap "secondary" outline (transparent fill, muted border).
    Returns new tile dicts; the module JSON is never modified."""
    if style not in _CARD_STYLES:
        return layout
    out = []
    for tile in layout:
        t = dict(tile)
        card = dict(t.get("card") or {})
        own = "color" in card or "outline" in card
        bare = (not t.get("exec") and not t.get("title")
                and (t.get("block") or {}).get("type") == "markdown")
        if style == "muted":
            if not own:
                card.update(color="secondary", outline=True)
            t["_card_class"] = "sbi-card-muted"
        elif bare:
            t["_card_class"] = "sbi-card-bare"
        elif not own:
            card.update(color=None, outline=False)
            t["_card_class"] = f"sbi-card-match sbi-surface-{_module_surface()}"
        else:
            # A tile's own color tells the page's story (select / act / view): keep its colored
            # outline, but on the module's surface so HTML tiles still blend in.
            t["_card_class"] = f"sbi-surface-{_module_surface()}"
        t["card"] = card
        out.append(t)
    return out


def _page_has_dashboard_source(module_id, active_page_id) -> bool:
    if not module_id:
        return False
    try:
        module = load_module_json(module_id)
    except Exception:  # noqa: BLE001
        return False
    pages = module.get("pages") or []
    page = next((p for p in pages if p.get("page_id") == active_page_id), pages[0] if pages else {})
    return isinstance((page or {}).get("dashboard_source"), dict)


def build_page_config(module: dict, page: dict) -> dict:
    page_config_id = f"{module.get('module_id')}::{page.get('page_id')}"
    return {
        "id": page_config_id,
        "_dashboard_key": page_config_id,
        "name": page.get("label") or module.get("label"),
        "layout": page.get("layout", []),
        "settings": module.get("settings", {}),
    }


def _safe_session_segment(value) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))[:96]


def apply_dashboard_source(cfg: dict, page: dict, runtime_session_id, inputs) -> dict:
    """SESSION DASHBOARD LOADING (general module-page seam).

    If a multi_page_app page declares `dashboard_source`, render the caller's own session-scoped
    dashboard instead of the page's static layout — useful for conversational builders (StrataChat),
    per-session scratch dashboards, previews, and development workflows.

    Owner isolation is enforced by core, not the module: the `{runtime_session_id}` placeholder is
    filled from the core-managed runtime session store (never client input), so the client-supplied
    `{session_id}` (from the input store, sanitized) can only address keys UNDER the caller's own
    runtime-session prefix. The template MUST contain `{runtime_session_id}` or the seam is ignored.
    Anything missing/denied/corrupt degrades to the page's static `layout` (the empty state).
    """
    src = (page or {}).get("dashboard_source")
    if not isinstance(src, dict):
        return cfg
    tmpl = src.get("s3_key") or ""
    if "{runtime_session_id}" not in tmpl:
        return cfg  # refuse non-isolated templates
    store = (inputs or {}).get("inputs", inputs) if isinstance(inputs, dict) else {}
    sid = _safe_session_segment(store.get(src.get("session_input", "session_id")))
    rsid = _safe_session_segment(runtime_session_id or "shared")
    key = tmpl.replace("{runtime_session_id}", rsid).replace("{session_id}", sid)
    try:
        from stratabi.core.loader import load_dashboard_by_s3_key
        doc = load_dashboard_by_s3_key(key)
    except Exception:
        doc = None
    if isinstance(doc, dict) and isinstance(doc.get("layout"), list) and doc["layout"]:
        return {**cfg, "layout": doc["layout"], "name": doc.get("name", cfg.get("name")),
                "settings": doc.get("settings", cfg.get("settings", {}))}
    return cfg


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
        return not exec_cfg.get("sync", False)  # exec.sync tiles answer in the request

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

def should_execute_tile(tile, trigger, trigger_data=None, tile_status=None, run_data=None,
                        app_route=False):
    mode = tile.get("load", {}).get("mode", "load_once")

    client_status = tile_status
    triggered_by = tile.get("triggered_by", []) or []

    latest_trigger_tile_id = None

    if isinstance(trigger_data, dict):
        latest_trigger_tile_id = trigger_data.get("trigger_tile_id")

    # Per-tile run button (▷) writes a dedicated run store carrying target_tile_id.
    # Kept separate from dashboard-trigger-store so the trigger bus stays dedicated
    # to input changes and full-page refresh. Checked BEFORE the "already running" guard so
    # ▷ can recover a tile stuck on Processing…; the runner itself refuses to double-invoke
    # a run that is genuinely still in progress.
    if trigger == "dashboard-run-store":
        return isinstance(run_data, dict) and run_data.get("target_tile_id") == tile.get("id")

    # If async tile is already running, do not create new work.
    # Polling is handled by should_check_tile().
    if client_status in ACTIVE_TILE_STATUSES:
        return False

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
        # An action tile finished (trigger_type "action"): only tiles that name it re-run — e.g. a
        # "Create report" action refreshing the report list and the Existing-report dropdown.
        if isinstance(trigger_data, dict) and trigger_data.get("trigger_type") == "action":
            return bool(latest_trigger_tile_id) and latest_trigger_tile_id in triggered_by
        if triggered_by and latest_trigger_tile_id:
            return latest_trigger_tile_id in triggered_by
        return mode in {"always", "input"}

    # App (module) Refresh re-queries the current page state: sync views/option feeds run again
    # (each call is a fresh read), failed tiles retry — but manual tiles are actions (send,
    # create, delete…), so Refresh never runs them.
    if trigger == "dashboard-refresh-store" and app_route:
        if mode == "manual" or client_status in ACTIVE_TILE_STATUSES:
            return False
        if client_status in FAILED_TILE_STATUSES:
            return True
        _x = tile.get("exec") or {}
        if _x.get("type") == "lambda" and _x.get("sync"):
            return True
        return mode in {"always", "interval", "input"} or client_status != "SUCCEEDED"

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
    # A tick never starts work for load_once/input/manual tiles. For interval/always tiles it
    # schedules the next run even after a success or failure: interval run ids are bucketed by
    # load.interval_ms, so within a bucket the runner just returns the existing run (no duplicate
    # invoke) and a new bucket starts the next run. An in-flight run is polled, not duplicated.
    if trigger == "dashboard-interval":
        if client_status in ACTIVE_TILE_STATUSES:
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

    # Sync Lambda tiles block their request: show the loading spinner while it runs.
    if exec_type == "lambda" and exec_cfg.get("sync", False):
        return "loading"

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
_PORTRAIT_ALIGN = {"start": "flex-start", "center": "center", "end": "flex-end"}


def _responsive_col_kwargs(tile: dict) -> dict:
    """Optional, additive responsive extras (dashboard schema 1.2.0):
      - position.portrait : per-tile overrides (order/width/height/align) applied in mobile portrait
      - position.hide_on  : hide the tile in the named orientation ('portrait' | 'landscape')
    Emits CSS custom properties + marker classes consumed by assets/portrait.css. No effect on
    desktop (except an explicit hide_on='landscape') and none when both fields are absent."""
    pos = tile.get("position") or {}
    classes, style = [], {}
    p = pos.get("portrait")
    if isinstance(p, dict) and p:
        classes.append("has-portrait")
        if "order" in p:
            style["--p-order"] = str(int(p["order"]))
        if "width" in p:
            style["--p-basis"] = f"{int(p['width']) / 12 * 100:.4f}%"
        if "height" in p:
            style["--p-height"] = f"{int(p['height'])}px"
        if "align" in p:
            style["--p-align"] = _PORTRAIT_ALIGN.get(p.get("align"), "stretch")
    if pos.get("hide_on") in ("portrait", "landscape"):
        classes.append(f"hide-on-{pos['hide_on']}")
    if not classes:
        return {}
    out = {"className": " ".join(classes)}
    if style:
        out["style"] = style
    return out


def _render_static_tile(tile: dict, dashboard_key: str | None, url_search: str | None):
    """Render a tile that runs nothing (no exec) straight into the grid. Its content is fully
    determined by the config, so it must not depend on a callback that races the grid rebuild
    (that race is why markdown/input tiles sometimes came up blank after switching tabs)."""
    block = tile.get("block")
    if not block:
        return html.Div("Tile missing block config.", className=status_text_class(tile, "danger"))

    if block.get("type") in _HYDRATABLE_INPUT_TYPES:
        input_id = (block.get("config") or {}).get("input_id")
        params = parse_query_params(url_search) if input_id else {}
        if input_id and input_id in params:
            block = deepcopy(block)
            block.setdefault("config", {})["value"] = params[input_id]

    try:
        return render_block(block, None, tile_id=tile.get("id"))
    except Exception as e:  # noqa: BLE001
        return html.Div(
            [html.Div("Block render failed.", className=status_text_class(tile, "danger") + " fw-bold"),
             html.Pre(str(e), className="small " + status_text_class(tile, "danger"))]
        )


# Shown while a tile's data is being produced (first load and async runs): a small badge with a
# working word, and a quiet hint. The word is stable for a tile for ~20 s (crc32, so every worker
# process agrees and re-renders don't flicker), then moves on during a long build.
BUILDING_WORDS = (
    "Building", "Calculating", "Extracting", "Generating", "Mining", "Scaffolding", "Processing",
    "Drilling", "Excavating", "Forging", "Smelting", "Pressurizing", "Calibrating", "Fabricating",
    "Assembling", "Wiring", "Machining", "Tuning", "Tempering", "Compiling", "Indexing", "Parsing",
    "Rendering", "Synthesizing", "Orchestrating", "Materializing", "Provisioning", "Stratifying",
    "Layering", "Coring", "Prospecting", "Distilling", "Igniting", "Separating", "Diverting",
    "Hydraulicking", "Hydrolyzing", "Effervescing",
)
BUILDING_HINT = "Refresh to check"
_WORD_PERIOD_S = 20


def _flavor_words(tile: dict | None) -> tuple:
    """tile.flavor_text (schema 1.6.0): one word or a list to rotate; else the default bank."""
    ft = (tile or {}).get("flavor_text")
    if isinstance(ft, str):
        ft = [ft]
    words = tuple(w.strip()[:40] for w in ft if isinstance(w, str) and w.strip()) if isinstance(ft, list) else ()
    return words or BUILDING_WORDS


def building_word(tile, now: float | None = None) -> str:
    """The working word for a tile right now (accepts the tile dict, or a bare tile id)."""
    tile = tile if isinstance(tile, dict) else {"id": tile}
    words = _flavor_words(tile)
    bucket = int((time.time() if now is None else now) // _WORD_PERIOD_S)
    word = words[zlib.crc32(f"{tile.get('id')}:{bucket}".encode()) % len(words)]
    return word if word.endswith(("…", "...")) else f"{word}…"


def building_indicator(tile: dict | None, now: float | None = None):
    word = building_word(tile or {}, now)
    return html.Div(
        [html.Span(word, className="badge rounded-pill text-bg-primary sbi-building-badge"),
         html.Span(BUILDING_HINT, className="sbi-building-hint")],
        className="sbi-building",
    )


def _initial_tile_content(tile: dict, dashboard_key: str | None, url_search: str | None):
    if not tile.get("exec"):
        return _render_static_tile(tile, dashboard_key, url_search)
    # Executing tiles: an explicit tile.placeholder, else a sensible default — never a blank card.
    placeholder = tile.get("placeholder")
    if not (isinstance(placeholder, str) and placeholder.strip()):
        if (tile.get("load") or {}).get("mode", "load_once") != "manual":
            return building_indicator(tile)
        placeholder = "Press **▷** to run."
    return dcc.Markdown(placeholder, className="text-muted small mb-0 stratabi-placeholder")


_DEFAULT_BLOCK_HEIGHT = {"table": "500px", "raw_html": "500px", "plotly": "450px",
                         "plotly_resampler": "450px"}
_INPUT_BLOCKS = {"input_select", "input_range", "input_text", "dropdown"}


def _reserved_height(tile: dict) -> str | None:
    """Height to hold for an EXECUTING tile until its result renders (placeholder -> content with no
    layout shift). Uses the block's own height (config.height, or a Plotly figure's layout.height),
    else the block's renderer default. Static tiles render at build time, so they need none."""
    if not tile.get("exec"):
        return None
    block = tile.get("block") or {}
    btype = block.get("type")
    cfg = block.get("config") or {}
    h = cfg.get("height")
    if btype in ("plotly", "plotly_resampler") and not h:
        fh = ((cfg.get("figure") or {}).get("layout") or {}).get("height") if isinstance(cfg.get("figure"), dict) else None
        h = f"{int(fh)}px" if isinstance(fh, (int, float)) else None
    if isinstance(h, (int, float)):
        h = f"{int(h)}px"
    if isinstance(h, str) and re.match(r"^\d+(\.\d+)?(px|vh|rem|em)$", h.strip()):
        return h.strip()
    if btype in _INPUT_BLOCKS:
        return "38px"          # one control row
    return _DEFAULT_BLOCK_HEIGHT.get(btype)


def render_tile_card(tile, polling_enabled=False, dashboard_key=None, url_search=None, stacked=False):
    tile_id = tile.get("id")

    if not tile_id:
        return dbc.Alert("Tile missing id.", color="danger")

    header = None
    if tile.get("title") and tile.get("card", {}).get("show_header", True):
        header = dbc.CardHeader(tile["title"])

    indicator = load_indicator(tile, dashboard_polling_enabled=polling_enabled)

    # Static tiles render their content here; executing tiles start with their placeholder
    # (tile.placeholder, schema 1.3.0, or a default) until their first result arrives.
    tile_content = html.Div(
        _initial_tile_content(tile, dashboard_key, url_search),
        id={"type": "tile-content", "tile_id": tile_id},
        # Reserve the block's final height while it loads, so cards don't jump when results land.
        style=({"minHeight": _reserved_height(tile)} if _reserved_height(tile) else None),
    )

    tile_status_store = dcc.Store(
        id={"type": "tile-status-store", "tile_id": tile_id},
        storage_type="session",
    )
    # Set when this tile's own run (▷) completes; tiles whose triggered_by names it re-run.
    tile_done_store = dcc.Store(id={"type": "tile-done", "tile_id": tile_id})

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
    _is_control_block = _block_type in {"input_select", "input_range", "input_text", "dropdown"}
    _buttons_default = bool(tile.get("exec")) and not _is_control_block

    control_buttons = []

    if tile_controls.get("run_button", _buttons_default):
        # controls.run_icon "refresh" (↻) for re-reading something (option lists, views); the
        # default ▷ for actions that do something.
        _refresh = tile_controls.get("run_icon") == "refresh"
        control_buttons.append(
            dbc.Button(
                "↻" if _refresh else "▷",
                id={"type": "tile-run", "tile_id": tile_id},
                color="primary",
                size="sm",
                outline=True,
                n_clicks=0,
                title="Refresh" if _refresh else "Run tile",
                className="me-1",
            )
        )

    # Download defaults ON only where an S3 artifact actually exists: cache tiles and
    # async runs (async Athena + Lambda). A plain sync tile returns an inline dataframe
    # with no downloadable object, so don't show a button that can't work. Explicit
    # artifact.download overrides.
    _exec_type = (tile.get("exec") or {}).get("type")
    _artifact_default = (_exec_type in ("cache", "lambda") or bool((tile.get("exec") or {}).get("async"))) \
        and not _is_control_block   # an input's option list isn't something to download
    if artifact_cfg.get("download", _artifact_default):
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
        tile_done_store,
        # keep_previous tiles: "Updating…" / "stale" badge over the last successful result
        html.Div(id={"type": "tile-badge", "tile_id": tile_id}, className="sbi-tile-badge"),
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
        # Stacked cards size to their content; side-by-side cards share the row height.
        className=("mb-3" if stacked else "mb-3 h-100") + (f" {tile['_card_class']}" if tile.get("_card_class") else ""),
    )


def build_dashboard_grid(dashboard_config, url_search=None):
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

        # position.stack (schema 1.5.0): tiles in this row that share a stack name render as ONE
        # column, one under another (e.g. a column of controls beside a tall conversation). The
        # column is as wide as the widest tile in the stack and sits where its first tile is ordered.
        groups, seen = [], {}
        for tile in row_tiles:
            name = (tile.get("position") or {}).get("stack")
            if name:
                if name not in seen:
                    seen[name] = []
                    groups.append(("stack", seen[name]))
                seen[name].append(tile)
            else:
                groups.append(("tile", tile))

        def card(tile, stacked=False):
            return render_tile_card(tile, polling_enabled=polling_enabled,
                                    dashboard_key=dashboard_config.get("_dashboard_key"),
                                    url_search=url_search, stacked=stacked)

        cols = []
        for kind, item in groups:
            if kind == "tile":
                cols.append(dbc.Col(
                    card(item),
                    # Stack full-width on phones (<768px); use the JSON-configured width on md+
                    # (tablets, landscape phones, desktop). The dashboard JSON is unchanged — the
                    # mobile reflow is purely presentational. Optional position.portrait overrides
                    # (order/width/height/align) apply only in mobile portrait, via assets/portrait.css.
                    xs=12,
                    md=item.get("position", {}).get("width", 12),
                    **_responsive_col_kwargs(item),
                ))
            else:
                width = max(int((t.get("position") or {}).get("width", 12)) for t in item)
                cols.append(dbc.Col([card(t, stacked=True) for t in item], xs=12, md=width,
                                    className="sbi-stack"))

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
def layout(**kwargs):
    # Dash Pages passes query-string params and any path variables to a page's layout function
    # as keyword arguments. Accept and ignore them here (callbacks read the URL themselves).
    # Without **kwargs, any query string on /dashboard raises TypeError and renders blank (500).
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
                            id="dash-ctl-selector",
                            xs=12,
                            md=4,
                        ),
                        dbc.Col(
                            dbc.Button(
                                "Refresh",
                                id="dashboard-refresh-btn",
                                color="primary",
                                n_clicks=0,
                            ),
                            id="dash-ctl-refresh",
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Button(
                                "Status",
                                id="dashboard-status-btn",
                                color="secondary",
                                n_clicks=0,
                            ),
                            id="dash-ctl-status",
                            width="auto",
                        ),
                        dbc.Col(
                            html.Div(id="dashboard-status-text", className="text-muted"),
                            xs=12,
                            md=True,
                        ),
                    ],
                    className="g-2 align-items-center mb-4",
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
        return html.Div("No runs recorded for this page in this session yet.", className="text-muted")

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
    Input("url", "search"),
    Input("dashboard-refresh-store", "data"),
    State("current-user-id-store", "data"),
    State("dashboard-input-store", "data"),
    State("dashboard-runtime-session-store", "data"),
)
def load_dashboard_config(pathname, dashboard_key, active_page_id, search, _refresh, user_id, inputs, runtime_session):
    _t0 = time.perf_counter()
    try:
        return _load_dashboard_config(pathname, dashboard_key, active_page_id, search, _refresh,
                                      user_id, inputs, runtime_session)
    finally:
        _log_timing("config", parse_app_module_id(pathname) or dashboard_key, _t0, page=active_page_id)


def _load_dashboard_config(pathname, dashboard_key, active_page_id, search, _refresh, user_id, inputs, runtime_session):
    module_id = parse_app_module_id(pathname)
    # Refresh reloads the config only for module pages whose layout comes from a session
    # dashboard (dashboard_source, e.g. StrataChat's Workspace) — the tile-level refresh alone
    # can't pick up a newly selected session. Everything else keeps today's tile-only refresh.
    if ctx.triggered_id == "dashboard-refresh-store" and not _page_has_dashboard_source(module_id, active_page_id):
        raise PreventUpdate
    runtime_session_id = (runtime_session or {}).get("runtime_session_id") if isinstance(runtime_session, dict) else None

    if module_id:
        try:
            module = load_module_json(module_id)
        except Exception as e:
            return {}, dbc.Alert(f"Failed to load module `{module_id}`: {e}", color="danger")

        module_type = module.get("module_type")
        pages = module.get("pages", [])

        if module_type != "multi_page_app":
            module_config_id = module.get("module_id") or module_id
            cfg = {
                "id": module_config_id,
                "_dashboard_key": module_config_id,
                "name": module.get("label"),
                "layout": module.get("layout", []),
                "settings": module.get("settings", {}),
                "_module_ui": _module_ui(module),
            }
            cfg["layout"] = _apply_card_style(cfg["layout"], cfg["_module_ui"]["card_style"])
            # Same ?source resolution as multi-page modules and dashboards.
            return resolve_sources_in_config(cfg), html.H5(module.get("label", module_id))

        if not pages:
            return {}, dbc.Alert("Module has no pages.", color="warning")

        if not active_page_id:
            active_page_id = module.get("overrides", {}).get("default_page") or pages[0].get("page_id")

        page = next((p for p in pages if p.get("page_id") == active_page_id), pages[0])
        controls = render_module_controls(module, active_page_id)

        cfg = apply_dashboard_source(build_page_config(module, page), page, runtime_session_id, inputs)
        cfg["_module_ui"] = _module_ui(module)
        cfg["layout"] = _apply_card_style(cfg["layout"], cfg["_module_ui"]["card_style"])
        return resolve_sources_in_config(cfg), controls

    if not dashboard_key:
        raise PreventUpdate

    try:
        config = load_dashboard_json(dashboard_key)
    except PermissionError:
        # Not authorized for this key (or a crafted key) — degrade to empty, don't error.
        return {}, hidden_module_controls()
    except Exception:
        # Missing/corrupt key — same graceful empty state rather than a callback error.
        return {}, hidden_module_controls()

    config = deepcopy(config)
    config["_dashboard_key"] = dashboard_key

    return resolve_sources_in_config(config), hidden_module_controls()

@callback(
    Output("dashboard-grid", "children"),
    Input("dashboard-config-store", "data"),
    State("url", "search"),
)
def render_dashboard_grid(config, url_search=None):
    if not config:
        return html.Div("Select a dashboard.", className="text-muted")

    try:
        return build_dashboard_grid(config, url_search=url_search)
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


def _input_defaults_from_config(config: dict) -> dict:
    """Default values declared by the dashboard's input_select / input_range blocks,
    keyed by their input_id. Used to seed a tile's first run: on initial load the
    dashboard-input-store is still empty (store_inputs hasn't fired), so without these
    a parameterised tile would execute with no inputs and raise "Missing input for SQL
    param". Mirrors the {input_id: value} shape store_inputs writes under "inputs"."""
    defaults: dict = {}
    for tile in (config or {}).get("layout", []):
        block = tile.get("block") or {}
        if block.get("type") in _INPUT_BLOCK_TYPES:
            cfg = block.get("config") or {}
            input_id = cfg.get("input_id") or tile.get("id")
            if input_id is None or not ("value" in cfg or "default" in cfg):
                continue
            value = cfg.get("value", cfg.get("default"))
            # A static select's default must be one of its options (dynamic ones are filled by
            # their own run, so they're not checked here).
            if block.get("type") in ("input_select", "dropdown") and not tile.get("exec") and value is not None:
                opts = cfg.get("options")
                if isinstance(opts, list) and opts:
                    valid = {o.get("value") if isinstance(o, dict) else o for o in opts}
                    values = value if isinstance(value, list) else [value]
                    if not all(v in valid for v in values):
                        continue
            defaults[input_id] = value
    return defaults


def _url_input_values(config: dict, url_search: str | None) -> dict:
    """?input_id=value URL params for inputs this page declares (initial values only)."""
    params = parse_query_params(url_search)
    if not params:
        return {}
    out = {}
    for tile in (config or {}).get("layout", []):
        block = tile.get("block") or {}
        if block.get("type") in _HYDRATABLE_INPUT_TYPES:
            input_id = (block.get("config") or {}).get("input_id")
            if input_id in params:
                out[input_id] = params[input_id]
    return out


_INPUT_BLOCK_TYPES = ("input_select", "input_range", "input_text", "dropdown")


def _current_page_inputs(config: dict, stored: dict) -> dict:
    allowed: dict = {}
    for tile in (config or {}).get("layout", []):
        block = tile.get("block") or {}
        if block.get("type") not in _INPUT_BLOCK_TYPES:
            continue
        cfg = block.get("config") or {}
        input_id = cfg.get("input_id") or tile.get("id")
        static_values = None
        if block.get("type") in ("input_select", "dropdown") and not tile.get("exec"):
            opts = cfg.get("options")
            if isinstance(opts, list) and opts:
                static_values = {o.get("value") if isinstance(o, dict) else o for o in opts}
        allowed[input_id] = static_values
    if not allowed:
        return {}  # no input tiles on this page: nothing from other pages applies

    out = {}
    for key, value in stored.items():
        if key not in allowed:
            continue
        valid = allowed[key]
        if valid is not None and value is not None:
            values = value if isinstance(value, list) else [value]
            if not all(v in valid for v in values):
                continue
        out[key] = value
    return out


_TIMING = os.getenv("STRATABI_TIMING_LOG", "").strip().lower() in ("1", "true", "yes")
_timing_logger = __import__("logging").getLogger("stratabi.timing")


def _log_timing(kind: str, name, t0: float, **fields) -> None:
    """STRATABI_TIMING_LOG=1: one log line per tile execution / config load, for measuring where
    page-open time goes (CloudWatch Logs Insights: filter @message like 'stratabi.timing')."""
    if not _TIMING:
        return
    ms = (time.perf_counter() - t0) * 1000
    extra = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    _timing_logger.warning("stratabi.timing kind=%s name=%s ms=%.0f %s", kind, name, ms, extra)


_RUN_STATUSES = ACTIVE_TILE_STATUSES | FAILED_TILE_STATUSES | {"SUCCEEDED"}


def _run_status(result):
    """The run status if `result` is a runner status envelope ({"status": "RUNNING"} etc.), else
    None. A JSON payload — dropdown options {"options": [...]}, an input value {"value": ...} — is
    DATA for the block, not a status: it used to be read as status "RUNNING" (the old default), which
    left every JSON-fed input stuck on "Processing…" even though its run succeeded."""
    if not isinstance(result, dict) or "status" not in result:
        return None
    status = str(result.get("status") or "").upper()
    return status if status in _RUN_STATUSES else None


def _empty_result_note(tile: dict, block: dict, result):
    """A successful run with nothing to show says so, instead of rendering a blank card."""
    btype = (block or {}).get("type")
    if btype in ("table", "plotly", "plotly_resampler") and getattr(result, "empty", False) is True:
        return html.Div("No rows returned.", className=status_text_class(tile, "muted"))
    if btype in ("raw_html", "markdown") and isinstance(result, str) and not result.strip():
        return html.Div("The tile ran but returned no content.", className=status_text_class(tile, "muted"))
    return None


def _tile_exec_error(tile: dict, exc: Exception):
    """Render a tile execution failure (returns (content, status)) instead of letting the
    exception escape the callback as an HTTP 500 with a blank tile."""
    name = type(exc).__name__
    msg = str(exc) or name
    blob = f"{name} {msg}".lower()
    if "nocredential" in blob or "expiredtoken" in blob or ("expired" in blob and "token" in blob):
        friendly = "AWS credentials not found or expired. Run `aws sso login` (or refresh your credentials)."
    else:
        friendly = f"Tile execution failed: {msg}"
    return html.Div(friendly, className=status_text_class(tile, "danger")), "FAILED"


@callback(
    Output({"type": "tile-content", "tile_id": MATCH}, "children"),
    Output({"type": "tile-status-store", "tile_id": MATCH}, "data"),
    Output({"type": "tile-badge", "tile_id": MATCH}, "children"),
    Output({"type": "tile-done", "tile_id": MATCH}, "data"),
    Input("dashboard-config-store", "data"),
    Input("dashboard-refresh-store", "data"),
    Input("dashboard-interval", "n_intervals"),
    Input("dashboard-trigger-store", "data"),
    Input("dashboard-run-store", "data"),
    State("dashboard-input-store", "data"),
    State("active-dashboard-key-store", "data"),
    State("dashboard-runtime-session-store", "data"),
    State({"type": "tile-status-store", "tile_id": MATCH}, "data"),
    State({"type": "tile-content", "tile_id": MATCH}, "id"),
    State("url", "search"),
    # Fire when a tile mounts too: a call triggered by the config change can land on the grid
    # being replaced, so each freshly mounted tile must request its own content.
    prevent_initial_call=False,
)
def update_tile(config, _refresh, _tick, trigger_data, run_data, inputs, active_dashboard, runtime_session,
                tile_status_store, tile_component_id, url_search):
    out = _update_tile_impl(config, _refresh, _tick, trigger_data, run_data, inputs, active_dashboard,
                            runtime_session, tile_status_store, tile_component_id, url_search)
    content, status = out[0], out[1]
    done = _action_done(config, (tile_component_id or {}).get("tile_id"), ctx.triggered_id, run_data,
                        tile_status_store, content, status)
    if len(out) > 2:
        return content, status, out[2], done
    # New content replaces whatever was there, so any Updating/stale badge goes with it.
    return content, status, ("" if content is not dash.no_update else dash.no_update), done


def _action_done(config, tile_id, trigger, run_data, previous_status, content, status):
    """A timestamp when this tile's own run just finished successfully and some other tile lists
    it in `triggered_by`; else no_update. Sync runs finish inside the ▷ call; async runs finish
    when polling first sees SUCCEEDED."""
    layout = (config or {}).get("layout") or []
    if not tile_id or not any(tile_id in (t.get("triggered_by") or []) for t in layout):
        return dash.no_update
    ran_now = (trigger == "dashboard-run-store" and isinstance(run_data, dict)
               and run_data.get("target_tile_id") == tile_id)
    if ran_now:
        ok = content is not dash.no_update and status not in ACTIVE_TILE_STATUSES | FAILED_TILE_STATUSES | {"RESTRICTED"}
    else:
        ok = (trigger == "dashboard-interval" and status == "SUCCEEDED"
              and previous_status in ACTIVE_TILE_STATUSES)
    return time.time() if ok else dash.no_update


@callback(
    Output("dashboard-trigger-store", "data", allow_duplicate=True),
    Input({"type": "tile-done", "tile_id": ALL}, "data"),
    State("current-user-id-store", "data"),
    State("active-dashboard-key-store", "data"),
    prevent_initial_call=True,
)
def announce_action_done(_done, user_id, dashboard_key):
    tid = ctx.triggered_id
    if not isinstance(tid, dict) or not (ctx.triggered or [{}])[0].get("value"):
        raise PreventUpdate
    return {"trigger_type": "action", "trigger_tile_id": tid.get("tile_id"), "input_id": None,
            "ts": time.time(), "user_id": user_id, "dashboard_key": dashboard_key}


def _keeps_previous(tile: dict) -> bool:
    return bool((tile.get("load") or {}).get("keep_previous")) and tile_is_async(tile)


def _badge(status: str, result: dict | None, tile: dict | None = None):
    if status in ACTIVE_TILE_STATUSES:  # previous result stays visible; the badge says work is underway
        return html.Span(building_word(tile or {}),
                         className="badge rounded-pill text-bg-primary sbi-building-badge")
    msg = (result or {}).get("message") or ("run cancelled" if status == "CANCELLED" else "run failed")
    return html.Span(f"Last successful result (stale) — {str(msg)[:200]}", className="badge text-bg-warning",
                     title=str(msg))


def _last_success_result(tile: dict, dashboard_key, runtime_session_id):
    """The last successful result for this tile in this dashboard + runtime session, loaded through
    its own (immutable, run-specific) result contract — or None."""
    if local_mode():
        return None
    try:
        from stratabi.core.s3_loader import load_result_from_status
        from stratabi.core.status_store import last_succeeded_for_tile
        item = last_succeeded_for_tile(dashboard_key=dashboard_key, runtime_session_id=runtime_session_id,
                                       tile_id=tile.get("id"))
        return load_result_from_status(item) if item else None
    except Exception:  # noqa: BLE001 — no fallback is fine; the placeholder shows
        return None


def _with_resolved_triggers(tile: dict, config: dict) -> dict:
    """`triggered_by` may name either an input TILE id ("region_input", as the schema docs and the
    LLM contract show) or the input's `input_id` ("region"). Input components are keyed by input_id,
    so the trigger bus carries the input_id; resolve tile ids to their input_ids so both spellings
    work."""
    names = tile.get("triggered_by") or []
    if not names:
        return tile
    by_tile = {}
    for t in (config or {}).get("layout") or []:
        iid = ((t.get("block") or {}).get("config") or {}).get("input_id")
        if t.get("id") and iid:
            by_tile[t["id"]] = iid
    resolved = list(dict.fromkeys([*names, *(by_tile[n] for n in names if n in by_tile)]))
    return tile if resolved == list(names) else {**tile, "triggered_by": resolved}


def _update_tile_impl(config, _refresh, _tick, trigger_data, run_data, inputs, active_dashboard, runtime_session, tile_status_store, tile_component_id, url_search):
    if not config:
        return html.Div("Dashboard config not loaded", className="text-muted"), dash.no_update
    
    runtime_session_id = None
    if isinstance(runtime_session, dict):
        runtime_session_id = runtime_session.get("runtime_session_id")

    tile = get_tile_by_id(config, tile_component_id["tile_id"])

    if not tile:
        return html.Div("Tile not found", className="text-danger"), dash.no_update

    # Static tiles (no exec) are rendered into the grid at build time; nothing to do here.
    if not tile.get("exec"):
        return dash.no_update, dash.no_update

    trigger = ctx.triggered_id

    should_start_or_reload = should_execute_tile(
        _with_resolved_triggers(tile, config),
        trigger,
        trigger_data,
        tile_status=tile_status_store,
        run_data=run_data,
        app_route=bool(config.get("_module_ui") is not None),
    )
    should_poll_existing = should_check_tile(tile, trigger, tile_status_store)

    if not should_start_or_reload and not should_poll_existing:
        return dash.no_update, dash.no_update
    
    dashboard_key = config.get("_dashboard_key") or active_dashboard

    # Merge declared input defaults UNDER whatever the input store currently holds, so a
    # parameterised tile has values on its first run even before store_inputs fires.
    # Store values take precedence over config defaults.
    # Precedence: current user input > URL initial value > configured value/default.
    effective_inputs = {"inputs": _input_defaults_from_config(config)}
    effective_inputs["inputs"].update(_current_page_inputs(config, _url_input_values(config, url_search)))
    if isinstance(inputs, dict):
        store_inputs_data = inputs.get("inputs") if isinstance(inputs.get("inputs"), dict) else \
            {k: v for k, v in inputs.items() if k != "_meta"}
        # The input store only refreshes when an input changes, so after switching pages/tabs it
        # can still hold the previous page's values. Keep only inputs this page declares, and
        # drop values a static select can't hold (its default applies instead).
        effective_inputs["inputs"].update(_current_page_inputs(config, store_inputs_data or {}))

    # Async re-run intent: an explicit ▷ re-runs the tile even if it already finished; a fresh
    # page load retries a failed or dead run; polls just report the current run.
    if trigger == "dashboard-run-store":
        rerun = "force"
    elif (trigger == "dashboard-trigger-store" and isinstance(trigger_data, dict)
          and trigger_data.get("trigger_type") == "action" and should_start_or_reload):
        rerun = "force"  # the action changed what this tile shows: same inputs, fresh run
    elif trigger in (None, "dashboard-config-store") and should_start_or_reload:
        rerun = "retry_failed"
    else:
        rerun = None

    trigger_kind = "action" if (trigger == "dashboard-trigger-store" and isinstance(trigger_data, dict)
                                and trigger_data.get("trigger_type") == "action") else {
        "dashboard-run-store": "run",
        "dashboard-trigger-store": "input",
        "dashboard-refresh-store": "refresh",
        "dashboard-interval": "interval",
    }.get(trigger, "load")

    _t0 = time.perf_counter()
    try:
        result = execute_tile(
            tile,
            effective_inputs,
            dashboard_key=dashboard_key,
            runtime_session_id=runtime_session_id,
            rerun=rerun,
            trigger_kind=trigger_kind,
        )
        _log_timing("tile", tile.get("id"), _t0, trigger=trigger_kind,
                    exec=(tile.get("exec") or {}).get("type"), dashboard=dashboard_key)
    except ValueError as e:
        # A param whose input value isn't available yet (input store not filled, or the
        # user hasn't chosen). Show a muted placeholder and wait for the input to
        # re-trigger this tile — never a 500.
        if "Missing input for SQL param" in str(e):
            return (
                html.Div("Waiting for input…", className=status_text_class(tile, "muted")),
                dash.no_update,
            )
        return _tile_exec_error(tile, e)
    except Exception as e:  # noqa: BLE001 — never let a tile's execution 500 the page
        # e.g. NoCredentialsError / ExpiredToken on a lapsed SSO session, or any Athena/
        # Lambda/S3 error. Render it in the tile as a failure instead of a blank 500.
        return _tile_exec_error(tile, e)

    status = _run_status(result)
    keep = None
    if status is not None and _keeps_previous(tile) and (status in ACTIVE_TILE_STATUSES or status in FAILED_TILE_STATUSES):
        badge = _badge(status, result, tile)
        if trigger not in (None, "dashboard-config-store"):
            # The previous result is already on screen: leave it, just show the badge.
            return dash.no_update, status, badge
        # Freshly mounted (reload / tab switch): nothing on screen yet — fetch the last success.
        previous = _last_success_result(tile, dashboard_key, runtime_session_id)
        if previous is not None:
            result, keep = previous, (status, badge)
            status = None  # render `previous` below, then report the real status + badge
        else:
            return (building_indicator(tile)
                    if status in ACTIVE_TILE_STATUSES else
                    html.Div(result.get("message", "Tile execution failed."),
                             className=status_text_class(tile, "danger"))), status, ""
    if status is not None:

        if status in ACTIVE_TILE_STATUSES:
            return building_indicator(tile), status

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

    # URL query params behave as INITIAL input values. Only on the initial
    # dashboard-load render (trigger None / dashboard-config-store) do we overlay a
    # matching ?input_id=value onto a COPY of an input block's config, so the control
    # renders with the hydrated value and store_inputs picks it up normally. We never
    # mutate the stored dashboard JSON, and we skip later triggers (refresh / interval
    # / input / run) so a user's own edits are never reset by the URL.
    if trigger in (None, "dashboard-config-store") and block.get("type") in _HYDRATABLE_INPUT_TYPES:
        input_id = (block.get("config") or {}).get("input_id")
        if input_id:
            params = parse_query_params(url_search)
            if input_id in params:
                block = deepcopy(block)
                block.setdefault("config", {})["value"] = params[input_id]

    empty_note = _empty_result_note(tile, block, result)
    if empty_note is not None:
        if keep:
            return empty_note, keep[0], keep[1]
        return empty_note, ("SUCCEEDED" if tile_is_async(tile) else dash.no_update)

    try:
        rendered = render_block(block, result, tile_id=tile.get("id"))

        if keep:
            return rendered, keep[0], keep[1]
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
    State("dashboard-input-store", "data"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def store_inputs(values, ids, user_id, dashboard_key, previous=None, pathname=None):
    # Values of inputs NOT on the current page are kept (same dashboard/app only), so a choice made
    # on one tab survives switching tabs — e.g. StrataChat's session drives the Workspace tab's
    # dashboard_source and pre-selects the JSON tab. Tiles still only receive inputs their own page
    # declares (_current_page_inputs), so nothing leaks into another page's tiles.
    scope = pathname or dashboard_key
    input_values = {}
    if isinstance(previous, dict) and (previous.get("_meta") or {}).get("scope") == scope:
        input_values.update(previous.get("inputs") or {})

    for value, ident in zip(values, ids):
        input_key = ident.get("input_id") or ident["tile_id"]
        input_values[input_key] = value

    data = {
        "_meta": {
            "user_id": user_id,
            "dashboard_key": dashboard_key,
            "scope": scope,
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

    # Only a real click on THIS button counts. Checking "any button has clicks" let a newly
    # mounted tile (n_clicks 0/None, fired on registration) be mistaken for a click once any
    # other tile had been clicked, running the wrong tile.
    fired = (ctx.triggered or [{}])[0]
    if not isinstance(triggered, dict) or not (fired.get("value") or 0) > 0:
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
    State("dashboard-config-store", "data"),
    State("dashboard-runtime-session-store", "data"),
    prevent_initial_call=True,
)
def toggle_status_modal(btn, close, is_open, config, runtime_session):
    if ctx.triggered_id == "dashboard-status-btn":
        # Read the status table only when someone asks (it used to be re-queried for every
        # tile on every interval tick, ~1 query/tile/second while async work ran).
        if not config or local_mode():
            return True, render_status_rows({})
        try:
            statuses = get_dashboard_statuses(
                _executing_only(config),
                runtime_session_id=(runtime_session or {}).get("runtime_session_id")
                if isinstance(runtime_session, dict) else None,
            )
        except Exception as e:  # noqa: BLE001
            return True, html.Div(f"Status is unavailable: {e}", className="text-warning")
        return True, render_status_rows(statuses)

    if ctx.triggered_id == "dashboard-status-close":
        return False, dash.no_update

    return is_open, dash.no_update


# -----------------------------------------------
# INTERVAL CONFIG
# -----------------------------------------------
_ASYNC_POLL_MS = int(os.getenv("STRATABI_ASYNC_POLL_MS", "1000"))


@callback(
    Output("dashboard-interval", "interval"),
    Output("dashboard-interval", "disabled"),
    Input("dashboard-config-store", "data"),
    Input({"type": "tile-status-store", "tile_id": ALL}, "data"),
)
def configure_interval(config, tile_statuses=None):
    if not config:
        return dash.no_update, True

    settings = config.get("settings", {})
    # Async tiles (async Athena / Lambda) only pick up completion on interval ticks. If a
    # dashboard has any async tile, auto-enable polling even when settings.interval_enabled
    # is false — otherwise the tile is stuck on "Processing…" forever. This is safe:
    # interval ticks never start new work for load_once/input tiles (only interval/always
    # tiles run on a tick, which is their intended behavior).
    has_async = any(tile_is_async(tile) for tile in config.get("layout", []))
    explicitly_enabled = settings.get("interval_enabled", False)
    enabled = explicitly_enabled or has_async
    default_ms = 5_000 if (has_async and not explicitly_enabled) else 60_000

    # Each tick fires one server round-trip per tile on the page, so a fast interval is only
    # cheap if it stops when there's nothing to wait for. When the clock exists only to poll
    # async work (no interval/always tiles), run it just while some tile is still in flight.
    timer_tiles = any(
        (tile.get("load") or {}).get("mode") in ("interval", "always")
        for tile in config.get("layout", [])
    )
    if not timer_tiles and not has_async:
        # Nothing consumes the clock (no interval/always tiles, no async work) — keep it off even
        # if settings.interval_enabled is set; ticks would just be N idle requests per second.
        return settings.get("interval_ms", default_ms), True
    if has_async and not timer_tiles:
        enabled = any(
            str(s).upper() in ACTIVE_TILE_STATUSES for s in (tile_statuses or []) if s
        )
        # Async-only clock: poll fast (default 1s) — it's only on while work is in flight, so a
        # short interval costs nothing at rest. settings.interval_ms governs timer tiles only.
        return _ASYNC_POLL_MS, not enabled
    return (
        settings.get("interval_ms", default_ms),
        not enabled,
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
    Input("url", "pathname"),
    Input("url", "search"),
    State("dashboard-selector", "value"),
    prevent_initial_call=False,
)
def populate_dashboard_selector(_, user_id, start_date, end_date, pathname, search, current_value):
    # App routes hide the selector, so don't list (and GetObject every) dashboard in S3 for it.
    # Leaving the selector untouched keeps the stores quiet; navigating back to /dashboard
    # changes the pathname, which repopulates it.
    if is_app_route(pathname):
        return dash.no_update, dash.no_update

    # list_dashboard_options honors local mode (`stratabi demo quick`): dashboards from disk.
    options = list_dashboard_options(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    if not options:
        return [], None

    values = {opt["value"] for opt in options}

    # A /dashboard/<key> URL selects that dashboard. Match the path key against an
    # option's full value or its dashboard id; setting the selector value drives the
    # existing selector -> config-store -> active-dashboard chain. Unknown keys fall
    # through to the current/default selection (ignored safely).
    path_key = parse_dashboard_key(pathname)
    if path_key:
        url_match = next(
            (
                opt["value"]
                for opt in options
                if opt["value"] == path_key or dashboard_id_from_value(opt["value"]) == path_key
            ),
            None,
        )
        if url_match:
            return options, url_match

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

def _executing_only(config: dict) -> dict:
    """Static tiles never have runs; don't query the status table for them."""
    return {**config, "layout": [t for t in config.get("layout", []) if t.get("exec")]}


@callback(
    Output("active-dashboard-key-store", "data", allow_duplicate=True),
    Input("url", "pathname"),
    Input("dashboard-selector-store", "data"),
    State("url", "search"),
    prevent_initial_call=True,
)
def sync_active_dashboard(pathname, dashboard_key, search=None):
    if pathname and pathname.startswith("/dashboard"):
        if is_app_route(pathname):
            return None
    else:
        return dash.no_update

    return dashboard_key

# -----------------------------------------------
# DASHBOARD CONTROLS
# -----------------------------------------------
_SHOW, _HIDE = {}, {"display": "none"}


@callback(
    Output("dashboard-controls-row", "hidden"),
    Output("dash-ctl-selector", "style"),
    Output("dash-ctl-refresh", "style"),
    Output("dash-ctl-status", "style"),
    Input("url", "pathname"),
    Input("dashboard-config-store", "data"),
)
def toggle_dashboard_controls(pathname, config=None):
    """Dashboards get the full toolbar. Apps hide it, except the Refresh/Status buttons a module
    opts into via module.json `ui.show_refresh` / `ui.show_status` (default off)."""
    if not (pathname and pathname.startswith("/dashboard")):
        return (dash.no_update,) * 4
    if not is_app_route(pathname):
        return False, _SHOW, _SHOW, _SHOW
    ui = (config or {}).get("_module_ui") or {}
    refresh, status = bool(ui.get("show_refresh")), bool(ui.get("show_status"))
    if not (refresh or status):
        return True, _HIDE, _HIDE, _HIDE
    return (False, _HIDE, _SHOW if refresh else _HIDE, _SHOW if status else _HIDE)

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
    Output("artifact-download-modal", "is_open", allow_duplicate=True),
    Input("artifact-download-close", "n_clicks"),
    prevent_initial_call=True,
)
def close_artifact_download_modal(_n):
    # The Close button had no callback, so the modal couldn't be dismissed. Mirror the
    # status modal's close behavior.
    if not _n:
        raise PreventUpdate
    return False


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