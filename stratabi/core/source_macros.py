# stratabi/core/source_macros.py

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from io import StringIO
from typing import Any
from urllib.parse import urlparse

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.fs as pafs

glue = boto3.client("glue")
s3 = boto3.client("s3")


SOURCE_MACRO_PATTERN = re.compile(
    r"!(parquet|csv)\(\s*(['\"])(.*?)\2\s*\)",
    flags=re.IGNORECASE,
)

DEFAULT_CATALOG_DATABASE = os.getenv("STRATABI_CATALOG_DATABASE", "stratabi")
DEFAULT_SOURCE_TABLE_PREFIX = os.getenv("STRATABI_SOURCE_TABLE_PREFIX", "__src")




@dataclass(frozen=True)
class S3Location:
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


@dataclass(frozen=True)
class SourceMacro:
    raw: str
    source_format: str
    source_uri: str


@dataclass
class ResolvedSource:
    raw: str
    source_format: str
    source_uri: str
    source_bucket: str
    source_key: str
    table_location: str
    database: str
    table_name: str
    qualified_table: str
    columns: list[dict[str, str]] = field(default_factory=list)
    created: bool = False
    existed: bool = False


@dataclass
class SourceResolutionResult:
    original_sql: str
    resolved_sql: str
    sources: list[ResolvedSource]


class SourceMacroError(Exception):
    pass


class SourceMacroResolver:
    """
    Resolves StrataBI SQL source macros before Athena execution.

    Supported MVP macros:

      !parquet('s3://bucket/path/file.parquet')
      !csv('s3://bucket/path/file.csv')

    These are NOT Athena SQL. StrataBI resolves them by creating/reusing
    deterministic external tables in the StrataBI Glue database and rewriting
    the SQL before submission to Athena.
    """

    def __init__(
        self,
        *,
        database: str | None = None,
        source_table_prefix: str | None = None,
    ):
        self.database = database or DEFAULT_CATALOG_DATABASE
        self.source_table_prefix = source_table_prefix or DEFAULT_SOURCE_TABLE_PREFIX

    def resolve(self, sql: str, *, ensure_tables: bool = True) -> SourceResolutionResult:
        if not sql:
            return SourceResolutionResult(
                original_sql=sql,
                resolved_sql=sql,
                sources=[],
            )

        resolved_sources: list[ResolvedSource] = []

        def replace(match: re.Match) -> str:
            source_format = match.group(1).lower()
            source_uri = match.group(3).strip()
            raw = match.group(0)

            source = self._resolve_source(
                raw=raw,
                source_format=source_format,
                source_uri=source_uri,
                ensure_table=ensure_tables,
            )

            resolved_sources.append(source)
            return source.qualified_table

        resolved_sql = SOURCE_MACRO_PATTERN.sub(replace, sql)

        return SourceResolutionResult(
            original_sql=sql,
            resolved_sql=resolved_sql,
            sources=resolved_sources,
        )

    def _resolve_source(
        self,
        *,
        raw: str,
        source_format: str,
        source_uri: str,
        ensure_table: bool,
    ) -> ResolvedSource:
        if source_format not in {"parquet", "csv"}:
            raise SourceMacroError(f"Unsupported source macro format: {source_format}")

        location = parse_s3_uri(source_uri)

        table_location = resolve_table_location(
            location=location,
            source_format=source_format,
        )

        table_name = make_source_table_name(
            source_format=source_format,
            source_uri=source_uri,
            prefix=self.source_table_prefix,
        )

        qualified_table = quote_qualified_table(self.database, table_name)

        source = ResolvedSource(
            raw=raw,
            source_format=source_format,
            source_uri=source_uri,
            source_bucket=location.bucket,
            source_key=location.key,
            table_location=table_location,
            database=self.database,
            table_name=table_name,
            qualified_table=qualified_table,
        )

        if ensure_table:
            self.ensure_table(source)

        return source

    def ensure_table(self, source: ResolvedSource) -> ResolvedSource:
        """
        Create the Glue external table if it does not exist.

        Existing deterministic tables are reused.
        """

        try:
            response = glue.get_table(
                DatabaseName=source.database,
                Name=source.table_name,
            )

            existing_table = response.get("Table", {})
            source.existed = True
            source.columns = existing_table.get("StorageDescriptor", {}).get("Columns", [])
            return source

        except glue.exceptions.EntityNotFoundException:
            pass

        columns = infer_source_columns(
            source_format=source.source_format,
            source_uri=source.source_uri,
        )

        table_input = build_glue_table_input(
            source=source,
            columns=columns,
        )

        glue.create_table(
            DatabaseName=source.database,
            TableInput=table_input,
        )

        source.created = True
        source.columns = columns
        return source


