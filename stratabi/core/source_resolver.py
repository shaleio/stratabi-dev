# stratabi/core/source_resolver.py

import json
from urllib.parse import urlparse

import boto3


s3 = boto3.client("s3")


# stratabi/core/source_resolver.py

import json
import os
from typing import Any
from urllib.parse import urlparse

import boto3


class SourceResolver:
    """
    Resolves StrataBI source values.

    Supports dashboard values like:

        {"?source": "region_options"}

    Flow:
      1. Detect source reference
      2. Look up source_id in DynamoDB source registry
      3. Validate active source
      4. Load source payload from S3
      5. Parse payload based on value_type
      6. Return resolved value

    Expected DynamoDB item shape:

        {
          "source_id": "region_options",
          "source_type": "s3",
          "value_type": "json",
          "s3_uri": "s3://bucket/analyst/source_values/region_options.json",
          "content_type": "application/json",
          "status": "active"
        }
    """

    def __init__(
        self,
        *,
        table_name: str | None = None,
        region_name: str | None = None,
        dynamodb_resource=None,
        s3_client=None,
    ):
        self.table_name = table_name or os.getenv(
            "STRATABI_SOURCE_REGISTRY_TABLE",
            "stratabi_source_registry",
        )

        self.dynamodb = dynamodb_resource or boto3.resource(
            "dynamodb",
            region_name=region_name,
        )

        self.s3 = s3_client or boto3.client(
            "s3",
            region_name=region_name,
        )

        self.table = self.dynamodb.Table(self.table_name)

    @staticmethod
    def is_source_ref(value: Any) -> bool:
        return isinstance(value, dict) and "?source" in value

    @staticmethod
    def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
        parsed = urlparse(s3_uri)

        if parsed.scheme != "s3":
            raise ValueError(f"Expected s3:// URI, got: {s3_uri}")

        bucket = parsed.netloc
        key = parsed.path.lstrip("/")

        if not bucket or not key:
            raise ValueError(f"Invalid S3 URI: {s3_uri}")

        return bucket, key

    def get_source_item(self, source_id: str) -> dict[str, Any]:
        if not source_id:
            raise ValueError("source_id is required")

        response = self.table.get_item(
            Key={
                "source_id": source_id,
            }
        )

        item = response.get("Item")

        if not item:
            raise ValueError(f"Source not found in registry: {source_id}")

        status = item.get("status", "active")

        if status != "active":
            raise ValueError(f"Source is not active: {source_id}")

        return item

    def load_payload(self, item: dict[str, Any]) -> str:
        source_type = item.get("source_type", "s3")

        if source_type != "s3":
            raise ValueError(f"Unsupported source_type: {source_type}")

        s3_uri = item.get("s3_uri")

        if not s3_uri:
            raise ValueError(
                f"Source registry item missing s3_uri: {item.get('source_id')}"
            )

        bucket, key = self.parse_s3_uri(s3_uri)

        response = self.s3.get_object(
            Bucket=bucket,
            Key=key,
        )

        body = response["Body"].read()

        return body.decode("utf-8")

    def parse_payload(
        self,
        raw: str,
        *,
        value_type: str | None = None,
        expected_type: str | None = None,
    ) -> Any:
        """
        Parse the raw source payload.

        value_type comes from Dynamo item.
        expected_type comes from the calling field, e.g.:
          - json
          - text
          - markdown
          - html
          - sql
          - plotly_figure
          - dropdown_options

        For MVP:
          json / plotly_figure / dropdown_options -> json.loads(raw)
          text / markdown / html / sql -> raw string
        """
        resolved_type = value_type or expected_type or "text"

        if resolved_type in {"json", "plotly_figure", "dropdown_options"}:
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Source payload expected JSON but could not be parsed: {exc}"
                ) from exc

        if resolved_type in {"text", "markdown", "html", "sql"}:
            return raw

        raise ValueError(f"Unsupported source value_type: {resolved_type}")

    def validate_resolved_value(
        self,
        value: Any,
        *,
        expected_type: str | None = None,
        source_id: str | None = None,
    ) -> Any:
        """
        Lightweight field-level validation.

        This does not replace JSON Schema. It only catches obvious bad source payloads.
        """
        if expected_type is None:
            return value

        if expected_type in {"text", "markdown", "html", "sql"}:
            if not isinstance(value, str):
                raise ValueError(
                    f"Source {source_id} expected {expected_type} string, got {type(value).__name__}"
                )

        elif expected_type == "dropdown_options":
            if not isinstance(value, list):
                raise ValueError(
                    f"Source {source_id} expected dropdown options list, got {type(value).__name__}"
                )

            for idx, option in enumerate(value):
                if not isinstance(option, dict):
                    raise ValueError(
                        f"Source {source_id} dropdown option {idx} must be an object"
                    )

                if "label" not in option or "value" not in option:
                    raise ValueError(
                        f"Source {source_id} dropdown option {idx} must include label and value"
                    )

        elif expected_type == "plotly_figure":
            if not isinstance(value, dict):
                raise ValueError(
                    f"Source {source_id} expected Plotly figure object, got {type(value).__name__}"
                )

            if "data" not in value:
                raise ValueError(
                    f"Source {source_id} Plotly figure must include data"
                )

        elif expected_type == "json":
            # Any valid JSON value is allowed.
            pass

        return value

    def resolve_source_ref(
        self,
        source_ref: dict[str, Any],
        *,
        expected_type: str | None = None,
    ) -> Any:
        if not self.is_source_ref(source_ref):
            raise ValueError(f"Not a source reference: {source_ref}")

        source_id = source_ref["?source"]

        item = self.get_source_item(source_id)
        raw = self.load_payload(item)

        value = self.parse_payload(
            raw,
            value_type=item.get("value_type"),
            expected_type=expected_type,
        )

        return self.validate_resolved_value(
            value,
            expected_type=expected_type,
            source_id=source_id,
        )

    def resolve_value(
        self,
        value: Any,
        *,
        expected_type: str | None = None,
    ) -> Any:
        """
        Resolve a single value if it is a ?source reference.
        Otherwise return it unchanged.
        """
        if self.is_source_ref(value):
            return self.resolve_source_ref(
                value,
                expected_type=expected_type,
            )

        return value