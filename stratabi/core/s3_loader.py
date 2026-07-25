# stratabi/core/s3_loader.py

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta, date
from io import BytesIO, StringIO
from typing import Any
import boto3
import pandas as pd
import base64
from urllib.parse import urlparse

from boto3.dynamodb.conditions import Key
from dash import html

from stratabi.core.config import config


logger = logging.getLogger(__name__)

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")


# ---------------------------------------------------------------------
# Environment / core config
# ---------------------------------------------------------------------

def get_system_bucket() -> str:
    bucket = os.getenv("STRATABI_SYSTEM_BUCKET") or getattr(config, "BUCKET", None)
    if not bucket:
        raise RuntimeError("STRATABI_SYSTEM_BUCKET is not configured.")
    return bucket


def get_dashboard_prefix() -> str:
    return os.getenv(
        "STRATABI_DASHBOARD_PREFIX",
        getattr(config, "DASHBOARD_PREFIX", "analyst/dashboards"),
    ).strip("/")


def get_module_prefix() -> str:
    return os.getenv("STRATABI_MODULE_PREFIX", "analyst/modules").strip("/")


def current_year_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y_%m")

def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _get_table(env_var_name: str):
    table_name = os.getenv(env_var_name)
    if not table_name:
        return None
    return dynamodb.Table(table_name)

def parse_s3_location(location: str, default_bucket: str | None = None) -> tuple[str, str]:
    """
    Accept either:
      - s3://bucket/key
      - key/inside/default/bucket

    Returns:
      (bucket, key)
    """

    if not location:
        raise ValueError("S3 location is required.")

    if location.startswith("s3://"):
        parsed = urlparse(location)

        bucket = parsed.netloc
        key = parsed.path.lstrip("/")

        if not bucket or not key:
            raise ValueError(f"Invalid S3 URI: {location}")

        return bucket, key

    bucket = default_bucket or get_system_bucket()
    key = location.lstrip("/")

    if not bucket:
        raise ValueError("No default S3 bucket configured.")

    if not key:
        raise ValueError("S3 key is required.")

    return bucket, key


def s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key.lstrip('/')}"

# ---------------------------------------------------------------------
# Generic S3 loaders
# ---------------------------------------------------------------------

def load_json_from_s3(location: str, bucket: str | None = None) -> dict[str, Any]:
    resolved_bucket, key = parse_s3_location(location, bucket)
    obj = s3.get_object(Bucket=resolved_bucket, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))


def load_text_from_s3(location: str, bucket: str | None = None) -> str:
    resolved_bucket, key = parse_s3_location(location, bucket)
    obj = s3.get_object(Bucket=resolved_bucket, Key=key)
    return obj["Body"].read().decode("utf-8")


def load_bytes_from_s3(location: str, bucket: str | None = None) -> bytes:
    resolved_bucket, key = parse_s3_location(location, bucket)
    obj = s3.get_object(Bucket=resolved_bucket, Key=key)
    return obj["Body"].read()


def load_dataframe_from_s3(location: str, bucket: str | None = None):
    resolved_bucket, key = parse_s3_location(location, bucket)
    obj = s3.get_object(Bucket=resolved_bucket, Key=key)

    lower_key = key.lower()

    if lower_key.endswith(".csv"):
        return pd.read_csv(StringIO(obj["Body"].read().decode("utf-8")))

    if lower_key.endswith(".parquet"):
        return pd.read_parquet(BytesIO(obj["Body"].read()))

    raise ValueError(f"Unsupported dataframe format for S3 location: {s3_uri(resolved_bucket, key)}")


def load_markdown_from_s3(location: str, bucket: str | None = None) -> str:
    return load_text_from_s3(location, bucket)


def load_html_from_s3(location: str, bucket: str | None = None) -> str:
    return load_text_from_s3(location, bucket)


def load_image_data_uri_from_s3(location: str, bucket: str | None = None) -> str:
    resolved_bucket, key = parse_s3_location(location, bucket)
    raw = load_bytes_from_s3(key, resolved_bucket)

    lower_key = key.lower()

    if lower_key.endswith(".png"):
        mime = "image/png"
    elif lower_key.endswith(".jpg") or lower_key.endswith(".jpeg"):
        mime = "image/jpeg"
    elif lower_key.endswith(".webp"):
        mime = "image/webp"
    elif lower_key.endswith(".svg"):
        mime = "image/svg+xml"
    else:
        mime = "application/octet-stream"

    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"

# ---------------------------------------------------------------------
# Main Result Loader
# ---------------------------------------------------------------------