def parse_s3_uri(uri: str) -> S3Location:
    if not uri or not uri.startswith("s3://"):
        raise SourceMacroError(f"Source macro requires a full s3:// URI. Got: {uri}")

    parsed = urlparse(uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")

    if not bucket or not key:
        raise SourceMacroError(f"Invalid S3 URI: {uri}")

    return S3Location(bucket=bucket, key=key)


def make_source_table_name(
    *,
    source_format: str,
    source_uri: str,
    prefix: str = DEFAULT_SOURCE_TABLE_PREFIX,
) -> str:
    digest = hashlib.sha256(
        f"{source_format}|{normalize_source_uri(source_uri)}".encode("utf-8")
    ).hexdigest()[:16]

    safe_format = re.sub(r"[^a-zA-Z0-9_]", "_", source_format.lower())
    safe_prefix = re.sub(r"[^a-zA-Z0-9_]", "_", prefix.strip("_").lower())

    return f"__{safe_prefix}_{safe_format}_{digest}"


def normalize_source_uri(uri: str) -> str:
    """
    Normalize only enough to avoid accidental duplicate table names.

    Do not over-normalize S3 paths. S3 keys are case-sensitive.
    """
    uri = uri.strip()

    if uri.endswith("/"):
        return uri

    return uri


def quote_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def quote_qualified_table(database: str, table: str) -> str:
    return f"{quote_identifier(database)}.{quote_identifier(table)}"


def resolve_table_location(
    *,
    location: S3Location,
    source_format: str,
) -> str:
    """
    Athena external tables point at prefixes, not individual files.

    If the macro points at a file, use its parent prefix.
    If it points at a prefix, use the prefix as-is.
    """

    key = location.key

    if key.endswith("/"):
        prefix = key
    elif key.lower().endswith(f".{source_format}"):
        prefix = key.rsplit("/", 1)[0] + "/" if "/" in key else ""
    else:
        # Treat extensionless values as prefixes.
        prefix = key.rstrip("/") + "/"

    return f"s3://{location.bucket}/{prefix}"


def select_sample_object(source_uri: str, source_format: str) -> S3Location:
    """
    Return a representative object for schema inference.

    If the URI points to a file, use it directly.
    If it points to a prefix, find the first matching object.
    """

    location = parse_s3_uri(source_uri)
    key = location.key

    if key.lower().endswith(f".{source_format}"):
        return location

    prefix = key if key.endswith("/") else f"{key}/"

    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=location.bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            obj_key = obj.get("Key", "")

            if obj_key.lower().endswith(f".{source_format}"):
                return S3Location(bucket=location.bucket, key=obj_key)

    raise SourceMacroError(
        f"No .{source_format} files found under s3://{location.bucket}/{prefix}"
    )


def infer_source_columns(
    *,
    source_format: str,
    source_uri: str,
) -> list[dict[str, str]]:
    if source_format == "parquet":
        return infer_parquet_columns(source_uri)

    if source_format == "csv":
        return infer_csv_columns(source_uri)

    raise SourceMacroError(f"Unsupported source format: {source_format}")


def infer_parquet_columns(source_uri: str) -> list[dict[str, str]]:
    """
    Infer Parquet columns from file metadata/schema without loading the full dataset.
    """
    sample = select_sample_object(source_uri, "parquet")

    s3_fs = pafs.S3FileSystem()
    path = f"{sample.bucket}/{sample.key}"

    schema = pq.read_schema(path, filesystem=s3_fs)

    return arrow_schema_to_athena_columns(schema)

def arrow_type_to_athena(dtype: pa.DataType) -> str:
    if pa.types.is_int8(dtype) or pa.types.is_int16(dtype) or pa.types.is_int32(dtype):
        return "int"

    if pa.types.is_int64(dtype):
        return "bigint"

    if pa.types.is_uint8(dtype) or pa.types.is_uint16(dtype) or pa.types.is_uint32(dtype):
        return "bigint"

    if pa.types.is_uint64(dtype):
        return "decimal(20,0)"

    if pa.types.is_float32(dtype):
        return "float"

    if pa.types.is_float64(dtype):
        return "double"

    if pa.types.is_boolean(dtype):
        return "boolean"

    if pa.types.is_date(dtype):
        return "date"

    if pa.types.is_timestamp(dtype):
        return "timestamp"

    if pa.types.is_string(dtype) or pa.types.is_large_string(dtype):
        return "string"

    if pa.types.is_binary(dtype) or pa.types.is_large_binary(dtype):
        return "binary"

    # MVP fallback. Complex/list/struct/map can be added later.
    return "string"

def arrow_schema_to_athena_columns(schema: pa.Schema) -> list[dict[str, str]]:
    columns = []

    for field in schema:
        columns.append(
            {
                "Name": str(field.name),
                "Type": arrow_type_to_athena(field.type),
            }
        )

    if not columns:
        raise SourceMacroError("Could not infer any columns from Parquet schema.")

    return columns

def infer_csv_columns(source_uri: str) -> list[dict[str, str]]:
    sample = select_sample_object(source_uri, "csv")
    obj = s3.get_object(Bucket=sample.bucket, Key=sample.key)
    text = obj["Body"].read().decode("utf-8")

    df = pd.read_csv(StringIO(text), nrows=1000)
    return dataframe_columns_to_athena(df)


def dataframe_columns_to_athena(df: pd.DataFrame) -> list[dict[str, str]]:
    columns = []

    for col_name, dtype in df.dtypes.items():
        columns.append(
            {
                "Name": str(col_name),
                "Type": pandas_dtype_to_athena(dtype),
            }
        )

    if not columns:
        raise SourceMacroError("Could not infer any columns from source.")

    return columns


def pandas_dtype_to_athena(dtype: Any) -> str:
    dtype_str = str(dtype).lower()

    if dtype_str.startswith("int"):
        return "bigint"

    if dtype_str.startswith("uint"):
        return "bigint"

    if dtype_str.startswith("float"):
        return "double"

    if dtype_str in {"bool", "boolean"}:
        return "boolean"

    if "datetime" in dtype_str:
        return "timestamp"

    if dtype_str == "date":
        return "date"

    return "string"


def build_glue_table_input(
    *,
    source: ResolvedSource,
    columns: list[dict[str, str]],
) -> dict[str, Any]:
    if source.source_format == "parquet":
        return build_parquet_table_input(source=source, columns=columns)

    if source.source_format == "csv":
        return build_csv_table_input(source=source, columns=columns)

    raise SourceMacroError(f"Unsupported source format: {source.source_format}")


def base_table_parameters(source: ResolvedSource) -> dict[str, str]:
    return {
        "classification": source.source_format,
        "EXTERNAL": "TRUE",
        "stratabi.source_macro": source.raw,
        "stratabi.source_format": source.source_format,
        "stratabi.source_uri": source.source_uri,
        "stratabi.managed": "true",
        "stratabi.table_kind": "source_macro",
    }


def build_parquet_table_input(
    *,
    source: ResolvedSource,
    columns: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "Name": source.table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": base_table_parameters(source),
        "StorageDescriptor": {
            "Columns": columns,
            "Location": source.table_location,
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {
                    "serialization.format": "1",
                },
            },
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
    }


def build_csv_table_input(
    *,
    source: ResolvedSource,
    columns: list[dict[str, str]],
) -> dict[str, Any]:
    parameters = base_table_parameters(source)
    parameters["skip.header.line.count"] = "1"

    return {
        "Name": source.table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": parameters,
        "StorageDescriptor": {
            "Columns": columns,
            "Location": source.table_location,
            "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe",
                "Parameters": {
                    "field.delim": ",",
                    "serialization.format": ",",
                },
            },
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
    }