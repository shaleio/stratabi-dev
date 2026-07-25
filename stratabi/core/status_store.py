# stratabi/core/status_store.py

import hashlib
import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key


dynamodb = boto3.resource("dynamodb")

STATUS_TABLE_NAME = os.getenv("STRATABI_TILE_STATUS_TABLE", "stratabi_tile_status")

STATUS_RUNTIME_INDEX_NAME = os.getenv(
    "STRATABI_STATUS_RUNTIME_TILE_INDEX",
    "runtime-tile-updated-index",
)

DEPLOYMENT_ID = os.getenv("STRATABI_DEPLOYMENT_ID", "default")

STATUS_TABLE = dynamodb.Table(STATUS_TABLE_NAME)


def _normalize_runtime_session_id(runtime_session_id: str | None) -> str:
    return runtime_session_id or "shared"


def _dashboard_key_hash(dashboard_key: str) -> str:
    raw = str(dashboard_key or "default").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _runtime_tile_key(
    dashboard_key: str,
    runtime_session_id: str | None,
    tile_id: str,
) -> str:
    session_id = _normalize_runtime_session_id(runtime_session_id)
    return f"{DEPLOYMENT_ID}#{_dashboard_key_hash(dashboard_key)}#{session_id}#{tile_id}"


def _dashboard_tile_key(dashboard_key: str, tile_id: str) -> str:
    return f"{DEPLOYMENT_ID}#{_dashboard_key_hash(dashboard_key)}#{tile_id}"


def _normalize_status_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "deployment_id": item.get("deployment_id", ""),
        "dashboard_key": item.get("dashboard_key", ""),
        "dashboard_key_hash": item.get("dashboard_key_hash", ""),
        "runtime_session_id": item.get("runtime_session_id", ""),
        "runtime_tile_key": item.get("runtime_tile_key", ""),
        "dashboard_tile_key": item.get("dashboard_tile_key", ""),
        "tile_id": item.get("tile_id", ""),
        "run_id": item.get("run_id", ""),
        "input_hash": item.get("input_hash", ""),
        "status": item.get("status", "UNKNOWN"),
        "exec_type": item.get("exec_type", ""),
        "module_id": item.get("module_id", ""),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
        "message": item.get("message", ""),
        "traceback": item.get("traceback", ""),
        "query_execution_id": item.get("query_execution_id", ""),
        "result_s3_key": item.get("result_s3_key", ""),
        "bytes_scanned": item.get("bytes_scanned", ""),
    }


def _dashboard_key_from_config(dashboard_config: dict[str, Any]) -> str:
    dashboard_key = dashboard_config.get("_dashboard_key")

    if not dashboard_key:
        raise ValueError("Dashboard config is missing `_dashboard_key` runtime identity.")

    return str(dashboard_key)


def _latest_status_for_tile(
    *,
    dashboard_key: str,
    runtime_session_id: str | None,
    tile_id: str,
) -> dict[str, Any] | None:
    runtime_tile_key = _runtime_tile_key(
        dashboard_key=dashboard_key,
        runtime_session_id=runtime_session_id,
        tile_id=tile_id,
    )

    response = STATUS_TABLE.query(
        IndexName=STATUS_RUNTIME_INDEX_NAME,
        KeyConditionExpression=Key("runtime_tile_key").eq(runtime_tile_key),
        ScanIndexForward=False,
        Limit=1,
    )

    items = response.get("Items", [])

    if not items:
        return None

    return _normalize_status_item(items[0])


def get_dashboard_statuses(
    dashboard_config: dict[str, Any],
    runtime_session_id: str | None,
) -> dict[str, dict[str, Any]]:
    dashboard_key = _dashboard_key_from_config(dashboard_config)

    statuses: dict[str, dict[str, Any]] = {}

    for tile in dashboard_config.get("layout", []):
        tile_id = tile.get("id")

        if not tile_id:
            continue

        latest = _latest_status_for_tile(
            dashboard_key=dashboard_key,
            runtime_session_id=runtime_session_id,
            tile_id=tile_id,
        )

        if latest:
            statuses[tile_id] = latest

    return statuses