def load_result_from_status(status: dict):
    result_kind = status.get("result_kind")
    result_format = status.get("result_format")
    result_s3_key = status.get("result_s3_key")

    # For status-driven runtime artifacts, default bucket should come from
    # status_context/system_bucket first, then environment system bucket.
    result_bucket = status.get("system_bucket") or get_system_bucket()

    if not result_s3_key:
        return {
            "status": "failed",
            "message": "Status is missing result_s3_key.",
        }

    if result_kind == "dataframe":
        return load_dataframe_from_s3(result_s3_key, bucket=result_bucket)

    if result_format == "json":
        return load_json_from_s3(result_s3_key, bucket=result_bucket)

    if result_format == "md":
        return load_markdown_from_s3(result_s3_key, bucket=result_bucket)

    if result_format == "html":
        return load_html_from_s3(result_s3_key, bucket=result_bucket)

    if result_format in {"png", "jpg", "jpeg", "webp", "svg"}:
        return {
            "status": "succeeded",
            "result_kind": result_kind or "artifact",
            "result_format": result_format,
            "result_s3_key": result_s3_key,
            "system_bucket": result_bucket,
            "data_uri": load_image_data_uri_from_s3(result_s3_key, bucket=result_bucket),
        }

    return {
        "status": "succeeded",
        "result_kind": result_kind,
        "result_format": result_format,
        "result_s3_key": result_s3_key,
        "system_bucket": result_bucket,
    }


def load_result_from_s3(result_s3_location: str, bucket: str | None = None):
    """
    Direct cache loader.

    Accepts:
      - s3://external-bucket/path/file.parquet
      - runtime/test/file.parquet, defaulting to system bucket
    """

    resolved_bucket, key = parse_s3_location(result_s3_location, bucket)
    lower_key = key.lower()
    resolved_location = s3_uri(resolved_bucket, key)

    if lower_key.endswith((".parquet", ".csv")):
        return load_dataframe_from_s3(key, bucket=resolved_bucket)

    if lower_key.endswith(".json"):
        return load_json_from_s3(key, bucket=resolved_bucket)

    if lower_key.endswith((".md", ".markdown")):
        return load_markdown_from_s3(key, bucket=resolved_bucket)

    if lower_key.endswith((".html", ".htm")):
        return load_html_from_s3(key, bucket=resolved_bucket)

    if lower_key.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")):
        return {
            "status": "succeeded",
            "result_s3_key": key,
            "result_s3_uri": resolved_location,
            "system_bucket": resolved_bucket,
            "data_uri": load_image_data_uri_from_s3(key, bucket=resolved_bucket),
        }

    return {
        "status": "succeeded",
        "result_s3_key": key,
        "result_s3_uri": resolved_location,
        "system_bucket": resolved_bucket,
    }

# ---------------------------------------------------------------------
# Dashboard identity / paths
# ---------------------------------------------------------------------

def dashboard_id_from_key(key: str) -> str:
    """
    Return filename stem from an S3 dashboard key.

    Example:
      analyst/dashboards/2026_05/users/alex/foo__20260505T...json
      -> foo__20260505T...
    """
    return key.rsplit("/", 1)[-1].removesuffix(".json")


def dashboard_key_is_default(key: str | None) -> bool:
    return bool(key) and key.rstrip("/") == default_dashboard_key()


def dashboard_id_from_value(value: str | None) -> str:
    if not value:
        return "default"

    if "/" in value:
        return dashboard_id_from_key(value)

    return value.removesuffix(".json")

def _find_dashboard_key(
    dashboard_id: str,
    user_id: str | None = None,
    *,
    s3_key: str | None = None,
) -> str:
    if s3_key:
        return s3_key

    bucket = get_system_bucket()
    dashboard_id = (dashboard_id or "default").removesuffix(".json")

    if dashboard_id == "default":
        key = default_dashboard_key()
        s3.head_object(Bucket=bucket, Key=key)
        return key

    # Fast path: derive month from filename timestamp.
    meta = parse_dashboard_identifier(dashboard_id)
    ts = meta.get("timestamp")
    months = [ts.strftime("%Y_%m")] if ts else default_dashboard_months(3)

    actor = _coerce_actor(user_id)

    candidate_prefixes = []
    for month in months:
        candidate_prefixes.append(dashboard_prefix_for_month_scope(month, "global"))
        if actor != "anonymous":
            candidate_prefixes.append(dashboard_prefix_for_month_scope(month, f"users/{actor}"))

    filename = f"{dashboard_id}.json"

    for prefix in candidate_prefixes:
        key = f"{prefix}{filename}"
        try:
            s3.head_object(Bucket=bucket, Key=key)
            return key
        except Exception:
            pass

    # Last-resort recursive lookup. Keep this for migration/backward compatibility.
    prefix = f"{get_dashboard_prefix().rstrip('/')}/"
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.rsplit("/", 1)[-1] == filename:
                return key

    raise FileNotFoundError(f"Dashboard not found in S3: {dashboard_id}")


