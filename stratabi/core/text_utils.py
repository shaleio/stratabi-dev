"""Small text helpers shared by the runtime.

`coerce_lines` lets multiline fields (SQL, markdown, raw HTML) be authored either
as a single string or as an array of strings joined with newlines. Array-of-lines
keeps embedded SQL/markdown readable in the JSON dashboard and in git diffs, while
the runtime always works with a normalized string. A single string passes through
unchanged; anything else (e.g. an unresolved source ref) is returned as-is.
"""

from __future__ import annotations

from typing import Any


def coerce_lines(value: Any, sep: str = "\n") -> Any:
    if isinstance(value, list):
        return sep.join(str(v) for v in value)
    return value
