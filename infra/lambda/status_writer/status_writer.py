# lambda/status_writer/status_writer.py

import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3


dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.getenv("STRATABI_TILE_STATUS_TABLE", "stratabi_tile_status")
TABLE = dynamodb.Table(TABLE_NAME)

DEFAULT_TTL_SECONDS = int(os.getenv("STRATABI_STATUS_TTL_SECONDS", "86400"))

VALID_STATUSES = {
    "REQUESTED",
    "QUEUED",
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
}

VALID_ACTIONS = {
    "requested": "REQUESTED",
    "queued": "QUEUED",
    "pending": "PENDING",
    "running": "RUNNING",
    "succeeded": "SUCCEEDED",
    "failed": "FAILED",
    "cancelled": "CANCELLED",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ttl_epoch() -> int:
    return int(time.time()) + DEFAULT_TTL_SECONDS


def response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "body": json.dumps(body, default=str),
    }


def _clean_dynamodb_value(value: Any) -> Any:
    """
    DynamoDB does not accept Python floats.
    Recursively convert floats to Decimal.
    """

    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, dict):
        return {
            key: _clean_dynamodb_value(inner)
            for key, inner in value.items()
            if inner is not None
        }

    if isinstance(value, list):
        return [_clean_dynamodb_value(inner) for inner in value]

    return value


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    """
    Support direct Lambda invokes and API Gateway-style invokes.
    """

    body = event.get("body")

    if body is None:
        return event

    if isinstance(body, dict):
        return body

    if isinstance(body, str):
        return json.loads(body)

    raise ValueError("Unsupported event body type.")


def _normalize_status(raw: dict[str, Any]) -> str:
    """
    Accept either:
      - status: SUCCEEDED
      - status: succeeded
      - action: succeeded
    """

    status = raw.get("status")

    if isinstance(status, str):
        upper_status = status.upper()
        if upper_status in VALID_STATUSES:
            return upper_status

        lower_status = status.lower()
        if lower_status in VALID_ACTIONS:
            return VALID_ACTIONS[lower_status]

    action = raw.get("action")

    if isinstance(action, str) and action.lower() in VALID_ACTIONS:
        return VALID_ACTIONS[action.lower()]

    raise ValueError(
        "Missing or unsupported status/action. "
        f"Valid statuses: {sorted(VALID_STATUSES)}. "
        f"Valid actions: {sorted(VALID_ACTIONS)}."
    )


def _build_item(raw: dict[str, Any]) -> dict[str, Any]:
    """
    New preferred payload:

    {
      "runtime_tile_key": "...",
      "run_id": "...",
      "status": "SUCCEEDED",
      "system_bucket": "...",
      "result_s3_key": "...",
      "result_kind": "dataframe",
      "result_format": "json",
      ...
    }

    Also supports:

    {
      "status_context": {...},
      "status": "SUCCEEDED",
      "message": "..."
    }
    """

    status_context = raw.get("status_context") or {}

    if not isinstance(status_context, dict):
        raise ValueError("status_context must be an object when provided.")

    merged = {
        **status_context,
        **{
            key: value
            for key, value in raw.items()
            if key != "status_context"
        },
    }

    status = _normalize_status(merged)

    runtime_tile_key = merged.get("runtime_tile_key")
    run_id = merged.get("run_id")

    missing = [
        name
        for name, value in {
            "runtime_tile_key": runtime_tile_key,
            "run_id": run_id,
        }.items()
        if not value
    ]

    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    item = dict(merged)
    item["runtime_tile_key"] = runtime_tile_key
    item["run_id"] = run_id
    item["status"] = status
    item["updated_at"] = now_iso()
    item["ttl"] = int(item.get("ttl") or ttl_epoch())

    # Keep created_at if supplied by status_context.
    item.setdefault("created_at", item["updated_at"])

    # Keep empty traceback valid but default it.
    item.setdefault("traceback", "")

    # Optional convenience: construct full result URI for humans/debugging.
    system_bucket = item.get("system_bucket")
    result_s3_key = item.get("result_s3_key")

    if system_bucket and result_s3_key and "result_s3_uri" not in item:
        item["result_s3_uri"] = f"s3://{system_bucket}/{result_s3_key}"

    return _clean_dynamodb_value(item)


def lambda_handler(event, context):
    """
    StrataBI status writer.

    Preferred usage:
      Module Lambda receives event["status_context"], writes artifact, then invokes
      this writer with a full status item or status_context + status.

    Required final DynamoDB key fields:
      runtime_tile_key
      run_id
    """

    try:
        raw = _parse_body(event)
        item = _build_item(raw)

        TABLE.put_item(Item=item)

        return response(
            200,
            {
                "ok": True,
                "runtime_tile_key": item["runtime_tile_key"],
                "run_id": item["run_id"],
                "status": item["status"],
            },
        )

    except Exception as e:
        return response(
            400,
            {
                "ok": False,
                "error": str(e),
            },
        )