def is_global_dashboard_id(dashboard_id: str) -> bool:
    return dashboard_id == "default" or "__g__" in dashboard_id


def dashboard_matches_actor(dashboard_id: str, actor: str | None) -> bool:
    if not actor or actor == "anonymous":
        return False

    return f"__{actor}__" in dashboard_id


def dashboard_visible_to_user(dashboard_id: str, user_id: str | None) -> bool:
    """
    MVP visibility rule.

    Visible:
      - default
      - global dashboards
      - dashboards owned by the current user

    Hidden:
      - dashboards owned by other users
    """
    if dashboard_id == "default":
        return True

    if is_global_dashboard_id(dashboard_id):
        return True

    if user_id and user_id != "anonymous":
        return dashboard_matches_actor(dashboard_id, user_id)

    return False

def parse_slug_and_tags(slug_part: str) -> tuple[str, list[str]]:
    pieces = slug_part.split("--") if slug_part else [""]

    slug = pieces[0]
    tags = [
        slugify(piece)[:24]
        for piece in pieces[1:]
        if slugify(piece)
    ]

    return slug, tags[:5]

def parse_dashboard_identifier(identifier: str) -> dict[str, Any]:
    parts = identifier.split("__") if identifier else []

    slug_part = parts[0] if parts else ""
    slug, tags = parse_slug_and_tags(slug_part)

    is_global = identifier == "default" or "g" in parts

    timestamp = None
    for part in parts:
        try:
            timestamp = datetime.strptime(part, "%Y%m%dT%H%M%SZ")
            break
        except ValueError:
            continue

    display_name = " ".join(
        word.capitalize()
        for word in slug.strip("_").split("_")
        if word
    )

    return {
        "display_name": display_name or identifier,
        "tags": tags,
        "is_global": is_global,
        "timestamp": timestamp,
    }


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


def _display_name_from_config(
    dashboard_id: str,
    cfg: dict[str, Any] | None = None,
) -> str:
    if isinstance(cfg, dict):
        name = cfg.get("name") or cfg.get("label")
        if isinstance(name, str) and name.strip():
            return name.strip()

    return label_from_identifier(dashboard_id)


def dashboard_search_text(
    dashboard_id: str,
    cfg: dict[str, Any] | None = None,
    *,
    is_pinned: bool = False,
    is_favorite: bool = False,
    is_recent: bool = False,
) -> str:
    """
    Search text for dcc.Dropdown.

    Includes symbolic tokens:
      ! -> pinned
      * -> favorite
      # -> recent
    """
    meta = parse_dashboard_identifier(dashboard_id)
    display_name = _display_name_from_config(dashboard_id, cfg)

    parts = [display_name, dashboard_id]

    if is_pinned:
        parts.extend(["!", "pinned", "pin"])

    if is_favorite:
        parts.extend(["*", "favorite", "star"])

    if is_recent:
        parts.extend(["#", "recent", "clock"])

    if meta["is_global"]:
        parts.extend(["G", "global"])

    if meta["timestamp"]:
        parts.append(meta["timestamp"].strftime("%Y-%m-%d %H:%M UTC"))

    try:
        tags = meta.get("tags", [])
        parts.extend(tags)
        parts.extend([f"tag:{tag}" for tag in tags])
    except:
        pass

    return " ".join(parts)


