"""Plotly-resampler block — a Plotly figure with server-side downsampling for large series."""
from dash import dcc, html
from plotly_resampler import FigureResampler
import plotly.graph_objects as go

from stratabi.core.base import Block
from stratabi.core.binder import bind_dataframe
from stratabi.core.plotly_utils import apply_plotly_template, coerce_dataframe


class PlotlyResamplerBlock(Block):
    block_type = "plotly_resampler"

    def render(self):
        figure_spec = self.config.get("figure")

        if not figure_spec:
            raise ValueError("Plotly Resampler block missing figure config.")

        try:
            df = coerce_dataframe(self.result)
        except Exception as e:
            raise ValueError(f"Plotly Resampler block failed to generate dataframe result: {e}")

        themed_figure_spec = apply_plotly_template(figure_spec, self.config)

        if df is None:
            bound_figure = themed_figure_spec
        else:
            bound_figure = bind_dataframe(themed_figure_spec, df)

        fig = go.Figure(bound_figure)
        fr = FigureResampler(fig)

        return dcc.Graph(
            figure=fr,
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