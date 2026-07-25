"""Markdown block — renders static Markdown content or a runtime markdown artifact."""
from dash import dcc, html
from stratabi.core.base import Block
from stratabi.core.text_utils import coerce_lines


class MarkdownBlock(Block):
    block_type = "markdown"

    def render(self):
        content = coerce_lines(self.config.get("content", ""))

        if isinstance(self.result, str):
            content = self.result
        elif isinstance(self.result, dict):
            content = (
                self.result.get("content")
                or self.result.get("markdown")
                or self.result.get("text")
                or content
            )

        if not content:
            raise ValueError("Markdown block has no content.")

        return dcc.Markdown(content)