def dashboard_dropdown_label(
    dashboard_id: str,
    cfg: dict[str, Any] | None = None,
    *,
    is_pinned: bool = False,
    is_favorite: bool = False,
    is_recent: bool = False,
):
    """
    Rich Dash dropdown label.

    value remains dashboard_id.
    label becomes a component with visual badges.
    search should be provided separately.
    """
    meta = parse_dashboard_identifier(dashboard_id)
    display_name = _display_name_from_config(dashboard_id, cfg)

    children: list[Any] = []

    if is_pinned:
        children.append(
            html.Span("📌", className="me-1", title="Pinned dashboard")
        )
    elif is_favorite:
        children.append(
            html.Span("⭐", className="me-1", title="Favorite dashboard")
        )
    elif is_recent:
        children.append(
            html.Span("🕘", className="me-1", title="Recent dashboard")
        )

    children.append(html.Span(display_name, className="me-2"))

    if meta["is_global"]:
        children.append(
            html.Span(
                "G",
                className="badge rounded-pill bg-info text-dark me-1",
                title="Global dashboard",
            )
        )
    
    for tag in meta.get("tags", []):
        children.append(
            html.Span(
                tag,
                className="badge rounded-pill bg-secondary text-light me-1",
                title=f"Tag: {tag}",
            )
        )

    if meta["timestamp"]:
        children.append(
            html.Span(
                meta["timestamp"].strftime("%Y-%m-%d %H:%M UTC"),
                className="badge rounded-pill bg-light text-dark",
                title="Saved timestamp",
            )
        )

    return html.Span(
        children,
        className="d-inline-flex align-items-center gap-1",
    )


def _coerce_actor(user_id: str | None = None) -> str:
    actor = user_id or resolve_actor_token()
    actor = slugify(str(actor or "anonymous"))[:32]
    return actor or "anonymous"


def _scope_prefix_for_save(*, global_dashboard: bool, user_id: str | None = None) -> str:
    if global_dashboard:
        return "global"

    actor = _coerce_actor(user_id)
    if actor == "anonymous":
        return "global"

    return f"users/{actor}"


def dashboard_month_from_dt(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y_%m")


def dashboard_prefix_for_month_scope(month: str, scope_prefix: str) -> str:
    return f"{get_dashboard_prefix()}/{month}/{scope_prefix}/"


def default_dashboard_key() -> str:
    return f"{get_dashboard_prefix()}/default.json"


def _dashboard_key_for_new_save(
    dashboard_id: str,
    *,
    user_id: str | None = None,
    global_dashboard: bool = False,
) -> str:
    filename = dashboard_id if dashboard_id.endswith(".json") else f"{dashboard_id}.json"
    month = dashboard_month_from_dt()
    scope_prefix = _scope_prefix_for_save(
        global_dashboard=global_dashboard,
        user_id=user_id,
    )
    return f"{dashboard_prefix_for_month_scope(month, scope_prefix)}{filename}"

# ---------------------------------------------------------------------
# Overlay Helper
# ---------------------------------------------------------------------

def _overlay_item_to_dashboard_option(item: dict[str, Any]) -> dict[str, Any] | None:
    dashboard_key = item.get("dashboard_key") or item.get("s3_key")
    dashboard_id = item.get("dashboard_id")

    if dashboard_key:
        dashboard_id = dashboard_id or dashboard_id_from_key(dashboard_key)
        value = dashboard_key
    elif dashboard_id:
        # Migration fallback for old simple overlay rows.
        value = dashboard_id
    else:
        return None

    cfg_meta = {
        "name": item.get("label") or item.get("name"),
        "label": item.get("label") or item.get("name"),
    }

    return {
        "label": _display_name_from_config(dashboard_id, cfg_meta),
        "value": value,
        "dashboard_id": dashboard_id,
        "search": dashboard_search_text(dashboard_id, cfg_meta),
        "s3_key": dashboard_key,
        "last_modified": None,
        "cfg_meta": cfg_meta,
        "from_overlay": True,
    }

# ---------------------------------------------------------------------
# Actor / identity
# ---------------------------------------------------------------------

def resolve_actor_token() -> str:
    """
    Best-effort actor identifier for dashboard save filenames.

    Not guaranteed to be a human user unless auth is configured.
    """
    try:
        from flask_login import current_user

        if current_user and getattr(current_user, "is_authenticated", False):
            value = (
                getattr(current_user, "username", None)
                or getattr(current_user, "email", None)
                or getattr(current_user, "id", None)
            )
            if value:
                return slugify(str(value))[:32]
    except Exception:
        pass

    try:
        from flask import request

        for header in [
            "X-Forwarded-User",
            "X-Authenticated-User",
            "X-User",
            "X-Email",
        ]:
            value = request.headers.get(header)
            if value:
                return slugify(value)[:32]

        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "anonymous")
        ip = ip.split(",")[0].strip()
        return slugify(ip)[:32]

    except Exception:
        return "anonymous"
    
# ---------------------------------------------------------------------
# Date Helpers
# ---------------------------------------------------------------------
    
