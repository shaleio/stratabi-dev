import os

def _get_env(name, default=None):
    val = os.getenv(name, default)
    return val if val not in ("None", "") else default

class Config:
    MODE = _get_env("STRATABI_MODE", "local")

    BUCKET = _get_env("STRATABI_BUCKET")
    DASHBOARD_PREFIX = _get_env("STRATABI_DASHBOARD_PREFIX", "analyst/dashboards")
    THEME_PREFIX = _get_env("STRATABI_THEME_PREFIX", "analyst/themes")

    # WORKGROUPS: safe parse list
    _wg_raw = _get_env("STRATABI_WORKGROUPS", "")
    WORKGROUPS = [w for w in _wg_raw.split(",") if w]

    BLOCK_RESULT_DEFAULTS = {
    "plotly": {
        "result_kind": "dataframe",
        "result_format": "parquet",
        "result_name": "result.parquet",
    },
    "plotly_resampler": {
        "result_kind": "dataframe",
        "result_format": "parquet",
        "result_name": "result.parquet",
    },
    "table": {
        "result_kind": "dataframe",
        "result_format": "parquet",
        "result_name": "result.parquet",
    },
    "markdown": {
        "result_kind": "artifact",
        "result_format": "md",
        "result_name": "result.md",
    },
    "raw_html": {
        "result_kind": "artifact",
        "result_format": "html",
        "result_name": "result.html",
    },
    "image": {
        "result_kind": "artifact",
        "result_format": "png",
        "result_name": "result.png",
    },
    "dropdown": {
        "result_kind": "json",
        "result_format": "json",
        "result_name": "result.json",
    },
    "input_select": {
        "result_kind": "json",
        "result_format": "json",
        "result_name": "result.json",
    },
    "input_range": {
        "result_kind": "json",
        "result_format": "json",
        "result_name": "result.json",
    },
    "button": {
        "result_kind": "json",
        "result_format": "json",
        "result_name": "result.json",
    },
}

config = Config()
