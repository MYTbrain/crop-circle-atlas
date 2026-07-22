"""Optional Planetary Computer STAC adapter with official asset signing."""

from __future__ import annotations

from typing import Any, Callable

from .stac import StacProvider


class PlanetaryComputerProvider(StacProvider):
    name = "planetary_computer"

    def __init__(
        self,
        endpoint: str = "https://planetarycomputer.microsoft.com/api/stac/v1",
        asset_key: str = "image",
        client_factory: Callable[[str], Any] | None = None,
        signer: Callable[[Any], Any] | None = None,
    ):
        if signer is None:
            try:
                import planetary_computer
            except ImportError as exc:
                if client_factory is None:
                    raise RuntimeError("install the stac extra to use Planetary Computer") from exc
                signer = lambda asset: asset
            else:
                signer = planetary_computer.sign
        super().__init__(endpoint, asset_key, client_factory=client_factory, asset_transform=signer)

    def search(self, *args, **kwargs):
        results = super().search(*args, **kwargs)
        for result in results:
            result["provider"] = self.name
        return results

