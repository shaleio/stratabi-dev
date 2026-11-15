"""Theme-aware Plotly colors (config.theme_colors)."""
import os
import sys

sys.path[:0] = [os.path.dirname(__file__), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
import _stubs  # noqa: E402

_stubs.install()
from stratabi.core import plotly_utils, theme_colors as tc  # noqa: E402


def test_every_bundled_theme_has_a_palette():
    import pathlib
    root = pathlib.Path(tc.__file__).resolve().parents[1] / "themes"
    names = {p.name.split(".")[0] for p in root.glob("*.css")}
    missing = [n for n in names if not tc.palette(n)]
    assert not missing, missing


def test_colors_follow_the_active_theme_and_explicit_values_win():
    os.environ["STRATABI_THEME"] = "guildmaster"
    fig = plotly_utils.apply_plotly_template(
        {"data": [], "layout": {"title": "Pressure", "xaxis": {"gridcolor": "red"}}}, {"theme_colors": True})
    lay = fig["layout"]
    assert lay["colorway"][0] == "#34b6c4"                    # theme primary first
    assert lay["font"]["color"] == "#e6eef5"
    assert lay["xaxis"]["gridcolor"] == "red"                 # explicit wins
    assert lay["yaxis"]["gridcolor"].startswith("rgba(")
    assert lay["title"] == "Pressure"                         # string title untouched
    os.environ["STRATABI_THEME"] = "guildmaster_light"
    lay2 = plotly_utils.apply_plotly_template({"data": []}, {"theme_colors": True})["layout"]
    assert lay2["colorway"] and lay2["font"]["color"] != lay["font"]["color"]


def test_off_by_default_and_deployment_switch():
    os.environ.pop("STRATABI_PLOTLY_THEME_COLORS", None)
    assert "colorway" not in plotly_utils.apply_plotly_template({"data": []}, {})["layout"]
    os.environ["STRATABI_PLOTLY_THEME_COLORS"] = "1"
    try:
        assert "colorway" in plotly_utils.apply_plotly_template({"data": []}, {})["layout"]
        assert "colorway" not in plotly_utils.apply_plotly_template({"data": []}, {"theme_colors": False})["layout"]
    finally:
        os.environ.pop("STRATABI_PLOTLY_THEME_COLORS")


def test_unknown_theme_falls_back_quietly():
    os.environ["STRATABI_THEME"] = "my-custom-theme"
    lay = plotly_utils.apply_plotly_template({"data": []}, {"theme_colors": True})["layout"]
    assert "colorway" not in lay
    os.environ["STRATABI_THEME"] = "guildmaster"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
