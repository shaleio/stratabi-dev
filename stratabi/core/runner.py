# stratabi/core/runner.py

import hashlib
import json
import os
import time
from datetime import datetime, timezone
import uuid
import re
import boto3
from botocore.exceptions import ClientError
from stratabi.core.athena_runner import AthenaRunner
from stratabi.core.text_utils import coerce_lines
from stratabi.core.lambda_runner import (
    invoke_lambda_sync,
    invoke_lambda_async,
    resolve_module_for_execution,
)
from stratabi.core.s3_loader import load_result_from_status, load_result_from_s3
from stratabi.core.source_macros import SourceMacroResolver


STATUS_TABLE_NAME = os.getenv("STRATABI_TILE_STATUS_TABLE", "stratabi_tile_status")

# Created lazily (not at import) with an explicit region so `import stratabi.core.runner`
# never raises NoRegionError, and a .env with only AWS_REGION resolves. See N7/N12.
_status_table = None


def _get_status_table():
    global _status_table
    if _status_table is None:
        from stratabi.core.config import aws_region
        _status_table = boto3.resource("dynamodb", region_name=aws_region()).Table(STATUS_TABLE_NAME)
    return _status_table

DEPLOYMENT_ID = os.getenv("STRATABI_DEPLOYMENT_ID", "default")
RESULT_PREFIX = os.getenv("STRATABI_RESULT_PREFIX", "runtime/results").strip("/")
BUCKET = os.getenv("STRATABI_SYSTEM_BUCKET", "")

BLOCK_RESULT_DEFAULTS = {
    "plotly": {
        "result_kind": "dataframe",
        "result_format": "parquet",
        "result_name": "result.parquet",
    },
    "plotly_resampler": {
        "result_kind": "dataframe",
        "result_format": "parquet",
        "result_name": "result.parquet",
    },
    "table": {
        "result_kind": "dataframe",
        "result_format": "parquet",
        "result_name": "result.parquet",
    },
    "markdown": {
        "result_kind": "artifact",
        "result_format": "md",
        "result_name": "result.md",
    },
    "raw_html": {
        "result_kind": "artifact",
        "result_format": "html",
        "result_name": "result.html",
    },
    "image": {
        "result_kind": "artifact",
        "result_format": "png",
        "result_name": "result.png",
    },
    "input_select": {
        "result_kind": "json",
        "result_format": "json",
        "result_name": "result.json",
    },
    "input_range": {
        "result_kind": "json",
        "result_format": "json",
        "result_name": "result.json",
    },
    "input_text": {
        "result_kind": "json",
        "result_format": "json",
        "result_name": "result.json",
    },
    "button": {
        "result_kind": "json",
        "result_format": "json",
        "result_name": "result.json",
    },
}

def _ttl_epoch() -> int:
    ttl_seconds = int(os.getenv("STRATABI_STATUS_TTL_SECONDS", "86400"))
    return int(time.time()) + ttl_seconds

def _normalize_runtime_session_id(runtime_session_id: str | None) -> str:
    return runtime_session_id or "shared"

def _dashboard_tile_key(dashboard_key: str, tile_id: str) -> str:
    return f"{DEPLOYMENT_ID}#{_dashboard_key_hash(dashboard_key)}#{tile_id}"

def _runtime_tile_key(
    dashboard_key: str,
    runtime_session_id: str | None,
    tile_id: str,
) -> str:
    session_id = _normalize_runtime_session_id(runtime_session_id)
    return f"{DEPLOYMENT_ID}#{_dashboard_key_hash(dashboard_key)}#{session_id}#{tile_id}"


def _input_hash(inputs: dict | None) -> str:
    raw = json.dumps(inputs or {}, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]

def _dashboard_key_hash(dashboard_key: str) -> str:
    raw = str(dashboard_key or "default").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _execution_mode(tile: dict) -> str:
    return (
        tile.get("load", {})
        .get("mode", "load_once")
    )

def _result_s3_key(
    *,
    dashboard_key_hash: str,
    runtime_session_id: str,
    tile_id: str,
    run_id: str,
    result_name: str,
) -> str:
    return (
        f"{RESULT_PREFIX}/"
        f"dash={dashboard_key_hash}/"
        f"session={runtime_session_id}/"
        f"tile={tile_id}/"
        f"run={run_id}/"
        f"{result_name}"
    )

