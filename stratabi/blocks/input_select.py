"""Input-select block — a dropdown input whose selection feeds dependent tiles."""
# stratabi/blocks/input_select.py

from dash import dcc, html
from stratabi.core.base import Block


def _normalize_options(options):
    if not options:
        return []

    normalized = []

    for opt in options:
        if isinstance(opt, dict):
            if "label" in opt and "value" in opt:
                normalized.append(opt)
            elif "value" in opt:
                normalized.append({
                    "label": str(opt["value"]),
                    "value": opt["value"],
                })
            else:
                continue
        else:
            normalized.append({
                "label": str(opt),
                "value": opt,
            })

    return normalized


class InputSelectBlock(Block):
    block_type = "input_select"

    def render(self):
        cfg = self.config

        component = cfg.get("component", "dropdown")
        options = cfg.get("options", [])
        value = cfg.get("value")

        block_id = cfg.get("input_id")
        if not block_id:
            raise ValueError("input_select block missing input_id.")


        # Dynamic JSON result support.
        # Supported:
        #   result = [{"label": "...", "value": "..."}, ...]
        #   result = {"options": [...], "value": "..."}
        #   result = {"options": [...], "default": "..."}
        if isinstance(self.result, list):
            options = self.result

        elif isinstance(self.result, dict):
            options = (
                self.result.get("options")
                or self.result.get("items")
                or options
            )

            value = (
                self.result.get("value")
                if "value" in self.result
                else self.result.get("default", value)
            )

        options = _normalize_options(options)
        valid_values = {opt.get("value") for opt in options}

        is_multi_value = cfg.get("multi", False) or component == "checklist"

        # Avoid rendering a value that is no longer valid after dynamic refresh.
        if value is not None:
            if is_multi_value:
                if not isinstance(value, list):
                    value = [value]
                value = [v for v in value if v in valid_values]
            elif value not in valid_values:
                value = None

        common_kwargs = {
            "id": {
                "type": "tile-input",
                "tile_id": block_id,
            },
            "options": options,
            "value": value,
        }

        if component == "dropdown":
            return dcc.Dropdown(
                **common_kwargs,
                multi=cfg.get("multi", False),
                clearable=cfg.get("clearable", True),
                placeholder=cfg.get("placeholder"),
            )

        if component == "radio":
            return dcc.RadioItems(**common_kwargs)

        if component == "checklist":
            return dcc.Checklist(**common_kwargs)

        raise ValueError(f"Unknown input_select component: {component}")