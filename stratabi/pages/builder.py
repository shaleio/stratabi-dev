# stratabi/pages/builder.py

import json
from dash import html, dcc, callback, Input, Output, State, register_page, no_update, clientside_callback, ctx
import dash_bootstrap_components as dbc
import re
import uuid
from dash.exceptions import PreventUpdate
import os
from datetime import datetime, timezone
from importlib.resources import files
import boto3
from botocore.exceptions import ClientError
from datetime import date

from stratabi import __version__ as STRATABI_VERSION
from ..core.s3_loader import (
    dashboard_id_from_value,
    load_dashboard_json,
    list_dashboard_options,
    save_dashboard_json,
    resolve_actor_token,
    record_dashboard_recent,
)
from ..core import ai_helpers

register_page(__name__, path="/builder")

def load_dashboard_schema():
    schema_path = files("stratabi.data.schemas").joinpath("dashboard.schema.json")
    return json.loads(schema_path.read_text())

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")


def get_system_bucket() -> str:
    bucket = os.getenv("STRATABI_SYSTEM_BUCKET")
    if not bucket:
        raise RuntimeError("STRATABI_SYSTEM_BUCKET is not set.")
    return bucket

def validate_file_label(value: str | None) -> tuple[bool, str, str]:
    """
    Returns:
      valid, normalized_label, message
    """
    if not value or not value.strip():
        return False, "", "Dashboard name is required."

    raw = value.strip()

    if "__" in raw:
        return False, raw, "Double underscores are reserved for StrataBI system metadata."

    if "--" in raw:
        return False, raw, "Double dashes are reserved for dashboard tags."

    if "  " in raw:
        return False, raw, "Use single spaces only."

    if len(raw) > 60:
        return False, raw, "Dashboard name must be 60 characters or fewer."

    # Allow letters, numbers, single spaces, and underscores.
    # No punctuation.
    if not re.fullmatch(r"[A-Za-z0-9_ ]+", raw):
        return False, raw, "Use only letters, numbers, spaces, and underscores."

    # Normalize internal whitespace.
    normalized = re.sub(r"\s+", " ", raw).strip()

    return True, normalized, ""

def validate_dashboard_tags(raw_tags: str | list[str] | None) -> tuple[bool, list[str], str]:
    """
    Returns:
      valid, normalized_tags, message
    """
    if not raw_tags:
        return True, [], ""

    if isinstance(raw_tags, str):
        if "__" in raw_tags:
            return False, [], "Double underscores are reserved for StrataBI system metadata."

        if "--" in raw_tags:
            return False, [], "Double dashes are reserved for StrataBI tag encoding."

        raw_parts = raw_tags.split(",")
    else:
        raw_parts = [str(x) for x in raw_tags]

    if len(raw_parts) > 5:
        return False, [], "Use at most 5 tags."

    tags: list[str] = []
    seen: set[str] = set()

    for raw in raw_parts:
        tag = raw.strip().lower()

        if not tag:
            continue

        if " " in tag:
            return False, tags, "Tags must be one word each. Use commas between tags."

        if "_" in tag:
            return False, tags, "Tags must be one word each. Use letters and numbers only."

        if not re.fullmatch(r"[a-z0-9]+", tag):
            return False, tags, "Tags may only contain lowercase letters and numbers."

        if len(tag) > 24:
            return False, tags, "Each tag must be 24 characters or fewer."

        if tag in seen:
            continue

        seen.add(tag)
        tags.append(tag)

    if len(tags) > 5:
        return False, tags[:5], "Use at most 5 tags."

    return True, tags, ""


def get_module_prefix() -> str:
    return os.getenv("STRATABI_MODULE_PREFIX", "analyst/modules").strip("/")


def get_module_registry_table():
    table_name = os.getenv("STRATABI_MODULE_REGISTRY_TABLE")
    if not table_name:
        return None
    return dynamodb.Table(table_name)


