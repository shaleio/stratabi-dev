# stratabi/blocks/input_text.py
"""Free-text input block (dcc.Textarea / dcc.Input).

Writes its value into dashboard-input-store under input_id, exactly like input_select / input_range,
so parameterised tiles and module Lambdas read it from `inputs`. Added to support conversational and
free-form module UIs (e.g. StrataChat) without a module-owned frontend. Additive + non-breaking."""

from dash import dcc
from stratabi.core.base import Block


class InputTextBlock(Block):
    block_type = "input_text"

    def render(self):
        cfg = self.config
        input_id = cfg.get("input_id")
        if not input_id:
            raise ValueError("input_text block missing input_id.")

        value = cfg.get("value", cfg.get("default"))
        # Dynamic JSON result support: a bare string, or {"value": "..."} / {"default": "..."}.
        if isinstance(self.result, str):
            value = self.result
        elif isinstance(self.result, dict) and ("value" in self.result or "default" in self.result):
            value = self.result.get("value", self.result.get("default"))

        comp_id = {"type": "tile-input", "tile_id": input_id}
        placeholder = cfg.get("placeholder", "")
        maxlength = cfg.get("maxlength")

        if cfg.get("multiline", True):
            rows = int(cfg.get("rows", 4) or 4)
            return dcc.Textarea(
                id=comp_id,
                value=value or "",
                placeholder=placeholder,
                maxLength=maxlength,
                style={"width": "100%", "minHeight": f"{max(1, rows) * 1.6:.1f}em",
                       "resize": "vertical"},
            )

        return dcc.Input(
            id=comp_id,
            value=value or "",
            type="text",
            placeholder=placeholder,
            maxLength=maxlength,
            debounce=bool(cfg.get("debounce", True)),
            style={"width": "100%"},
        )
