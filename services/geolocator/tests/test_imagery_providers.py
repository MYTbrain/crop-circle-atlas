from __future__ import annotations

from dataclasses import dataclass

import pytest

from crop_circle_geo.imagery.planetary_computer import PlanetaryComputerProvider
from crop_circle_geo.imagery.stac import StacProvider
from crop_circle_geo.imagery.usgs_m2m import UsgsM2MProvider


@dataclass
class FakeAsset:
    href: str
    media_type: str = "image/tiff"


class FakeItem:
    id = "scene-1"
    collection_id = "naip"
    geometry = {"type": "Polygon", "coordinates": [[[-1, 0], [1, 0], [1, 1], [-1, 1], [-1, 0]]]}
    bbox = [-1, 0, 1, 1]
    properties = {"datetime": "2004-07-01T00:00:00Z", "proj:code": "EPSG:32610", "gsd": 1, "license": "public-domain-item-review-pending"}
    assets = {"image": FakeAsset("https://example.test/scene.tif")}

    def to_dict(self):
        return {"id": self.id, "collection": self.collection_id, "properties": self.properties, "geometry": self.geometry}


class FakeSearch:
    def items(self):
        return iter([FakeItem()])


class FakeClient:
    def search(self, **kwargs):
        self.kwargs = kwargs
        return FakeSearch()


def test_mocked_stac_search_normalizes_item():
    client = FakeClient()
    provider = StacProvider("https://example.test/stac", client_factory=lambda _: client)
    results = provider.search(FakeItem.geometry, "2004-01-01", "2004-12-31", ["naip"], 5)
    assert results[0]["item_id"] == "scene-1"
    assert results[0]["asset"]["href"] == "https://example.test/scene.tif"
    assert results[0]["rights"]["public_derivative_export_allowed"] is False
    assert client.kwargs["max_items"] == 5


def test_mocked_planetary_computer_signs_assets():
    client = FakeClient()
    provider = PlanetaryComputerProvider(
        client_factory=lambda _: client,
        signer=lambda asset: FakeAsset(asset.href + "?signed=yes", asset.media_type),
    )
    result = provider.search(FakeItem.geometry, None, None, ["naip"], 1)[0]
    assert result["provider"] == "planetary_computer"
    assert result["asset"]["href"].endswith("signed=yes")


class FakeM2MTransport:
    def __init__(self):
        self.calls = []

    def post(self, path, payload, api_key=None):
        self.calls.append((path, payload, api_key))
        if path == "scene-search":
            return {"data": {"results": [{
                "entityId": "USGS-1", "acquisitionDate": "1998-07-28",
                "spatialCoverage": FakeItem.geometry, "boundingBox": FakeItem.bbox,
                "spatialReference": "EPSG:32610", "spatialResolution": 1, "orthorectified": True,
            }]}}
        if path == "download-options":
            return {"data": {"availableDownloads": [{"entityId": "USGS-1", "productId": "p1"}]}}
        raise AssertionError(path)


def test_mocked_usgs_m2m_scene_and_download_flow():
    transport = FakeM2MTransport()
    provider = UsgsM2MProvider(transport, "doq", token="test-token")
    result = provider.search(FakeItem.geometry, "1998-01-01", "1998-12-31", limit=2)[0]
    assert result["item_id"] == "USGS-1"
    assert result["orthorectified"] is True
    downloads = provider.request_download(["USGS-1"])
    assert downloads["availableDownloads"][0]["productId"] == "p1"
    assert all(call[2] == "test-token" for call in transport.calls)