def scan_module_registry() -> list[dict]:
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
        items.extend(response.get("Items", []))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    return sorted(
        items,
        key=lambda x: str(x.get("label") or x.get("module_id") or "").lower()
    )


def load_module_llm_contract(module_id: str) -> str | None:
    # Reads modules/<id>/llm_context.txt (legacy llm_contract.txt fallback) from S3.
    return ai_helpers.load_module_context(module_id)


def load_llm_contract(selected_module_ids: list[str] | None = None) -> str:
    # Core contract + appended module llm_context.txt for each selected module.
    return ai_helpers.assemble_llm_context(selected_module_ids)

def layout():
    return dbc.Container(
        fluid=True,
        className="p-3",
        children=[
            html.H3("StrataBI Builder"),

            # Stores
            dcc.Store(id="builder-schema-store"),
            dcc.Store(id="builder-initial-store"),
            dcc.Store(id="builder-action-store"),
            dcc.Store(id="builder-current-s3-key-store"),
            dcc.Store(id="builder-selected-module-context-store"),
            dcc.Store(id="builder-ai-store"),
            dcc.Store(id="ai-handoff-store", storage_type="session"),

            # Hidden textarea bridge (JS writes into this; Dash reads value)
            dcc.Textarea(
                id="monaco-hidden-textarea",
                value="{}",   # ✅ allowed
                style={"display": "none"},
            ),

            dbc.Row(
                className="mb-3",
                children=[
                    dbc.Col(
                        width=4,
                        children=[
                            dbc.Card(
                                body=True,
                                children=[
                                    html.H5("Controls"),
                                    html.Br(),
                                    dcc.DatePickerRange(
                                        id='builder-date-picker-range',
                                        initial_visible_month=date.today(),
                                        className="dash-date-range",
                                    ),  
                                    html.Br(),
                                    dbc.Row(
                                        [
                                            dbc.Col([
                                                    dcc.Dropdown(
                                                        id="builder-dashboard-selector",
                                                        options=[],
                                                        value=None,
                                                        clearable=True,
                                                        className="dash-dropdown",
                                                    )
                                                ],
                                                width=12
                                            ),
                                        ]
                                ),
                                    html.Div(
                                        [
                                            html.Br(),
                                            dbc.Input(id="file_label", placeholder="file label.", type="text"),
                                            dbc.InputGroup(
                                                [
                                                    dbc.InputGroupText("Tags"),
                                                    dbc.Input(
                                                        id="dashboard-tags-input",
                                                        placeholder="Optional. Format: finance, executive, monthly",
                                                        type="text",
                                                        debounce=True,
                                                    ),
                                                ],
                                                className="mt-2",
                                            ),
                                            html.Br()
                                        ]
                                    ),
                                    html.Div(id="dashboard-tags-status", className="mt-1"),
                                    html.Br(),
                                    dbc.Checklist(
                                        options=[
                                            {"label": "Global", "value": "global"},
                                        ],
                                        value=[],
                                        id="builder-switches-input",
                                        switch=True,
                                    ),
                                    html.Hr(),
                                    html.Hr(),
                                    dbc.Button(
                                        "LLM Contract",
                                        id="builder-llm-contract-btn",
                                        color="success",
                                        className="mt-2",
                                        n_clicks=0
                                    ),
                                    dbc.Button(
                                        "⧉ Copy S3 Key",
                                        id="builder-copy-s3-key-btn",
                                        color="secondary",
                                        className="mt-2 ms-2",
                                        outline = True,
                                        n_clicks=0,
                                    ),
                                    dbc.Button(
                                        "⧉ Copy JSON",
                                        id="builder-copy-json-btn",
                                        color="secondary",
                                        className="mt-2 ms-2",
                                        outline = True,
                                        n_clicks=0,
                                    ),
                                    dbc.Button(
                                        "Module Context",
                                        id="builder-module-context-btn",
                                        color="info",
                                        className="mt-2 ms-2",
                                        n_clicks=0,
                                    ),
                                    dbc.Button(
                                        "Preview",
                                        id="builder-preview-btn",
                                        color="secondary",
                                        className="mt-2 ms-2",
                                        n_clicks=0
                                    ),
                                    dbc.Button(
                                        "Save",
                                        id="builder-save-btn",
                                        color="primary",
                                        className="mt-2 ms-2",
                                        n_clicks=0,
                                        disabled=True,
                                    ),
                                    html.Div(id="builder-save-status", className="text-muted mt-2"),
                                    html.Div(id="builder-copy-s3-status", className="small text-muted mt-2"),
                                    html.Div(id="builder-copy-json-status", className="small text-muted mt-1"),
                                    html.Hr(),
                                    html.Div(
                                        [
                                            html.Div("Notes:", className="fw-bold"),
                                            html.Div("• No live charts in builder (queries cost)."),
                                            html.Div("• Preview = layout + metadata only."),
                                            html.Div("• LLM Contract meant to be pasted into LLM Chat tool for dashboard construction.")
                                        ],
                                        className="small text-muted"
                                    )
                                ]
                            )
                        ]
                    ),

                    dbc.Col(
                        width=8,
                        children=[
                            dbc.Card(
                                body=True,
                                children=[
                                    html.Div(
                                        id="monaco-container",
                                        style={
                                            "height": "70vh",
                                            "border": "1px solid #ddd",
                                            "borderRadius": "8px"
                                        }
                                    ),
                                    html.Div(
                                        id="builder-editor-status",
                                        className="small text-muted mt-2",
                                        children="Editor: initializing…"
                                    ),
                                ]
                            )
                        ]
                    )
                ]
            ),

            # Preview modal template
            dbc.Modal(
                id="builder-preview-modal",
                is_open=False,
                size="xl",
                children=[
                    dbc.ModalHeader(dbc.ModalTitle("Preview (no render)")),
                    dbc.ModalBody(
                        html.Div(id="builder-preview-body")
                    ),
                    dbc.ModalFooter(
                        dbc.Button("Close", id="builder-preview-close", className="ms-auto")
                    )
                ]
            ),

            dbc.Modal(
                id="builder-llm-contract-modal",
                is_open=False,
                size="xl",
                scrollable=True,
                children=[
                    dbc.ModalHeader(dbc.ModalTitle("LLM Contract")),
                    dbc.ModalBody(
                        html.Pre(id="builder-llm-contract-body", style={"whiteSpace": "pre-wrap"})
                    ),
                    dbc.ModalFooter(
                        children=[
                            dbc.Button("Copy", id="builder-llm-contract-copy", className="me-auto")
                        ]
                    )
                ]
            ),
            dbc.Modal(
                id="builder-module-context-modal",
                is_open=False,
                size="lg",
                scrollable=True,
                children=[
                    dbc.ModalHeader(dbc.ModalTitle("Module LLM Context")),
                    dbc.ModalBody(
                        [
                            dbc.Alert(
                                "Selecting module context appends module-specific LLM instructions "
                                "to the core contract. This can improve module-aware generation, "
                                "but it increases token usage.",
                                color="warning",
                            ),
                            dbc.Button(
                                "Select All",
                                id="builder-module-context-select-all",
                                color="secondary",
                                size="sm",
                                className="me-2",
                                n_clicks=0,
                            ),
                            dbc.Button(
                                "Clear",
                                id="builder-module-context-clear",
                                color="secondary",
                                size="sm",
                                n_clicks=0,
                            ),
                            html.Hr(),
                            dbc.Checklist(
                                id="builder-module-context-checklist",
                                options=[],
                                value=[],
                                switch=False,
                            ),
                        ]
                    ),
                    dbc.ModalFooter(
                        dbc.Button("Done", id="builder-module-context-done", className="ms-auto")
                    ),
                ],
            ),
        ]
    )

