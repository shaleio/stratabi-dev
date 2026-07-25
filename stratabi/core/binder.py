# stratabi/binder.py

import pandas as pd


class BindError(Exception):
    pass


def bind_dataframe(obj, df: pd.DataFrame):
    """
    Recursively bind @column references in a Plotly figure spec
    to values from a pandas DataFrame.

    Returns a JSON-serializable structure.
    """

    if isinstance(obj, str):
        if obj.startswith("@"):
            col = obj[1:]
            if col not in df.columns:
                raise BindError(f"Column '{col}' not found in DataFrame")

            series = df[col]

            # Convert to JSON-safe values
            if pd.api.types.is_datetime64_any_dtype(series):
                return series.dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()

            return series.tolist()

        return obj

    elif isinstance(obj, dict):
        return {
            key: bind_dataframe(value, df)
            for key, value in obj.items()
        }

    elif isinstance(obj, list):
        return [
            bind_dataframe(item, df)
            for item in obj
        ]

    elif isinstance(obj, tuple):
        return tuple(
            bind_dataframe(item, df)
            for item in obj
        )

    else:
        # ints, floats, bools, None, etc.
        return obj