def dashboard_in_date_range(
    dashboard_id: str,
    *,
    start: date | None,
    end: date | None,
) -> bool:
    """
    Return True if the dashboard_id timestamp falls within the date range.

    Uses the timestamp encoded in the dashboard filename, not S3 LastModified.
    If no timestamp can be parsed, allow the dashboard through so older/default
    artifacts do not disappear unexpectedly.
    """
    if not start or not end:
        return True

    meta = parse_dashboard_identifier(dashboard_id)
    ts = meta.get("timestamp")

    if not ts:
        return True

    ts_date = ts.date()
    lo, hi = (start, end) if start <= end else (end, start)

    return lo <= ts_date <= hi
    

def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def months_between(start: date, end: date) -> list[str]:
    if start > end:
        start, end = end, start

    months: list[str] = []
    cursor = date(start.year, start.month, 1)
    end_month = date(end.year, end.month, 1)

    while cursor <= end_month:
        months.append(cursor.strftime("%Y_%m"))

        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    return months

def months_for_previous_days(days: int = 90) -> list[str]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    return months_between(start, end)

def dashboard_prefixes_for_user_months(
    *,
    user_id: str | None,
    months: list[str],
) -> list[str]:
    actor = _coerce_actor(user_id)

    prefixes: list[str] = []

    for month in months:
        prefixes.append(dashboard_prefix_for_month_scope(month, "global"))

        if actor != "anonymous":
            prefixes.append(dashboard_prefix_for_month_scope(month, f"users/{actor}"))

    return prefixes

def default_dashboard_months(window_months: int = 3) -> list[str]:
    today = datetime.now(timezone.utc).date()
    cursor = date(today.year, today.month, 1)

    months: list[str] = []
    for _ in range(window_months):
        months.append(cursor.strftime("%Y_%m"))

        if cursor.month == 1:
            cursor = date(cursor.year - 1, 12, 1)
        else:
            cursor = date(cursor.year, cursor.month - 1, 1)

    return months


# ---------------------------------------------------------------------
# Dashboard JSON load/save
# ---------------------------------------------------------------------

def load_dashboard_json(
    dashboard_key: str | None = None,
    user: str | None = None,
) -> dict[str, Any]:
    """
    Load dashboard JSON from S3.

    New behavior:
      - dashboard_key is normally the full S3 key from the dropdown.
      - None/default loads analyst/dashboards/default.json.
      - old dashboard_id values still resolve through _find_dashboard_key.
    """
    value = dashboard_key or "default"
    bucket = get_system_bucket()

    if value == "default":
        key = default_dashboard_key()
    elif "/" in value:
        key = value
    else:
        # Migration fallback.
        key = _find_dashboard_key(value, user)

    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")

    return json.loads(body)


# ---------------------------------------------------------------------
# Git registry overlay: the set of dashboards version-controlled via git
# (the StrataCLI `dashboards` commands scan this table). GLOBAL/DASHBOARD#<key>
# overlay shape. No UI in the developer edition — register via the CLI.
# ---------------------------------------------------------------------
def is_dashboard_git_registered(dashboard_key: str) -> bool:
    table = _get_table("STRATABI_DASHBOARD_GIT_REGISTRY")
    if table is None or not dashboard_key:
        return False

    try:
        resp = table.get_item(
            Key={
                "pk": "GLOBAL",
                "sk": f"DASHBOARD#{dashboard_key}",
            }
        )
        return "Item" in resp
    except Exception:
        return False


def put_dashboard_git_registered(
    dashboard_key: str,
    *,
    label: str | None = None,
    registered_by: str | None = None,
) -> None:
    table = _get_table("STRATABI_DASHBOARD_GIT_REGISTRY")
    if table is None:
        raise RuntimeError("STRATABI_DASHBOARD_GIT_REGISTRY is not configured.")

    dashboard_id = dashboard_id_from_value(dashboard_key)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    item = {
        "pk": "GLOBAL",
        "sk": f"DASHBOARD#{dashboard_key}",
        "dashboard_key": dashboard_key,
        "s3_key": dashboard_key,
        "dashboard_id": dashboard_id,
        "registered_at": now,
    }

    if label:
        item["label"] = label
    if registered_by:
        item["registered_by"] = registered_by

    table.put_item(Item=item)


def delete_dashboard_git_registered(dashboard_key: str) -> None:
    table = _get_table("STRATABI_DASHBOARD_GIT_REGISTRY")
    if table is None:
        return

    table.delete_item(
        Key={
            "pk": "GLOBAL",
            "sk": f"DASHBOARD#{dashboard_key}",
        }
    )


