"""LLM-context + schema helpers for bring-your-own-AI workflows.

The Developer Edition makes no model calls. This module assembles the bundled core contract and
module llm_context.txt files (the Builder's Copy LLM context) and validates dashboards against the
bundled schema — the reference for building and testing your own agent tooling."""

from __future__ import annotations

import json
import logging
import os
from importlib.resources import files

logger = logging.getLogger("stratabi.llm_context")

# ---------------------------------------------------------------------------
# Bundled resources (shipped in the wheel under stratabi/data/)
# ---------------------------------------------------------------------------
def load_core_contract() -> str:
    """The core StrataBI LLM contract, read from the bundled data/docs copy.

    The bundled text uses the `<your-system-bucket>` placeholder (never a real account's
    bucket). When STRATABI_SYSTEM_BUCKET is configured, substitute it so examples point at
    the user's own bucket instead of a placeholder the model might copy verbatim."""
    try:
        text = files("stratabi.data.docs").joinpath("llm_contract.txt").read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("core llm_contract.txt load failed: %s", exc)
        return "(core llm_contract.txt unavailable)"
    bucket = os.getenv("STRATABI_SYSTEM_BUCKET")
    if bucket:
        text = text.replace("<your-system-bucket>", bucket)
    return text


def load_local_schema_text() -> str:
    """The bundled dashboard JSON schema as text (for best-effort validation)."""
    try:
        return files("stratabi.data.schemas").joinpath("dashboard.schema.json").read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("bundled dashboard.schema.json load failed: %s", exc)
        return ""


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



def _validator():
    schema = json.loads(load_local_schema_text() or "null")
    if not schema:
        return None
    try:
        from jsonschema import Draft202012Validator as V  # the schema declares draft 2020-12
    except Exception:  # noqa: BLE001 — older jsonschema
        from jsonschema import Draft7Validator as V
    return V(schema)


def _branch_errors(err):
    inst = err.instance
    if err.validator != "oneOf" or not isinstance(inst, dict) or "type" not in inst or not err.context:
        return None
    by_branch = {}
    for c in err.context:
        by_branch.setdefault(c.schema_path[0], []).append(c)
    for errs in by_branch.values():
        if not any(list(c.schema_path)[-1] == "const" and "type" in list(c.schema_path) for c in errs):
            return errs
    return None


def schema_errors(dashboard, limit: int = 5) -> list[str]:
    """Every failing rule as '<path>: <message> [<keyword>]', most specific first (capped)."""
    v = _validator()
    if v is None:
        raise RuntimeError("bundled dashboard schema unavailable")
    errs = sorted(v.iter_errors(dashboard), key=lambda e: (len(list(e.path)), list(map(str, e.path))))
    out = []
    for e in errs:
        # A block is "oneOf" nine block types; report the errors of the branch matching its `type`
        # (e.g. config.height must be a string) instead of "not valid under any of the given schemas".
        for x in (_branch_errors(e) or [e]):
            path = list(e.path) + (list(x.path) if x is not e else [])
            loc = "/" + "/".join(str(p) for p in path) if path else "/"
            out.append(f"{loc}: {x.message[:240]} [{x.validator}]")
            if len(out) >= limit:
                return out
    return out


def validate_dashboard(dashboard: dict) -> tuple[bool, str | None]:
    """Validate against the bundled canonical schema. Returns (ok, error_summary). Validation is
    never silently skipped: if it can't run, that is reported as an error."""
    try:
        errors = schema_errors(dashboard)
    except ImportError:
        return False, "Schema validation is unavailable (jsonschema is not installed)."
    except Exception as exc:  # noqa: BLE001
        return False, f"Schema validation could not run: {exc}"
    if errors:
        return False, "; ".join(errors)
    return True, None
