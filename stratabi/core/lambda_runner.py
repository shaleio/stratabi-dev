# stratabi/core/lambda_runner.py

import json
import os
from typing import Any

import boto3


lambda_client = boto3.client("lambda")
dynamodb = boto3.resource("dynamodb")

MODULE_REGISTRY_TABLE_NAME = os.getenv(
    "STRATABI_MODULE_REGISTRY_TABLE",
    "stratabi_module_registry",
)

MODULE_REGISTRY_TABLE = dynamodb.Table(MODULE_REGISTRY_TABLE_NAME)


def invoke_lambda_async(lambda_arn: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not lambda_arn:
        raise ValueError("lambda_arn is required")

    response = lambda_client.invoke(
        FunctionName=lambda_arn,
        InvocationType="Event",
        Payload=json.dumps(payload, default=str).encode("utf-8"),
    )

    return {
        "status_code": response.get("StatusCode"),
        "request_id": response.get("ResponseMetadata", {}).get("RequestId"),
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

    response = MODULE_REGISTRY_TABLE.get_item(
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