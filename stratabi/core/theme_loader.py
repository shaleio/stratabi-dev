from pathlib import Path
import json
import os
from .config import config

# Lazy boto3 import
def get_s3_client():
    import boto3
    return boto3.client("s3")


def _load_themes_from_s3():
    """
    AWS mode:
    Loads themes.json from:
        s3://bucket/<theme_prefix>/themes.json
    """
    s3 = get_s3_client()
    key = f"{config.THEME_PREFIX}/themes.json"

    obj = s3.get_object(Bucket=config.BUCKET, Key=key)
    data = json.loads(obj["Body"].read())

    return {k: v for k, v in data.items() if not k.startswith("//")}


# ============================================================
# PUBLIC ACCESS
# ============================================================

def load_theme_registry():
    if config.MODE == "aws":
        return _load_themes_from_s3()
    return


def get_theme(name):
    """
    Returns the theme as proper external_stylesheet value:
    - Local mode: /themes/<filename>.css
    - AWS mode: full S3 https URL
    """
    if config.MODE == "local":
        return
    
    THEME_REGISTRY = load_theme_registry()
    if name not in THEME_REGISTRY:
        raise KeyError(
            f"Theme '{name}' not found. "
            f"Available: {list(THEME_REGISTRY.keys())}"
        )

    path = THEME_REGISTRY[name]

    # AWS mode → return the S3 URL as stored in json
    # ex: "https://BUCKET.s3.amazonaws.com/analyst/themes/guildmaster.css"
    return path