def list_dashboard_git_registered() -> list[dict[str, Any]]:
    """All git-registered dashboards (what the StrataCLI version-controls)."""
    table = _get_table("STRATABI_DASHBOARD_GIT_REGISTRY")
    if table is None:
        return []
    return _query_dashboard_overlay_items(table, pk_value="GLOBAL")


def save_dashboard_json(
    dashboard_id: str,
    dashboard_config: dict[str, Any],
    user_id: str | None = None,
    *,
    global_dashboard: bool = False,
    existing_key: str | None = None,
) -> str:
    bucket = get_system_bucket()

    # Git-managed identity is stable: if the dashboard being edited is registered
    # for git, overwrite its existing artifact in place rather than minting a new
    # timestamped/uuid key. Otherwise keep the create-new-artifact behavior.
    if existing_key and is_dashboard_git_registered(existing_key):
        key = existing_key
    else:
        key = _dashboard_key_for_new_save(
            dashboard_id,
            user_id=user_id,
            global_dashboard=global_dashboard,
        )

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(dashboard_config, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    return key

# ---------------------------------------------------------------------
# Module JSON
# ---------------------------------------------------------------------

def load_module_json(module_id: str) -> dict[str, Any]:
    bucket = get_system_bucket()
    key = f"{get_module_prefix()}/{module_id}/module.json"

    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))


# ---------------------------------------------------------------------
# S3 dashboard listing
# ---------------------------------------------------------------------

def _try_load_dashboard_name(bucket: str, key: str) -> dict[str, Any] | None:
    """
    Lightweight metadata load for dropdown labels.

    For MVP this reads the JSON object and extracts name/label.
    If this gets slow later, replace with S3 object metadata or a registry table.
    """
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        cfg = json.loads(obj["Body"].read().decode("utf-8"))

        return {
            "name": cfg.get("name"),
            "label": cfg.get("label"),
        }
    except Exception:
        return None


def _list_s3_dashboard_options_for_prefix(
    bucket: str,
    prefix: str,
) -> list[dict[str, Any]]:
    """
    List dashboard JSON files for a single S3 prefix.

    Dropdown value is the S3 key. The filename stem remains dashboard_id
    for parsing labels/tags/timestamps.
    """
    options: list[dict[str, Any]] = []
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            if key.endswith("/") or not key.endswith(".json"):
                continue

            dashboard_id = dashboard_id_from_key(key)
            cfg_meta = _try_load_dashboard_name(bucket, key)

            options.append(
                {
                    "label": _display_name_from_config(dashboard_id, cfg_meta),
                    "value": key,  # canonical artifact identity
                    "dashboard_id": dashboard_id,
                    "search": dashboard_search_text(dashboard_id, cfg_meta),
                    "s3_key": key,
                    "last_modified": obj.get("LastModified"),
                    "cfg_meta": cfg_meta,
                }
            )

    return options

# ---------------------------------------------------------------------
# Dynamo overlays: favorites, pinned, recents
# ---------------------------------------------------------------------


def _query_recent_dashboard_keys(
    table,
    user_id: str,
    limit: int = 50,
    deduped_limit: int = 25,
) -> list[str]:
    """
    Recents model, new key-first shape:
      pk = USER#alex
      sk = RECENT#2026-04-30T22:30:00Z#<dashboard_key>
      dashboard_key = analyst/dashboards/2026_05/users/alex/foo.json

    Migration fallback:
      old rows may only have dashboard_id.
    """
    if table is None or not user_id:
        return []

    response = table.query(
        KeyConditionExpression=Key("pk").eq(f"USER#{user_id}")
        & Key("sk").begins_with("RECENT#"),
        ScanIndexForward=False,
        Limit=limit,
    )

    seen: set[str] = set()
    ordered: list[str] = []

    for item in response.get("Items", []):
        dashboard_key = item.get("dashboard_key") or item.get("s3_key")

        # Migration fallback for old simple rows.
        if not dashboard_key:
            dashboard_key = item.get("dashboard_id")

        # Last fallback: parse from sk.
        if not dashboard_key:
            sk = item.get("sk", "")
            # RECENT#timestamp#dashboard_key
            parts = sk.split("#", 2)
            if len(parts) == 3:
                dashboard_key = parts[2]

        if dashboard_key and dashboard_key not in seen:
            seen.add(dashboard_key)
            ordered.append(dashboard_key)

        if len(ordered) >= deduped_limit:
            break

    return ordered


# Favorites + pinned removed in the community/local edition (DynamoDB overlay
# tables not used). Dashboard listing comes straight from S3.


