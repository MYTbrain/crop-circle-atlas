"""Optional AnyLoc adapter boundary; weights remain external and opt-in."""

from __future__ import annotations


class AnyLocAdapter:
    name = "anyloc"

    def __init__(self, model_cache):
        self.model_cache = model_cache

    def rank(self, *args, **kwargs):
        raise RuntimeError("AnyLoc is an optional reviewed-license adapter; install and configure external weights before use")

