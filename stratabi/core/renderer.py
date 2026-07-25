# stratabi/core/renderer.py

from dash import html
from stratabi.core.registry import BLOCK_REGISTRY


def render_block(block_spec, result=None, tile_id=None):
    config = block_spec.get("config", {})
    block_type = block_spec.get("type")

    if not block_type:
        return html.Div("Block is missing type.", className="text-danger")

    block_cls = BLOCK_REGISTRY.get(block_type)

    if not block_cls:
        return html.Div(
            f"Unknown block type: {block_type}",
            className="text-danger",
        )

    block = block_cls(
        config=config,
        result=result,
        tile_id=tile_id,
    )

    return block.render()