def _prepare_sql(sql: str, params: dict | None, inputs: dict | None) -> str:
    if params:
        raw_inputs = inputs or {}
        input_values = raw_inputs.get("inputs", raw_inputs)

        for sql_param, input_path in params.items():
            value = input_values

            for part in input_path.split("."):
                if not isinstance(value, dict):
                    value = None
                    break

                value = value.get(part)

                if value is None:
                    break

            if value is None:
                raise ValueError(f"Missing input for SQL param: {sql_param}")

            sql = _replace_sql_param(sql, sql_param, value)

    resolver = SourceMacroResolver(
        database=os.getenv("STRATABI_CATALOG_DATABASE", "stratabi")
    )

    resolution = resolver.resolve(sql, ensure_tables=True)
    return resolution.resolved_sql

def _sql_literal(value):
    if value is None:
        return "NULL"

    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, (list, tuple)):
        return "(" + ", ".join(_sql_literal(v) for v in value) + ")"

    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"

def _interval_bucket(tile: dict) -> int:
    interval_ms = tile.get("load", {}).get("interval_ms")

    if interval_ms is None:
        interval_ms = int(os.getenv("STRATABI_DEFAULT_INTERVAL_MS", "60000"))

    interval_seconds = max(int(interval_ms / 1000), 1)
    return int(time.time() // interval_seconds)

def _replace_sql_param(sql: str, name: str, value) -> str:
    pattern = rf":{re.escape(name)}\b"
    return re.sub(pattern, _sql_literal(value), sql)

def _make_run_id(
    tile: dict,
    inputs: dict | None,
    dashboard_key: str,
    runtime_session_id: str | None,
    runtime_event: dict | None = None,
) -> str:
    mode = _execution_mode(tile)
    runtime_event = runtime_event or {}

    payload = {
        "deployment_id": DEPLOYMENT_ID,
        "dashboard_key": dashboard_key,
        "runtime_session_id": _normalize_runtime_session_id(runtime_session_id),
        "tile_id": tile["id"],
        "exec": tile.get("exec"),
        "query": tile.get("query"),
        "mode": mode,
    }

    if mode == "load_once":
        pass

    elif mode == "input":
        payload["inputs"] = inputs or {}

    elif mode == "manual":
        payload["inputs"] = inputs or {}

    elif mode == "interval":
        payload["inputs"] = inputs or {}
        payload["interval_tick"] = runtime_event.get("interval_tick") or _interval_bucket(tile)

    elif mode == "always":
        payload["inputs"] = inputs or {}
        payload["nonce"] = uuid.uuid4().hex

    else:
        payload["inputs"] = inputs or {}

    if runtime_event.get("sync_nonce"):
        payload["sync_nonce"] = runtime_event["sync_nonce"]  # exec.sync: every call is its own run

    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _get_tile_status(runtime_tile_key: str, run_id: str) -> dict | None:
    return _get_status_table().get_item(
        Key={
            "runtime_tile_key": runtime_tile_key,
            "run_id": run_id,
        }
    ).get("Item")

def _status_context(
    *,
    dashboard_key: str,
    tile: dict,
    runtime_session_id: str | None,
    inputs: dict | None,
    run_id: str,
    exec_type: str,
    module_id: str | None = None,
) -> dict:
    now = _now_iso()
    tile_id = tile["id"]

    dashboard_hash = _dashboard_key_hash(dashboard_key)
    session_id = _normalize_runtime_session_id(runtime_session_id)
    result_defaults = _result_defaults_for_tile(tile)

    result_s3_key = _result_s3_key(
        dashboard_key_hash=dashboard_hash,
        runtime_session_id=session_id,
        tile_id=tile_id,
        run_id=run_id,
        result_name=result_defaults["result_name"],
    )

    context = {
        "deployment_id": DEPLOYMENT_ID,
        "dashboard_key": dashboard_key,
        "dashboard_key_hash": dashboard_hash,
        "runtime_session_id": session_id,
        "runtime_tile_key": _runtime_tile_key(
            dashboard_key=dashboard_key,
            runtime_session_id=runtime_session_id,
            tile_id=tile_id,
        ),
        "dashboard_tile_key": _dashboard_tile_key(dashboard_key, tile_id),
        "tile_id": tile_id,
        "run_id": run_id,
        "input_hash": _input_hash(inputs),
        "exec_type": exec_type,

        # result contract
        "block_type": result_defaults["block_type"],
        "result_kind": result_defaults["result_kind"],
        "result_format": result_defaults["result_format"],
        "result_s3_key": result_s3_key,

        #system_bucket
        "system_bucket": BUCKET,

        # latest state
        "created_at": now,
        "updated_at": now,
        "status": "REQUESTED",
        "message": "Async execution requested.",
        "traceback": "",
        "ttl": _ttl_epoch(),
    }

    if module_id:
        context["module_id"] = module_id
        # Who asked. The module contract carries actor / actor_verified / auth_mode. The
        # Developer Edition has no sign-in, so this is always the unverified shared actor —
        # exactly what a module sees from a deployment without auth. Build modules to treat
        # actor_verified=False as "no individual user".
        context.update(_actor_fields())

    return context


def _actor_fields() -> dict:
    return {"actor": "anonymous", "actor_verified": False, "auth_mode": "none"}


def _put_running_status(
    status_context: dict,
    message: str | None = None,
    replace: dict | None = None,
) -> tuple[dict, bool]:
    """Claim the run (write RUNNING). New run: only if no row exists. Re-run of an existing
    row (`replace`): only if the row is still exactly the one we looked at, so two browsers
    retrying at once can't both invoke."""
    item = dict(status_context)

    exec_type = item.get("exec_type", "unknown")

    item["status"] = "RUNNING"
    item["updated_at"] = _now_iso()
    item["message"] = message or f"Async {exec_type} execution invoked."
    item["traceback"] = ""

    if replace is None:
        cond = {"ConditionExpression": (
            "attribute_not_exists(runtime_tile_key) "
            "AND attribute_not_exists(run_id)"
        )}
    else:
        item["attempt"] = int(replace.get("attempt") or 1) + 1
        cond = {
            "ConditionExpression": "#st = :st AND updated_at = :u",
            "ExpressionAttributeNames": {"#st": "status"},
            "ExpressionAttributeValues": {":st": replace.get("status"), ":u": replace.get("updated_at")},
        }

    try:
        _get_status_table().put_item(Item=item, **cond)
        return item, True

    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return item, False
        raise


# A worker that dies before reporting (crash, missing IAM, timeout) leaves its row RUNNING. Lambda
# tops out at 15 min, so a RUNNING row older than this can never complete on its own.
ASYNC_STALE_SECONDS = int(os.getenv("STRATABI_ASYNC_STALE_SECONDS", "900"))
_ACTIVE = ("QUEUED", "PENDING", "RUNNING", "REQUESTED", "PROCESSING")
_FAILED = ("FAILED", "CANCELLED")


def _is_stale(status: dict) -> bool:
    if str(status.get("status", "")).upper() not in _ACTIVE:
        return False
    try:
        ts = datetime.fromisoformat(str(status.get("updated_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True  # unparseable timestamp on an active row: treat as dead
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() > ASYNC_STALE_SECONDS


def _mark_timed_out(status: dict) -> dict:
    failed = dict(status)
    failed["status"] = "FAILED"
    failed["updated_at"] = _now_iso()
    failed["message"] = (f"No completion reported within {ASYNC_STALE_SECONDS // 60} min — the worker "
                         "stopped without reporting. Use ▷ to run again.")
    try:
        _get_status_table().put_item(
            Item=failed,
            ConditionExpression="#st = :st AND updated_at = :u",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":st": status.get("status"), ":u": status.get("updated_at")},
        )
    except ClientError:
        pass  # someone else updated it first; their state wins
    return failed


def _resolve_existing(status: dict | None, rerun: str | None) -> tuple[dict | None, dict | None]:
    """Decide what to do with an existing status row. Returns (status_to_report, row_to_replace):
    - (row, None)  -> report the row as-is (cached result / still running / failed)
    - (None, row)  -> re-invoke, overwriting `row`
    rerun: None (poll/normal), "retry_failed" (fresh page load), "force" (explicit ▷ run)."""
    if not status:
        return None, None
    st = str(status.get("status", "")).upper()
    stale = _is_stale(status)
    if rerun == "force" and (st not in _ACTIVE or stale):
        return None, status
    if rerun == "retry_failed" and (st in _FAILED or stale):
        return None, status
    if stale:
        return _mark_timed_out(status), None
    return status, None


def _run_lambda_sync(tile: dict, exec_cfg: dict, inputs: dict, dashboard_key: str,
                     runtime_session_id: str | None, trigger_kind: str = "load"):
    """exec.sync: call the module Lambda and wait for it (RequestResponse) instead of invoking it
    in the background and polling. Same contract as async — the module writes its artifact to
    status_context.result_s3_key and returns {"status", "message"} — so artifacts stay in S3 and
    inspectable, and a module needs no changes to support it. Each call is a fresh run (unique
    run_id): sync tiles aren't cached, which is what action tiles want. For quick work only; the
    tile's request blocks until the Lambda answers (exec.timeout_seconds, default 30, max 120)."""
    try:
        module = resolve_module_for_execution(exec_cfg["module_id"], exec_cfg["lambda_index"])
    except Exception as e:  # noqa: BLE001
        return {"status": "FAILED", "message": f"Failed to resolve module {exec_cfg.get('module_id')}: {e}"}

    run_id = _make_run_id(tile=tile, inputs=inputs, dashboard_key=dashboard_key,
                          runtime_session_id=runtime_session_id,
                          runtime_event={"sync_nonce": uuid.uuid4().hex})
    status_context = _status_context(
        dashboard_key=dashboard_key, tile=tile, runtime_session_id=runtime_session_id,
        inputs=inputs, run_id=run_id, exec_type="lambda", module_id=module["module_id"],
    )
    payload = {
        "deployment_id": DEPLOYMENT_ID,
        "dashboard_key": dashboard_key,
        "runtime_session_id": _normalize_runtime_session_id(runtime_session_id),
        "runtime_tile_key": status_context["runtime_tile_key"],
        "dashboard_tile_key": status_context["dashboard_tile_key"],
        "tile": tile,
        "tile_id": tile["id"],
        "inputs": inputs,
        "run_id": run_id,
        "invocation": "sync",
        "trigger": trigger_kind,
        # No status writer: core records the outcome itself once the call returns.
        "status_writer_lambda_arn": None,
        "status_context": status_context,
        "module": {
            "module_id": module["module_id"],
            "version": module.get("version"),
            "lambda_index": module["lambda_index"],
            "lambda_name": module.get("lambda_name"),
        },
    }
    try:
        resp = invoke_lambda_sync(module["lambda_arn"], payload, exec_cfg.get("timeout_seconds"))
    except Exception as e:  # noqa: BLE001 — timeout / throttle / permission
        return {"status": "FAILED", "message": f"Module Lambda call failed: {e}"}

    body = resp.get("payload") or {}
    if resp.get("function_error"):
        msg = body.get("errorMessage") or body.get("message") or resp["function_error"]
        return {"status": "FAILED", "message": f"Module Lambda error: {msg}"}
    status = str(body.get("status") or "SUCCEEDED").upper()
    if status in _FAILED:
        return {"status": "FAILED", "message": body.get("message") or "Module reported failure."}

    if isinstance(body.get("inline_html"), str):
        # Ephemeral result (e.g. a one-time launch link): render it in this response only. It is
        # never written to S3, the status table or logs, so nothing can replay or download it.
        return body["inline_html"]

    record = dict(status_context)
    record.update(status="SUCCEEDED", updated_at=_now_iso(), invocation="sync",
                  message=body.get("message") or "Completed (sync).", traceback="")
    try:  # lineage + artifact download; best-effort, never fails the tile
        _get_status_table().put_item(Item=record)
    except Exception:  # noqa: BLE001
        pass
    return load_result_from_status(record)


def _handle_status_result(status: dict):
    current_status = str(status.get("status", "RUNNING")).upper()

    if current_status in ("QUEUED", "PENDING", "RUNNING", "REQUESTED", "PROCESSING"):
        return {"status": "RUNNING"}

    if current_status == "SUCCEEDED":
        try:
            return load_result_from_status(status)
        except Exception as e:
            return {
                "status": "FAILED",
                "message": f"Failed to load result artifact: {e}",
            }

    if current_status in ("FAILED", "CANCELLED"):
        return {
            "status": "FAILED",
            "message": status.get(
                "message",
                f"Tile execution ended with status {current_status}.",
            ),
            "traceback": status.get("traceback", ""),
        }

    return {
        "status": "FAILED",
        "message": f"Unknown tile execution status: {current_status}",
    }

def _block_type(tile: dict) -> str:
    return str(tile.get("block", {}).get("type", "unknown"))


def _result_defaults_for_tile(tile: dict) -> dict:
    block_type = _block_type(tile)

    defaults = BLOCK_RESULT_DEFAULTS.get(
        block_type,
        {
            "result_kind": "artifact",
            "result_format": "json",
            "result_name": "result.json",
        },
    )

    # Later escape hatch:
    # tile["exec"]["result_format"] or tile["exec"]["result_name"]
    exec_cfg = tile.get("exec", {}) or {}

    return {
        "block_type": block_type,
        "result_kind": exec_cfg.get("result_kind", defaults["result_kind"]),
        "result_format": exec_cfg.get("result_format", defaults["result_format"]),
        "result_name": exec_cfg.get("result_name", defaults["result_name"]),
    }

def execute_tile(
    tile: dict,
    inputs: dict | None = None,
    dashboard_key: str | None = None,
    runtime_session_id: str | None = None,
    rerun: str | None = None,
    trigger_kind: str = "load",
):
    """
    Execute a StrataBI tile.

    rerun (async tiles): None = report the existing run; "retry_failed" = re-invoke a failed or
    dead run (fresh page load); "force" = re-invoke any finished or dead run (explicit ▷).

    Returns:
      - pandas.DataFrame or renderable result when ready
      - {"status": "RUNNING"} when async work is still running
      - {"status": "FAILED", "message": "..."} when async work failed
    """

    dashboard_key = dashboard_key or "default"

    inputs = inputs or {}

    exec_cfg = tile.get("exec")

    if not exec_cfg:
        return None

    exec_type = exec_cfg.get("type", "athena")

    # ---------------------------------------
    # 1) CACHE ONLY / PRECOMPUTED RESULT
    # ---------------------------------------
    if exec_type == "cache":
        return load_result_from_s3(exec_cfg["cache_s3_uri"])

    # ---------------------------------------
    # 2) ATHENA
    # ---------------------------------------
    if exec_type == "athena":
        query_cfg = tile["query"]

        if isinstance(query_cfg["sql"], dict):
            raise ValueError("query.sql source values must be resolved before execute_tile.")
        sql = _prepare_sql(
            sql=coerce_lines(query_cfg["sql"]),
            params=query_cfg.get("params"),
            inputs=inputs,
        )

        # Sync Athena path
        if not exec_cfg.get("async", False):
            runner = AthenaRunner()
            return runner.run_query(
                query=sql,
                database=exec_cfg.get("database"),
            )

        # Async Athena path
        run_id = _make_run_id(
            tile=tile,
            inputs=inputs,
            dashboard_key=dashboard_key,
            runtime_session_id=runtime_session_id,
        )

        status_context = _status_context(
            dashboard_key=dashboard_key,
            tile=tile,
            runtime_session_id=runtime_session_id,
            inputs=inputs,
            run_id=run_id,
            exec_type="athena",
        )

        runtime_tile_key = _runtime_tile_key(
            dashboard_key=dashboard_key,
            runtime_session_id=runtime_session_id,
            tile_id=tile["id"],
        )

        status, replace = _resolve_existing(_get_tile_status(runtime_tile_key, run_id), rerun)

        if not status:
            # Temporary: async Athena still uses an explicit Lambda ARN.
            # Later, move this to an env var or internal module registry entry.
            lambda_arn = os.getenv("STRATABI_ATHENA_ASYNC_LAMBDA_ARN")
            
            if not lambda_arn:
                return {
                    "status": "FAILED",
                    "message": "STRATABI_ATHENA_ASYNC_LAMBDA_ARN is not configured.",
                }

            status_context, acquired_lock = _put_running_status(
                status_context,
                message="Async Athena Lambda invoked.",
                replace=replace,
            )
            if not acquired_lock:
                return {"status": "RUNNING"}

            try:
                invoke_lambda_async(
                    lambda_arn,
                    payload={
                        "deployment_id": DEPLOYMENT_ID,
                        "dashboard_key": dashboard_key,
                        "runtime_session_id": _normalize_runtime_session_id(runtime_session_id),
                        "runtime_tile_key": status_context["runtime_tile_key"],
                        "dashboard_tile_key": status_context["dashboard_tile_key"],
                        "tile_id": tile["id"],
                        "run_id": run_id,
                        "resolved_sql": sql,
                        "status_writer_lambda_arn": os.getenv("STRATABI_STATUS_WRITER_LAMBDA_ARN"),
                        "database": exec_cfg.get("database"),
                        "workgroup": exec_cfg.get("workgroup"),
                        "inputs": inputs,
                        "status_context": status_context,
                    }
                )
            except Exception as e:
                failed = dict(status_context)
                failed["status"] = "FAILED"
                failed["updated_at"] = _now_iso()
                failed["message"] = f"Failed to invoke async {exec_type}: {e}"
                failed["traceback"] = ""
                _get_status_table().put_item(Item=failed)
                return {
                    "status": "FAILED",
                    "message": failed["message"],
                }
            return {"status": "RUNNING"}

        return _handle_status_result(status)

    # ---------------------------------------
    # 3) CUSTOM REGISTERED MODULE LAMBDA
    # ---------------------------------------
    if exec_type == "lambda":

        if exec_cfg.get("sync"):
            return _run_lambda_sync(tile, exec_cfg, inputs, dashboard_key, runtime_session_id, trigger_kind)

        run_id = _make_run_id(
            tile=tile,
            inputs=inputs,
            dashboard_key=dashboard_key,
            runtime_session_id=runtime_session_id,
        )

        runtime_tile_key = _runtime_tile_key(
            dashboard_key=dashboard_key,
            runtime_session_id=runtime_session_id,
            tile_id=tile["id"],
        )

        status, replace = _resolve_existing(_get_tile_status(runtime_tile_key, run_id), rerun)

        if not status:
            try:
                module = resolve_module_for_execution(
                    exec_cfg["module_id"],
                    exec_cfg["lambda_index"],
                )
            except Exception as e:
                return {
                    "status": "FAILED",
                    "message": f"Failed to resolve module {exec_cfg.get('module_id')}: {e}",
                }

            status_context = _status_context(
                dashboard_key=dashboard_key,
                tile=tile,
                runtime_session_id=runtime_session_id,
                inputs=inputs,
                run_id=run_id,
                exec_type="lambda",
                module_id=module["module_id"],
            )

            status_context, acquired_lock = _put_running_status(
                status_context,
                message=f"Module Lambda invoked: {module['module_id']}",
                replace=replace,
            )

            if not acquired_lock:
                return {"status": "RUNNING"}
            
            try:
                invoke_lambda_async(
                    module["lambda_arn"],
                    payload={
                        "deployment_id": DEPLOYMENT_ID,
                        "dashboard_key": dashboard_key,
                        "runtime_session_id": _normalize_runtime_session_id(runtime_session_id),
                        "runtime_tile_key": status_context["runtime_tile_key"],
                        "dashboard_tile_key": status_context["dashboard_tile_key"],
                        "tile": tile,
                        "tile_id": tile["id"],
                        "inputs": inputs,
                        "run_id": run_id,
                        # why this run happened: load | input | run | refresh | interval —
                        # lets a module act only on an explicit ▷ (e.g. send a chat message).
                        "trigger": trigger_kind,
                        "status_writer_lambda_arn": os.getenv("STRATABI_STATUS_WRITER_LAMBDA_ARN"),
                        "status_context": status_context,
                        "module": {
                            "module_id": module["module_id"],
                            "version": module.get("version"),
                            "lambda_index": module["lambda_index"],
                            "lambda_name": module.get("lambda_name"),
                        },
                    },
                )
            except Exception as e:
                failed = dict(status_context)
                failed["status"] = "FAILED"
                failed["updated_at"] = _now_iso()
                failed["message"] = f"Failed to invoke async {exec_type}: {e}"
                failed["traceback"] = ""
                _get_status_table().put_item(Item=failed)
                return {
                    "status": "FAILED",
                    "message": failed["message"],
                }

            return {"status": "RUNNING"}

        return _handle_status_result(status)

    raise ValueError(f"Unsupported exec type: {exec_type}")