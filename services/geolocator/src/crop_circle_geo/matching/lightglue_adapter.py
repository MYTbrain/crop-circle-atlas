"""Optional LightGlue boundary with no bundled code or weights."""

from __future__ import annotations


class LightGlueAdapter:
    name = "lightglue"

    def match(self, *args, **kwargs):
        raise RuntimeError("LightGlue is optional; configure Apache-2.0-compatible features and externally cached weights")

