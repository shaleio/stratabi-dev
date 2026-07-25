"""Plotly block — renders a Plotly figure, either static (inline `figure`) or bound to a tile's dataframe result via @column references."""
# stratabi/blocks/plotly.py

from dash import dcc, html
import plotly.graph_objects as go

from stratabi.core.base import Block
from stratabi.core.binder import bind_dataframe
from stratabi.core.plotly_utils import apply_plotly_template, coerce_dataframe


class PlotlyBlock(Block):
    block_type = "plotly"

    def render(self):
        figure_spec = self.config.get("figure")

        if not figure_spec:
            raise ValueError("Plotly block missing figure config.")

        try:
            df = coerce_dataframe(self.result)
        except Exception as e:
            raise ValueError(f"Plotly block failed to generate dataframe result: {e}")

        themed_figure_spec = apply_plotly_template(figure_spec, self.config)

        if df is None:
            bound_figure = themed_figure_spec
        else:
            bound_figure = bind_dataframe(themed_figure_spec, df)

        fig = go.Figure(bound_figure)

        return dcc.Graph(
            figure=fig,
            config={
                "responsive": True,
                "displayModeBar": True,
                **self.config.get("graph_config", {}),
            },
            style={
                "width": "100%",
                "height": self.config.get("height", "400px"),
                **self.config.get("style", {}),
            },
        )