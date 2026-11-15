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

        # Sliders write into dashboard-input-store like every other input: same pattern id as
        # input_select / input_text (a plain string id was never seen by the store, so the chosen
        # value silently never reached tiles). The value is shown on the handle.
        input_component_id = {"type": "tile-input", "tile_id": block_id}
        initial = cfg.get("value", cfg.get("default"))
        if initial is None and component == "slider":
            initial = cfg.get("min")
        tooltip = {"placement": "bottom", "always_visible": True}

        if component == "slider":
            return dcc.Slider(
                id=input_component_id,
                min=cfg.get("min"),
                max=cfg.get("max"),
                step=cfg.get("step"),
                value=initial,
                marks=cfg.get("marks"),
                tooltip=tooltip,
            )

        if component == "range_slider":
            return dcc.RangeSlider(
                id=input_component_id,
                min=cfg.get("min"),
                max=cfg.get("max"),
                step=cfg.get("step"),
                value=initial,
                marks=cfg.get("marks"),
                tooltip=tooltip,
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
