# stratabi/registry.py

from stratabi.blocks.plotly import PlotlyBlock
from stratabi.blocks.plotly_resampler import PlotlyResamplerBlock
from stratabi.blocks.markdown import MarkdownBlock
from stratabi.blocks.image import ImageBlock
from stratabi.blocks.raw_html import RawHTMLBlock
from stratabi.blocks.input_range import InputRangeBlock
from stratabi.blocks.input_select import InputSelectBlock
from stratabi.blocks.table import TableBlock

BLOCK_REGISTRY = {
    "plotly": PlotlyBlock,
    "plotly_resampler": PlotlyResamplerBlock,
    "markdown": MarkdownBlock,
    "image": ImageBlock,
    "raw_html": RawHTMLBlock,
    "input_range": InputRangeBlock,
    "input_select": InputSelectBlock,
    "table": TableBlock
}