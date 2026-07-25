"""StrataBI AI helpers"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from importlib.resources import files

DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


# ---------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
def _docs_base_url() -> str:
    return os.getenv("STRATABI_DOCS_BASE_URL", "https://shaleio.com").strip().rstrip("/")


# ---------------------------------------------------------------------------
# Module context from S3 (llm_context.txt, with legacy fallback)
# ---------------------------------------------------------------------------
def load_module_context(module_id: str) -> str | None:
    """Read modules/<module_id>/llm_context.txt from the system bucket.

    Falls back to the legacy llm_contract.txt filename. Returns None when no
    context object exists (or on any access error — never raises to the UI).
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
        from ..core.s3_loader import get_system_bucket, get_module_prefix
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("module context deps unavailable: %s", exc)
        return None

    s3 = boto3.client("s3")
    try:
        bucket = get_system_bucket()
        prefix = get_module_prefix().rstrip("/")
    except Exception as exc:
        logger.warning("module context config unavailable: %s", exc)
        return None

    for fname in ("llm_context.txt", "llm_contract.txt"):
        key = f"{prefix}/{module_id}/{fname}"
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            return obj["Body"].read().decode("utf-8")
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404", "NoSuchBucket"}:
                continue
            logger.warning("module context load error %s: %s", key, exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("module context load error %s: %s", key, exc)
            return None
    return None


def assemble_llm_context(selected_module_ids: list[str] | None = None) -> str:
    """Core contract plus the llm_context.txt of each selected module."""
    selected = selected_module_ids or []
    sections = ["# StrataBI Core LLM Contract", load_core_contract()]

    for module_id in selected:
        if not module_id:
            continue
        ctx = load_module_context(module_id)
        if ctx:
            sections.append(f"\n\n# Module LLM Context: {module_id}\n{ctx}")
        else:
            sections.append(
                f"\n\n# Module LLM Context: {module_id}\n"
                "(No llm_context.txt found for module.)"
            )
    return "\n\n".join(sections)



def validate_dashboard(dashboard: dict) -> tuple[bool, str | None]:
    """Best-effort schema validation. Returns (ok, first_error_message)."""
    try:
        from jsonschema import Draft7Validator
    except Exception:
        return True, None

    schema_text = load_local_schema_text()
    if not schema_text:
        return True, None

    try:
        schema = json.loads(schema_text)
        errors = sorted(Draft7Validator(schema).iter_errors(dashboard), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            loc = "/".join(str(p) for p in first.path)
            return False, f"{first.message}" + (f" (at /{loc})" if loc else "")
        return True, None
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("schema validation skipped: %s", exc)
        return True, None


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def _user_message(contract: str, doc_context: str, intent: str) -> str:
    return (
        f"# Core contract\n{contract}\n\n"
        f"# Reference docs / schema\n{doc_context}\n\n"
        f"# User intent\n{intent.strip()}\n\n"
        "Return the StrataBI dashboard JSON now."
    )