"""Block base class — the contract every StrataBI block implements: it receives a config and an optional runtime `result`, and returns a Dash component from `render()`."""
# stratabi//base.core/base.py

from abc import ABC, abstractmethod

class Block(ABC):
    block_type: str

    def __init__(self, config=None, result=None, tile_id=None):
        self.config = config or {}
        self.result = result
        self.tile_id = tile_id

    @abstractmethod
    def render(self):
        """Return a Dash component"""
        pass