def record_dashboard_recent(
    user_id: str,
    dashboard_key: str,
    label: str | None = None,
) -> None:
    table = _get_table("STRATABI_DASHBOARD_RECENTS")
    if table is None or not user_id or not dashboard_key:
        return

    dashboard_id = dashboard_id_from_value(dashboard_key)

    now = datetime.now(timezone.utc)
    opened_at = now.isoformat(timespec="seconds")
    ttl_epoch = int((now + timedelta(days=90)).timestamp())

    item = {
        "pk": f"USER#{user_id}",
        "sk": f"RECENT#{opened_at}#{dashboard_key}",
        "dashboard_key": dashboard_key,
        "s3_key": dashboard_key,
        "dashboard_id": dashboard_id,
        "opened_at": opened_at,
        "ttl_epoch": ttl_epoch,
    }

    if label:
        item["label"] = label

    table.put_item(Item=item)


# ---------------------------------------------------------------------
# Public dashboard list APIs
# ---------------------------------------------------------------------

def _list_dashboard_options_for_prefixes(
    bucket: str,
    prefixes: list[str],
    max_workers: int = 8,
) -> list[dict[str, Any]]:
    if not prefixes:
        return []

    worker_count = min(max_workers, len(prefixes))

    all_options: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_list_s3_dashboard_options_for_prefix, bucket, prefix)
            for prefix in prefixes
        ]

        for future in as_completed(futures):
            all_options.extend(future.result())

    return all_options

def list_dashboards_from_s3(
    user_id: str | None = None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    max_options: int = 1000,
) -> list[dict[str, Any]]:
    """
    Return Dash dropdown options for dashboards.

    Canonical value:
      value = S3 key

    Default working-set mode, when no date range is selected:
      - all pinned overlays
      - all user favorite overlays
      - all user recent overlays
      - previous 90 days of S3 dashboards for global + current user

    Explicit date-search mode, when both start_date and end_date are selected:
      - S3 dashboards from matching month prefixes
      - filtered by parsed dashboard timestamp
      - decorated with pinned/favorite/recent overlays
    """
    effective_user_id = user_id or resolve_actor_token()
    bucket = get_system_bucket()

    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)
    explicit_date_range = bool(start and end)

    # Community/local edition: favorites + pinned removed, and recents dropped
    # so no DynamoDB overlay tables are required to run. Listing is pure S3.
    favorite_items: list[dict[str, Any]] = []
    pinned_items: list[dict[str, Any]] = []
    recent_keys: list[str] = []

    def overlay_key(item: dict[str, Any]) -> str | None:
        return item.get("dashboard_key") or item.get("s3_key") or item.get("dashboard_id")

    favorite_keys = {
        key
        for item in favorite_items
        if (key := overlay_key(item))
    }

    pinned_keys = {
        key
        for item in pinned_items
        if (key := overlay_key(item))
    }

    recent_rank = {
        dashboard_key: index
        for index, dashboard_key in enumerate(recent_keys)
    }

    if explicit_date_range:
        months = months_between(start, end)
    else:
        months = months_for_previous_days(90)

    prefixes = dashboard_prefixes_for_user_months(
        user_id=effective_user_id,
        months=months,
    )

    dashboards = _list_dashboard_options_for_prefixes(
        bucket=bucket,
        prefixes=prefixes,
        max_workers=int(os.getenv("STRATABI_DASHBOARD_LIST_WORKERS", "8")),
    )

    # Add default dashboard explicitly because it lives outside month prefixes.
    try:
        default_key = default_dashboard_key()
        default_cfg_meta = _try_load_dashboard_name(bucket, default_key)
        dashboards.append(
            {
                "label": _display_name_from_config("default", default_cfg_meta),
                "value": default_key,
                "dashboard_id": "default",
                "search": dashboard_search_text("default", default_cfg_meta),
                "s3_key": default_key,
                "last_modified": None,
                "cfg_meta": default_cfg_meta,
            }
        )
    except Exception:
        pass

    # Default mode includes overlay-resurfaced dashboards even if they live
    # outside the 90-day S3 prefix window.
    if not explicit_date_range:
        for item in pinned_items + favorite_items:
            option = _overlay_item_to_dashboard_option(item)
            if option:
                dashboards.append(option)

        for dashboard_key in recent_keys:
            dashboard_id = dashboard_id_from_value(dashboard_key)

            dashboards.append(
                {
                    "label": label_from_identifier(dashboard_id),
                    "value": dashboard_key,
                    "dashboard_id": dashboard_id,
                    "search": dashboard_search_text(
                        dashboard_id,
                        is_recent=True,
                        is_favorite=dashboard_key in favorite_keys,
                        is_pinned=dashboard_key in pinned_keys,
                    ),
                    "s3_key": dashboard_key if "/" in dashboard_key else None,
                    "last_modified": None,
                    "cfg_meta": None,
                    "from_overlay": True,
                }
            )

    # De-dupe by canonical value / S3 key.
    # Prefer real S3-listed item over overlay-only item.
    by_value: dict[str, dict[str, Any]] = {}

    for item in dashboards:
        value = item["value"]
        existing = by_value.get(value)

        if existing is None:
            by_value[value] = item
            continue

        existing_is_overlay = bool(existing.get("from_overlay"))
        item_is_overlay = bool(item.get("from_overlay"))

        if existing_is_overlay and not item_is_overlay:
            by_value[value] = item
            continue

        existing_lm = existing.get("last_modified")
        item_lm = item.get("last_modified")

        if item_lm and existing_lm and item_lm > existing_lm:
            by_value[value] = item

    dashboards = list(by_value.values())

    # Visibility is based on parsed filename stem, not the full S3 key.
    dashboards = [
        item
        for item in dashboards
        if dashboard_visible_to_user(
            item.get("dashboard_id") or dashboard_id_from_value(item["value"]),
            effective_user_id,
        )
    ]

    # Explicit date mode filters by filename timestamp.
    if explicit_date_range:
        dashboards = [
            item
            for item in dashboards
            if dashboard_in_date_range(
                item.get("dashboard_id") or dashboard_id_from_value(item["value"]),
                start=start,
                end=end,
            )
        ]

    def priority(item: dict[str, Any]) -> tuple[int, int, str]:
        value = item["value"]
        label = str(item.get("label") or "").lower()

        if value in pinned_keys:
            return (0, 0, label)

        if value in favorite_keys:
            return (1, 0, label)

        if value in recent_rank:
            return (2, recent_rank[value], label)

        return (3, 0, label)

    dashboards.sort(key=priority)

    options: list[dict[str, Any]] = []

    for item in dashboards[:max_options]:
        value = item["value"]
        dashboard_id = item.get("dashboard_id") or dashboard_id_from_value(value)
        cfg_meta = item.get("cfg_meta")

        is_pinned = value in pinned_keys
        is_favorite = value in favorite_keys
        is_recent = value in recent_rank

        options.append(
            {
                "label": dashboard_dropdown_label(
                    dashboard_id,
                    cfg_meta,
                    is_pinned=is_pinned,
                    is_favorite=is_favorite,
                    is_recent=is_recent,
                ),
                "value": value,
                "search": dashboard_search_text(
                    dashboard_id,
                    cfg_meta,
                    is_pinned=is_pinned,
                    is_favorite=is_favorite,
                    is_recent=is_recent,
                ),
            }
        )

    if len(dashboards) > max_options:
        options.append(
            {
                "label": f"Showing first {max_options:,} dashboards — use date search for older dashboards",
                "value": "__STRATABI_DASHBOARD_LIMIT__",
                "disabled": True,
            }
        )

    return options


