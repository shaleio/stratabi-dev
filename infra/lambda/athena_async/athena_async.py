# infra/lambda/athena_async/athena_async.py

import json
import os
import random
import time
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
import awswrangler as wr


lambda_client = boto3.client("lambda")
dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.getenv("STRATABI_TILE_STATUS_TABLE", "stratabi_tile_status")
TABLE = dynamodb.Table(TABLE_NAME)

DEFAULT_TTL_SECONDS = int(os.getenv("STRATABI_STATUS_TTL_SECONDS", "86400"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ttl_epoch() -> int:
    return int(time.time()) + DEFAULT_TTL_SECONDS


def decimalize(value: Any) -> Any:
    """
    DynamoDB does not accept Python floats.
    Convert float values to Decimal recursively.
    """
    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, dict):
        return {
            key: decimalize(inner)
            for key, inner in value.items()
            if inner is not None
        }

    if isinstance(value, list):
        return [decimalize(inner) for inner in value]

    return value


def select_workgroup(event: dict[str, Any]) -> str:
    """
    Select Athena workgroup.

    Priority:
      1. Explicit workgroup in event
      2. Random workgroup from STRATABI_WORKGROUPS
      3. Athena default primary workgroup
    """
    explicit = event.get("workgroup")
    if explicit:
        return explicit

    workgroups_raw = os.getenv("STRATABI_WORKGROUPS", "")
    workgroups = [wg.strip() for wg in workgroups_raw.split(",") if wg.strip()]

    if workgroups:
        return random.choice(workgroups)

    return "primary"


def build_status_item(
    status_context: dict[str, Any],
    status: str,
    **extra: Any,
) -> dict[str, Any]:
    item = {
        **status_context,
        **extra,
        "status": status,
        "updated_at": now_iso(),
        "ttl": int(status_context.get("ttl") or ttl_epoch()),
    }

    item.setdefault("created_at", item["updated_at"])
    item.setdefault("traceback", "")

    system_bucket = item.get("system_bucket")
    result_s3_key = item.get("result_s3_key")

    if system_bucket and result_s3_key and "result_s3_uri" not in item:
        item["result_s3_uri"] = f"s3://{system_bucket}/{result_s3_key}"

    return item


def notify_status_writer(
    status_writer_lambda_arn: str | None,
    status_item: dict[str, Any],
) -> None:
    """
    Prefer the central status writer when provided.
    Fallback to direct DynamoDB write for local/simple deployments.
    """
    if status_writer_lambda_arn:
        lambda_client.invoke(
            FunctionName=status_writer_lambda_arn,
            InvocationType="Event",
            Payload=json.dumps(status_item, default=str).encode("utf-8"),
        )
        return

    TABLE.put_item(Item=decimalize(status_item))


def write_status(
    *,
    status_writer_lambda_arn: str | None,
    status_context: dict[str, Any],
    status: str,
    **extra: Any,
) -> dict[str, Any]:
    item = build_status_item(status_context, status, **extra)
    notify_status_writer(status_writer_lambda_arn, item)
    return item


def _validate_event(event: dict[str, Any]) -> tuple[dict[str, Any], str]:
    status_context = event.get("status_context") or {}
    resolved_sql = event.get("resolved_sql")

    missing = [
        name
        for name, value in {
            "status_context": status_context,
            "runtime_tile_key": status_context.get("runtime_tile_key"),
            "run_id": status_context.get("run_id"),
            "system_bucket": status_context.get("system_bucket"),
            "result_s3_key": status_context.get("result_s3_key"),
            "result_kind": status_context.get("result_kind"),
            "result_format": status_context.get("result_format"),
            "resolved_sql": resolved_sql,
        }.items()
        if not value
    ]

    if missing:
        raise ValueError(f"Missing required event fields: {', '.join(missing)}")

    if status_context["result_kind"] != "dataframe":
        raise ValueError(
            "Async Athena only supports result_kind='dataframe'. "
            f"Got {status_context['result_kind']!r}."
        )

    if status_context["result_format"] != "parquet":
        raise ValueError(
            "Async Athena now writes parquet only. "
            f"Got result_format={status_context['result_format']!r}."
        )

    return status_context, resolved_sql


def _query_metadata(df) -> dict[str, Any]:
    """
    awswrangler commonly attaches query_metadata to returned DataFrames.
    Keep this defensive because exact metadata shape can vary by version/path.
    """
    metadata = getattr(df, "query_metadata", None)

    if not isinstance(metadata, dict):
        return {}

    return metadata


def lambda_handler(event, context):
    """
    StrataBI async Athena runner.

    Contract:
      - Core passes status_context.
      - This Lambda runs Athena.
      - This Lambda writes parquet to:
          s3://status_context["system_bucket"]/status_context["result_s3_key"]
      - This Lambda reports SUCCEEDED/FAILED.
      - Core reads the artifact from status.
    """

    status_context, resolved_sql = _validate_event(event)

    status_writer_lambda_arn = event.get("status_writer_lambda_arn")
    database = event.get("database")
    workgroup = select_workgroup(event)

    result_uri = (
        f"s3://{status_context['system_bucket']}/"
        f"{status_context['result_s3_key']}"
    )

    athena_output = os.getenv("STRATABI_ATHENA_OUTPUT")

    try:
        write_status(
            status_writer_lambda_arn=status_writer_lambda_arn,
            status_context=status_context,
            status="RUNNING",
            message="Async Athena query started.",
            workgroup=workgroup,
        )

        read_kwargs = {
            "sql": resolved_sql,
            "database": database,
            "workgroup": workgroup,
            "ctas_approach": False,
        }

        if athena_output:
            read_kwargs["s3_output"] = athena_output

        df = wr.athena.read_sql_query(**read_kwargs)

        metadata = _query_metadata(df)
        query_execution_id = metadata.get("QueryExecutionId")

        wr.s3.to_parquet(
            df=df,
            path=result_uri,
            index=False,
        )

        columns = [str(col) for col in df.columns]

        succeeded = write_status(
            status_writer_lambda_arn=status_writer_lambda_arn,
            status_context=status_context,
            status="SUCCEEDED",
            message="Async Athena query succeeded.",
            workgroup=workgroup,
            query_execution_id=query_execution_id,
            result_s3_uri=result_uri,
            rows=len(df),
            columns=columns,
            traceback="",
        )

        return {
            "ok": True,
            "runtime_tile_key": status_context["runtime_tile_key"],
            "run_id": status_context["run_id"],
            "status": "SUCCEEDED",
            "query_execution_id": query_execution_id,
            "result_s3_key": status_context["result_s3_key"],
            "result_s3_uri": succeeded.get("result_s3_uri", result_uri),
            "rows": len(df),
            "columns": columns,
        }

    except Exception as exc:
        failed = build_status_item(
            status_context,
            "FAILED",
            message=f"Async Athena execution failed: {exc}",
            error_code="ATHENA_ASYNC_EXCEPTION",
            workgroup=workgroup,
            traceback=traceback.format_exc(),
        )

        notify_status_writer(status_writer_lambda_arn, failed)

        raise