'''Utilities'''
def is_effectively_empty(cfg: dict) -> bool:
    if not cfg:
        return True

    # Allow metadata-only drafts?
    layout = cfg.get("layout")
    if isinstance(layout, list) and len(layout) == 0:
        return True

    return False

def tags_from_identifier(identifier: str) -> str:
    if not identifier:
        return ""

    base = identifier.split("__", 1)[0]
    pieces = base.split("--")

    if len(pieces) <= 1:
        return ""

    return ", ".join(pieces[1:6])

def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")

def dashboard_tags_suffix(tags: list[str]) -> str:
    return "".join(f"--{tag}" for tag in tags[:5])

def normalize_dashboard_tags(raw_tags: str | list[str] | None) -> list[str]:
    valid, tags, _message = validate_dashboard_tags(raw_tags)
    return tags if valid else []

def safe_user_token() -> str | None:
    user = resolve_user_meta()

    if not user:
        return None

    return slugify(str(user))[:32]


def safe_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def generate_dashboard_filename(
    display_name: str,
    *,
    global_dashboard: bool = False,
    tags: str | list[str] | None = None,
) -> str:
    slug = slugify(display_name or "dashboard")
    tag_part = dashboard_tags_suffix(normalize_dashboard_tags(tags))
    ts = safe_timestamp()
    actor = resolve_actor_token()
    uid = uuid.uuid4().hex[:8]

    base = f"{slug}{tag_part}"

    if global_dashboard or not actor or actor == "anonymous":
        return f"{base}__g__{ts}__{uid}"

    return f"{base}__{ts}__{actor}__{uid}"