def list_dashboard_options(
    user_id: str | None = None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    return list_dashboards_from_s3(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )


def list_dashboard_keys(user_id: str | None = None) -> list[str]:
    return [opt["value"] for opt in list_dashboards_from_s3(user_id=user_id)]


def _query_dashboard_overlay_items(
    table,
    pk_value: str,
    sk_prefix: str = "DASHBOARD#",
    limit: int = 500,
) -> list[dict[str, Any]]:
    if table is None:
        return []

    items: list[dict[str, Any]] = []
    last_key = None

    while True:
        kwargs = {
            "KeyConditionExpression": Key("pk").eq(pk_value)
            & Key("sk").begins_with(sk_prefix),
            "Limit": limit,
        }

        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        response = table.query(**kwargs)

        for item in response.get("Items", []):
            dashboard_key = item.get("dashboard_key") or item.get("s3_key")
            dashboard_id = item.get("dashboard_id")

            if not dashboard_key:
                sk = item.get("sk", "")
                raw = sk.removeprefix(sk_prefix)
                dashboard_key = raw or None

            if dashboard_key and not dashboard_id:
                dashboard_id = dashboard_id_from_value(dashboard_key)

            if dashboard_key or dashboard_id:
                enriched = dict(item)
                if dashboard_key:
                    enriched["dashboard_key"] = dashboard_key
                    enriched["s3_key"] = dashboard_key
                if dashboard_id:
                    enriched["dashboard_id"] = dashboard_id
                items.append(enriched)

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    return items