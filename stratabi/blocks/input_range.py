"""Input-range block — a numeric slider input whose value feeds dependent tiles."""
# stratabi/blocks/input_range.py

from dash import dcc
from stratabi.core.base import Block


class InputRangeBlock(Block):
    block_type = "input_range"

    def render(self):
        cfg = self.config
        component = cfg.get("component", "slider")
        block_id = cfg["input_id"]

        if component == "slider":
            return dcc.Slider(
                id=block_id,
                min=cfg.get("min"),
                max=cfg.get("max"),
                step=cfg.get("step"),
                value=cfg.get("value"),
                marks=cfg.get("marks")
            )

        if component == "range_slider":
            return dcc.RangeSlider(
                id=block_id,
                min=cfg.get("min"),
                max=cfg.get("max"),
                step=cfg.get("step"),
                value=cfg.get("value"),
                marks=cfg.get("marks")
            )

        if component == "date":
            return dcc.DatePickerSingle(
                id=block_id,
                date=cfg.get("value"),
                min_date_allowed=cfg.get("min"),
                max_date_allowed=cfg.get("max")
            )

        if component == "date_range":
            return dcc.DatePickerRange(
                id=block_id,
                start_date=cfg.get("start"),
                end_date=cfg.get("end"),
                min_date_allowed=cfg.get("min"),
                max_date_allowed=cfg.get("max")
            )

        raise ValueError(f"Unknown input_range component: {component}")
