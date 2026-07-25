# stratabi/core/plotly_utils.py

import os
from copy import deepcopy
from typing import Any
import pandas as pd

from stratabi.core.source_resolver import SourceResolver


source_resolver = SourceResolver()


def _resolve_theme_value(value: Any) -> Any:
    """
    Resolve Plotly theme/template values.

    Supports:
      "plotly_dark"
      {"?source": "themes.default.plotly_template"}
    """
    if source_resolver.is_source_ref(value):
        return source_resolver.resolve_value(value)

    return value

def coerce_dataframe(result):
    """
    Normalize runtime result payloads into a pandas DataFrame.

    Returns:
      - None when no runtime result exists
      - pandas.DataFrame when result is dataframe-shaped
    """

    if result is None:
        return None

    if isinstance(result, pd.DataFrame):
        return result

    if hasattr(result, "columns"):
        return result

    if isinstance(result, list):
        return pd.DataFrame(result)

    if isinstance(result, dict):
        if "records" in result:
            return pd.DataFrame(result["records"])

        if "data" in result:
            return pd.DataFrame(result["data"])

        if "result" in result:
            inner = result["result"]

            if isinstance(inner, list):
                return pd.DataFrame(inner)

            if isinstance(inner, dict):
                if "records" in inner:
                    return pd.DataFrame(inner["records"])

                if "data" in inner:
                    return pd.DataFrame(inner["data"])

        return pd.DataFrame([result])

    raise TypeError(f"Unsupported dataframe result type: {type(result)}")

# App themes that are dark; used to pick a sensible default Plotly template when
# a figure does not set one and STRATABI_PLOTLY_TEMPLATE is unset.
_DARK_THEMES = {"guildmaster", "cyborg", "darkly", "slate", "solar", "superhero", "vapor"}


def _default_plotly_template() -> str | None:
    """Default Plotly template for plotly / plotly_resampler blocks.

    STRATABI_PLOTLY_TEMPLATE overrides everything. Otherwise it follows the app
    theme: plotly_dark on dark themes, seaborn on light themes.
    """
    explicit = os.getenv("STRATABI_PLOTLY_TEMPLATE", "").strip()
    if explicit:
        return explicit
    theme = os.getenv("STRATABI_THEME", "guildmaster").strip().lower()
    return "plotly_dark" if theme in _DARK_THEMES else "seaborn"


def apply_plotly_template(figure_spec: dict, config: dict) -> dict:
    """
    Applies Plotly template/theme settings to a figure spec.

    Supports:
      config["template"]
      config["theme"]
      config["template"] = {"?source": "..."}
      config["theme"] = {"?source": "..."}

    Also defaults paper/plot backgrounds to transparent unless explicitly set.
    """

    patched = deepcopy(figure_spec or {})
    layout = patched.setdefault("layout", {})

    template = config.get("template", None)

    if template is None:
        template = config.get("theme", None)

    template = _resolve_theme_value(template)

    # Deployment-wide default when a figure does not specify a template: follows
    # the app theme (plotly_dark on dark themes, seaborn on light), overridable
    # via STRATABI_PLOTLY_TEMPLATE. Applies to both the plotly and
    # plotly_resampler blocks (both call this helper).
    if not template:
        template = _default_plotly_template()

    if template:
        layout["template"] = template

    # Default to transparent backgrounds because StrataBI renders charts inside cards.
    # Explicit layout values win.
    layout.setdefault("paper_bgcolor", "rgba(0,0,0,0)")
    layout.setdefault("plot_bgcolor", "rgba(0,0,0,0)")

    return patched