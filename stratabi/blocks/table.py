"""Table block — renders a tile's dataframe result as an AG Grid data table."""
import os

import dash_ag_grid as dag
from dash import html
from stratabi.core.base import Block


# App themes that are dark; mirrors plotly_utils._DARK_THEMES. Used to pick a
# sensible default AG Grid theme when className and STRATABI_AGGRID_THEME are unset.
_DARK_THEMES = {"guildmaster", "cyborg", "darkly", "slate", "solar", "superhero", "vapor"}


def _default_aggrid_theme() -> str:
    """Default AG Grid CSS theme for table blocks. STRATABI_AGGRID_THEME overrides;
    otherwise follows the app theme: ag-theme-alpine-dark on dark themes,
    ag-theme-alpine on light themes."""
    explicit = os.getenv("STRATABI_AGGRID_THEME", "").strip()
    if explicit:
        return explicit
    theme = os.getenv("STRATABI_THEME", "guildmaster").strip().lower()
    return "ag-theme-alpine-dark" if theme in _DARK_THEMES else "ag-theme-alpine"


class TableBlock(Block):
    block_type = "table"

    def render(self):
        df = self.result

        if df is None:
            return html.Div("Table block has no result.", className="text-muted")

        if not hasattr(df, "to_dict"):
            raise ValueError(f"Table block expected a dataframe result.")

        column_defs = self.config.get("column_defs")

        if not column_defs:
            column_defs = [
                {
                    "field": col,
                    "filter": True,
                    "sortable": True,
                    "resizable": True,
                }
                for col in df.columns
            ]

        default_col_def = {
            "sortable": True,
            "filter": True,
            "resizable": True,
            **self.config.get("default_col_def", {}),
        }

        return dag.AgGrid(
            id=self.config.get("grid_id"),
            rowData=df.to_dict("records"),
            columnDefs=column_defs,
            defaultColDef=default_col_def,
            dashGridOptions={
                # AG Grid v33 defaults to the Theming API and ignores the
                # ag-theme-* className unless we opt back into legacy CSS themes.
                "theme": "legacy",
                "pagination": self.config.get("pagination", True),
                "paginationPageSize": self.config.get("page_size", 25),
                "animateRows": False,
                **self.config.get("dash_grid_options", {}),
            },
            className=self.config.get("className", _default_aggrid_theme()),
            style={
                "height": self.config.get("height", "500px"),
                "width": "100%",
                **self.config.get("style", {}),
            },
        )