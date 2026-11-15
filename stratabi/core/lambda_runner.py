# stratabi/core/lambda_runner.py

import json
import os
from typing import Any

import boto3


MODULE_REGISTRY_TABLE_NAME = os.getenv(
    "STRATABI_MODULE_REGISTRY_TABLE",
    "stratabi_module_registry",
)

# AWS clients are created lazily, not at import time: a module-level
# boto3.client("lambda") raises NoRegionError when imported without a region
# configured, which breaks `import stratabi.core.runner` for tests and tooling.
_lambda_client = None
_module_registry_table = None


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        from stratabi.core.config import aws_region
        _lambda_client = boto3.client("lambda", region_name=aws_region())
    return _lambda_client


def _get_module_registry_table():
    global _module_registry_table
    if _module_registry_table is None:
        from stratabi.core.config import aws_region
        _module_registry_table = boto3.resource(
            "dynamodb", region_name=aws_region()
        ).Table(MODULE_REGISTRY_TABLE_NAME)
    return _module_registry_table


def invoke_lambda_async(lambda_arn: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not lambda_arn:
        raise ValueError("lambda_arn is required")

    response = _get_lambda_client().invoke(
        FunctionName=lambda_arn,
        InvocationType="Event",
        Payload=json.dumps(payload, default=str).encode("utf-8"),
    )

    return {
        "status_code": response.get("StatusCode"),
        "request_id": response.get("ResponseMetadata", {}).get("RequestId"),
    }


_sync_clients: dict[int, Any] = {}

SYNC_TIMEOUT_DEFAULT = 30
SYNC_TIMEOUT_MAX = 120


def invoke_lambda_sync(lambda_arn: str, payload: dict[str, Any], timeout_seconds: int = SYNC_TIMEOUT_DEFAULT) -> dict[str, Any]:
    """RequestResponse invoke for `exec.sync` tiles. No retries (a retried action tile could
    act twice); the read timeout bounds how long the tile's callback can block."""
    if not lambda_arn:
        raise ValueError("lambda_arn is required")
    timeout = max(1, min(int(timeout_seconds or SYNC_TIMEOUT_DEFAULT), SYNC_TIMEOUT_MAX))
    client = _sync_clients.get(timeout)
    if client is None:
        from botocore.config import Config
        from stratabi.core.config import aws_region
        client = boto3.client(
            "lambda",
            region_name=aws_region(),
            config=Config(read_timeout=timeout + 5, connect_timeout=5, retries={"max_attempts": 0}),
        )
        _sync_clients[timeout] = client

    response = client.invoke(
        FunctionName=lambda_arn,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload, default=str).encode("utf-8"),
    )
    raw = response["Payload"].read() if response.get("Payload") is not None else b""
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        body = {"raw": raw.decode("utf-8", errors="replace")}
    return {
        "status_code": response.get("StatusCode"),
        "function_error": response.get("FunctionError"),
        "payload": body if isinstance(body, dict) else {"result": body},
    }


def resolve_module_for_execution(module_id: str, lambda_index: int) -> dict[str, Any]:
    """
    Resolve a module_id + lambda_index into a concrete Lambda config.

    list shape:
    {
      "module_id": "sales_demo",
      "status": "active",
      "version": "0.1.0",
      "lambda_arns": [
        "arn:aws:lambda:..."
      ],
      "lambda_function_names": [
        "stratabi-sales_demo-sales_summary"
      ]
    }
    """

    if not module_id:
        raise ValueError("module_id is required")

    if lambda_index is None:
        raise ValueError("lambda_index is required")

    try:
        lambda_index = int(lambda_index)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"lambda_index must be an integer: {lambda_index}") from exc

    if lambda_index < 0:
        raise ValueError(f"lambda_index must be >= 0: {lambda_index}")

    response = _get_module_registry_table().get_item(
        Key={"module_id": module_id}
    )

    module = response.get("Item")

    if not module:
        raise ValueError(f"Module not found in registry: {module_id}")

    if module.get("status", "active") != "active":
        raise ValueError(f"Module is not active: {module_id}")

    version = module.get("version")

    # -------------------------------------------------------
    # Registry top-level lambda_arns list format
    # -------------------------------------------------------
    lambda_arns = module.get("lambda_arns")

    if lambda_arns is not None:
        if not isinstance(lambda_arns, list):
            raise ValueError(f"Module lambda_arns must be a list: {module_id}")

        if lambda_index >= len(lambda_arns):
            raise ValueError(
                f"lambda_index {lambda_index} out of range for module {module_id}; "
                f"module defines {len(lambda_arns)} lambda ARN(s)"
            )

        lambda_arn = lambda_arns[lambda_index]

        if not lambda_arn:
            raise ValueError(
                f"Module {module_id} lambda_index {lambda_index} missing lambda ARN"
            )

        lambda_function_names = module.get("lambda_function_names") or []

        lambda_name = None
        if (
            isinstance(lambda_function_names, list)
            and lambda_index < len(lambda_function_names)
        ):
            lambda_name = lambda_function_names[lambda_index]

        return {
            "module_id": module_id,
            "version": version,
            "lambda_index": lambda_index,
            "lambda_name": lambda_name,
            "lambda_arn": lambda_arn,
            "module": module,
            "lambda": {
                "name": lambda_name,
                "lambda_arn": lambda_arn,
            },
        }