def resolve_user_meta() -> str | bool | None:
    """
    Returns:
      - username (str) if capture enabled AND authenticated user exists
      - False if capture enabled BUT no authenticated user
      - None if capture disabled (caller should omit field)
    """
    if os.getenv("STRATABI_CAPTURE_USER", "").lower() != "true":
        return None

    try:
        from flask_login import current_user

        if current_user and getattr(current_user, "is_authenticated", False):
            return getattr(current_user, "username", False)

    except Exception:
        pass

    return False

def build_meta(*, dashboard_id: str, label: str) -> dict:
    meta = {
        "id": dashboard_id,
        "label": label,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    user_flag = resolve_user_meta()
    if user_flag is not None:
        meta["user"] = user_flag

    return meta

def apply_meta(cfg: dict, *, dashboard_id: str, label: str) -> dict:
    cfg.pop("id", None)
    cfg["name"] = label
    cfg["version"] = STRATABI_VERSION

    return cfg


def label_from_identifier(identifier: str) -> str:
    if not identifier:
        return ""

    base = identifier.split("__", 1)[0]
    slug = base.split("--", 1)[0]

    return " ".join(
        word.capitalize()
        for word in slug.strip("_").split("_")
        if word
    )

# ----------------------------
# Load Dropdown Options
# ----------------------------

@callback(
    Output("builder-dashboard-selector", "options"),
    Output("builder-dashboard-selector", "value"),
    Input("builder-dashboard-selector", "id"),
    Input("current-user-id-store", "data"),
    Input("builder-date-picker-range", "start_date"),
    Input("builder-date-picker-range", "end_date"),
    State("builder-dashboard-selector", "value"),
)
def populate_builder_dashboard_selector(_, user_id, start_date, end_date, current_value):
    options = list_dashboard_options(
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
        (opt["value"] for opt in options if dashboard_id_from_value(opt["value"]) == "default"),
        None,
    )

    if default_value:
        return options, default_value

    return options, options[0]["value"]


# ----------------------------
# Load schema + initial JSON
# ----------------------------
@callback(
    Output("builder-schema-store", "data"),
    Output("builder-initial-store", "data"),
    Input("builder-dashboard-selector", "value"),
    State("current-user-id-store", "data"),
)
def load_builder_assets(dashboard_key: str, user_id: str | None):
    schema = load_dashboard_schema()

    if not dashboard_key:
        return schema, {}

    try:
        initial = load_dashboard_json(dashboard_key, user_id)

        try:
            record_dashboard_recent(
                user_id=user_id,
                dashboard_key=dashboard_key,
                label=initial.get("name") or initial.get("label"),
            )
        except Exception:
            pass

    except Exception as e:
        dashboard_id = dashboard_id_from_value(dashboard_key)
        initial = {
            "id": dashboard_id,
            "name": label_from_identifier(dashboard_id),
            "description": f"Error loading dashboard: {e}",
            "layout": [],
        }

    return schema, initial


# ----------------------------
# Client-side Monaco init
# ----------------------------
clientside_callback(
    """
    function(schema, initial) {
      if (!schema || !initial) {
        return window.dash_clientside.no_update;
      }

      console.log("[Dash] calling StratabiMonaco.init");

      setTimeout(() => {
        window.StratabiMonaco.init({
          schema: schema,
          initialValue: initial,
          containerId: "monaco-container"
        });
      }, 0);

      return window.dash_clientside.no_update;
    }
    """,
    Output("builder-editor-status", "children", allow_duplicate=True),
    Input("builder-schema-store", "data"),
    Input("builder-initial-store", "data"),
    prevent_initial_call='initial_duplicate'
)

clientside_callback(
    """
    function(initial) {
      if (!initial || !window.StratabiMonaco) {
        return window.dash_clientside.no_update;
      }

      // Convert object → formatted JSON
      const text = JSON.stringify(initial, null, 2);

      // Push into Monaco editor
      window.StratabiMonaco.setValue(text);

      return "Editor: loaded dashboard JSON";
    }
    """,
    Output("builder-editor-status", "children", allow_duplicate=True),
    Input("builder-initial-store", "data"),
    prevent_initial_call=True
)

clientside_callback(
    """
    function(n, text) {
        if (!n || !text) {
            return "Copy";
        }

        function fallbackCopyText(text) {
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.top = "-1000px";
            textarea.style.left = "-1000px";

            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();

            let ok = false;
            try {
                ok = document.execCommand("copy");
            } catch (err) {
                ok = false;
            }

            document.body.removeChild(textarea);
            return ok;
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text)
                .then(function() {
                    return "Copied!";
                })
                .catch(function() {
                    const ok = fallbackCopyText(text);
                    return ok ? "Copied!" : "Copy failed";
                });
        }

        const ok = fallbackCopyText(text);
        return ok ? "Copied!" : "Copy failed";
    }
    """,
    Output("builder-llm-contract-copy", "children", allow_duplicate=True),
    Input("builder-llm-contract-copy", "n_clicks"),
    State("builder-llm-contract-body", "children"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(previewClicks, saveClicks) {
        const ctx = window.dash_clientside.callback_context;

        if (!ctx.triggered || !ctx.triggered.length) {
            return window.dash_clientside.no_update;
        }

        const trigger = ctx.triggered[0].prop_id.split(".")[0];

        let text = "{}";

        if (
            window.StratabiMonaco &&
            typeof window.StratabiMonaco.getValue === "function"
        ) {
            text = window.StratabiMonaco.getValue();
        } else {
            const hidden = document.getElementById("monaco-hidden-textarea");
            if (hidden) {
                text = hidden.value || "{}";
            }
        }

        if (trigger === "builder-preview-btn") {
            return {
                action: "preview",
                text: text,
                ts: Date.now()
            };
        }

        if (trigger === "builder-save-btn") {
            return {
                action: "save",
                text: text,
                ts: Date.now()
            };
        }

        return window.dash_clientside.no_update;
    }
    """,
    Output("builder-action-store", "data"),
    Input("builder-preview-btn", "n_clicks"),
    Input("builder-save-btn", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(n, currentKey) {
        if (!n) {
            return window.dash_clientside.no_update;
        }

        if (!currentKey) {
            return "No S3 key available yet.";
        }

        function fallbackCopyText(text) {
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.top = "-1000px";
            textarea.style.left = "-1000px";

            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();

            let ok = false;
            try {
                ok = document.execCommand("copy");
            } catch (err) {
                ok = false;
            }

            document.body.removeChild(textarea);
            return ok;
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(currentKey)
                .then(function() {
                    return "Copied S3 key.";
                })
                .catch(function() {
                    const ok = fallbackCopyText(currentKey);
                    return ok ? "Copied S3 key." : "Copy failed.";
                });
        }

        const ok = fallbackCopyText(currentKey);
        return ok ? "Copied S3 key." : "Copy failed. Browser blocked clipboard access.";
    }
    """,
    Output("builder-copy-s3-status", "children"),
    Input("builder-copy-s3-key-btn", "n_clicks"),
    State("builder-current-s3-key-store", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(n) {
        if (!n) {
            return window.dash_clientside.no_update;
        }

        let text = "{}";

        if (
            window.StratabiMonaco &&
            typeof window.StratabiMonaco.getValue === "function"
        ) {
            text = window.StratabiMonaco.getValue();
        } else {
            const hidden = document.getElementById("monaco-hidden-textarea");
            if (hidden) {
                text = hidden.value || "{}";
            }
        }

        function fallbackCopyText(text) {
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.top = "-1000px";
            textarea.style.left = "-1000px";

            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();

            let ok = false;
            try {
                ok = document.execCommand("copy");
            } catch (err) {
                ok = false;
            }

            document.body.removeChild(textarea);
            return ok;
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text)
                .then(function() {
                    return "Copied dashboard JSON.";
                })
                .catch(function() {
                    const ok = fallbackCopyText(text);
                    return ok ? "Copied dashboard JSON." : "Copy failed.";
                });
        }

        const ok = fallbackCopyText(text);
        return ok ? "Copied dashboard JSON." : "Copy failed. Browser blocked clipboard access.";
    }
    """,
    Output("builder-copy-json-status", "children"),
    Input("builder-copy-json-btn", "n_clicks"),
    prevent_initial_call=True,
)

# ----------------------------
# Preview modal logic (no charts)
# ----------------------------
@callback(
    Output("builder-preview-modal", "is_open"),
    Output("builder-preview-body", "children"),
    Input("builder-action-store", "data"),
    Input("builder-preview-close", "n_clicks"),
    State("builder-preview-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_preview(action_data, close_clicks, is_open):
    trigger = ctx.triggered_id

    if trigger == "builder-preview-close":
        return False, no_update

    if trigger != "builder-action-store":
        return is_open, no_update

    if not action_data or action_data.get("action") != "preview":
        return is_open, no_update

    raw_text = action_data.get("text") or ""

    if not raw_text.strip():
        return True, dbc.Alert("No JSON captured from editor yet.", color="warning")

    try:
        cfg = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return True, dbc.Alert(f"Invalid JSON: {e}", color="danger")

    layout = cfg.get("layout", [])
    if not isinstance(layout, list):
        return True, dbc.Alert("`layout` must be a list.", color="danger")

    items = []
    for tile in layout:
        tid = tile.get("id", "(no id)")
        ttype = tile.get("block", {}).get("type", "(no block type)")
        title = tile.get("title", "")
        pos = tile.get("position", {})

        items.append(
            dbc.ListGroupItem(
                [
                    html.Div(f"{tid}  •  {ttype}", className="fw-bold"),
                    html.Div(title, className="text-muted") if title else None,
                    html.Div(f"pos: {pos}", className="small text-muted"),
                ]
            )
        )

    body = html.Div(
        [
            dbc.Alert("Preview shows structure only. No queries are executed.", color="info"),
            dbc.ListGroup(items) if items else dbc.Alert("No tiles in layout.", color="warning"),
        ]
    )

    return True, body


# ----------------------------
# Save stub (wire later to S3)
# ----------------------------

@callback(
    Output("builder-save-status", "children", allow_duplicate=True),
    Output("builder-current-s3-key-store", "data"),
    Input("builder-action-store", "data"),
    State("file_label", "value"),
    State("builder-switches-input", "value"),
    State("dashboard-tags-input", "value"),
    State("current-user-id-store", "data"),
    State("builder-current-s3-key-store", "data"),
    prevent_initial_call=True
)
def save_dashboard_to_s3(action_data, file_label, switches, tags, user, current_key):
    if not action_data or action_data.get("action") != "save":
        raise PreventUpdate

    raw_text = action_data.get("text") or ""
    switches = switches or []

    actor = resolve_actor_token()

    is_global = "global" in switches

    if not actor or actor == "anonymous":
        is_global = True

    label_valid, normalized_label, label_message = validate_file_label(file_label)
    if not label_valid:
        return dbc.Alert(label_message, color="warning", dismissable=True), no_update

    tags_valid, normalized_tags, tags_message = validate_dashboard_tags(tags)
    if not tags_valid:
        return dbc.Alert(tags_message, color="warning", dismissable=True), no_update

    if not raw_text.strip():
        return dbc.Alert("Nothing to save yet.", color="warning", dismissable=True), no_update

    if not file_label:
        return dbc.Alert("No dashboard file label.", color="warning", dismissable=True), no_update

    try:
        dashboard_id = generate_dashboard_filename(
            normalized_label,
            global_dashboard=is_global,
            tags=normalized_tags,
        )

        parsed_raw = json.loads(raw_text)

        if is_effectively_empty(parsed_raw):
            return (dbc.Alert(
                "Dashboard is empty (no layout defined). Nothing to save.",
                color="warning",
                dismissable=True,
            ), no_update)

        parsed = apply_meta(
            parsed_raw,
            dashboard_id=dashboard_id,
            label=normalized_label,
        )

        key = save_dashboard_json(
            dashboard_id,
            parsed,
            user_id=user,
            global_dashboard=is_global,
            existing_key=current_key,
        )


        return (
            dbc.Alert(
                f"Dashboard saved to s3://{os.getenv('STRATABI_SYSTEM_BUCKET')}/{key}",
                color="success",
                dismissable=True,
            ),
            key,
        )

    except json.JSONDecodeError as e:
        return dbc.Alert(f"Invalid JSON: {e}", color="danger", dismissable=True), no_update

    except Exception as e:
        return dbc.Alert(f"Save failed: {e}", color="danger", dismissable=True), no_update


@callback(
    Output("builder-current-s3-key-store", "data", allow_duplicate=True),
    Input("builder-dashboard-selector", "value"),
    prevent_initial_call=True,
)
def sync_copy_key_from_selector(dashboard_key):
    return dashboard_key

@callback(
    Output("file_label", "value"),
    Output("dashboard-tags-input", "value"),
    Input("builder-dashboard-selector", "value"),
    prevent_initial_call=True,
)
def populate_file_name_input(dashboard_key):
    dashboard_id = dashboard_id_from_value(dashboard_key)
    return label_from_identifier(dashboard_id), tags_from_identifier(dashboard_id)


@callback(
    Output("builder-llm-contract-copy", "children", allow_duplicate=True),
    Input("builder-llm-contract-btn", "n_clicks"),
    prevent_initial_call=True
)
def reset_copy_text(open_clicks):
    return "Copy"


@callback(
    Output("active-dashboard-id-store", "data", allow_duplicate=True),
    Input("builder-dashboard-selector", "value"),
    prevent_initial_call=True
)
def sync_active_dashboard(dashboard_key):
    return dashboard_key


@callback(
    Output("builder-module-context-modal", "is_open"),
    Output("builder-module-context-checklist", "options"),
    Output("builder-module-context-checklist", "value"),
    Input("builder-module-context-btn", "n_clicks"),
    Input("builder-module-context-done", "n_clicks"),
    State("builder-module-context-modal", "is_open"),
    State("builder-selected-module-context-store", "data"),
    prevent_initial_call=True,
)
def toggle_module_context_modal(open_clicks, done_clicks, is_open, selected_ids):
    trigger = ctx.triggered_id

    if trigger == "builder-module-context-done":
        return False, no_update, no_update

    if trigger != "builder-module-context-btn":
        return is_open, no_update, no_update

    modules = scan_module_registry()

    options = []
    for module in modules:
        module_id = module.get("module_id")
        if not module_id:
            continue

        label = module.get("label") or module_id
        module_type = module.get("module_type", "module")
        version = module.get("version", "")

        options.append(
            {
                "label": f"{label} ({module_type}{', ' + version if version else ''})",
                "value": module_id,
            }
        )

    return True, options, selected_ids or []


@callback(
    Output("builder-module-context-checklist", "value", allow_duplicate=True),
    Input("builder-module-context-select-all", "n_clicks"),
    Input("builder-module-context-clear", "n_clicks"),
    State("builder-module-context-checklist", "options"),
    prevent_initial_call=True,
)
def select_or_clear_module_context(select_all_clicks, clear_clicks, options):
    trigger = ctx.triggered_id

    if trigger == "builder-module-context-clear":
        return []

    if trigger == "builder-module-context-select-all":
        return [opt["value"] for opt in options or []]

    raise PreventUpdate

@callback(
    Output("builder-copy-s3-status", "children", allow_duplicate=True),
    Input("builder-current-s3-key-store", "data"),
    prevent_initial_call=True,
)
def reset_copy_s3_status(_current_key):
    return ""

@callback(
    Output("builder-copy-json-status", "children", allow_duplicate=True),
    Input("builder-initial-store", "data"),
    prevent_initial_call=True,
)
def reset_copy_json_status(_initial):
    return ""

@callback(
    Output("builder-selected-module-context-store", "data"),
    Input("builder-module-context-checklist", "value"),
)
def persist_selected_module_context(selected_ids):
    return selected_ids or []

@callback(
    Output("builder-llm-contract-modal", "is_open"),
    Output("builder-llm-contract-body", "children"),
    Input("builder-llm-contract-btn", "n_clicks"),
    State("builder-llm-contract-modal", "is_open"),
    State("builder-selected-module-context-store", "data"),
    prevent_initial_call=True,
)
def toggle_llm_contract(open_clicks, is_open, selected_module_ids):
    if not ctx.triggered:
        return is_open, no_update

    if ctx.triggered_id == "builder-llm-contract-btn":
        text = load_llm_contract(selected_module_ids)
        return True, text

    return is_open, no_update


@callback(
    Output("builder-save-btn", "disabled"),
    Output("dashboard-tags-status", "children"),
    Input("file_label", "value"),
    Input("dashboard-tags-input", "value"),
)
def validate_builder_save_inputs(file_label, raw_tags):
    label_valid, _normalized_label, label_message = validate_file_label(file_label)
    tags_valid, normalized_tags, tags_message = validate_dashboard_tags(raw_tags)

    if not label_valid:
        return True, dbc.Alert(
            label_message,
            color="warning",
            className="py-1 px-2 small mb-0",
        )

    if not tags_valid:
        return True, dbc.Alert(
            tags_message,
            color="warning",
            className="py-1 px-2 small mb-0",
        )

    if normalized_tags:
        return False, dbc.Alert(
            f"Ready. Tags: {', '.join(normalized_tags)}",
            color="info",
            className="py-1 px-2 small mb-0",
        )

    return False, dbc.Alert(
        "Ready.",
        color="info",
        className="py-1 px-2 small mb-0",
    )