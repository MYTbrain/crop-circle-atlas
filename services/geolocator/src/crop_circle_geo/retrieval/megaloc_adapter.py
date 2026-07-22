"""Optional MegaLoc adapter boundary; no repository code or weights are vendored."""

from __future__ import annotations


class MegaLocAdapter:
    name = "megaloc"

    def __init__(self, model_cache):
        self.model_cache = model_cache

    def rank(self, *args, **kwargs):
        raise RuntimeError("MegaLoc is optional; configure its MIT-licensed code and separately reviewed weights in an external cache")
