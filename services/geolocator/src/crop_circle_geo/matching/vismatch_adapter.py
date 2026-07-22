"""Optional VisMatch boundary pending wrapper and selected-weight license review."""

from __future__ import annotations


class VisMatchAdapter:
    name = "vismatch"

    def match(self, *args, **kwargs):
        raise RuntimeError("VisMatch is disabled until both wrapper and selected model-weight licenses are recorded")

