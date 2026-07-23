"""Deterministic CPU descriptor emphasizing persistent scene structure."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..provenance import canonical_json, sha256_bytes, sha256_file
from .base import Retriever


class CpuBaselineRetriever(Retriever):
    name = "cpu_edge_gradient_descriptor"
    version = "1.0.0"

    def __init__(self, cache_root: Path | None = None):
        self.cache_root = cache_root.resolve() if cache_root else None

    @staticmethod
    def _read(path: Path) -> np.ndarray:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"unable to read image: {path}")
        return image

    @classmethod
    def descriptor(cls, path: Path, mask: Path | None = None) -> np.ndarray:
        gray = cls._read(path)
        gray = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        weights = np.ones_like(gray, dtype=np.float32)
        if mask:
            mask_image = cls._read(mask)
            mask_image = cv2.resize(mask_image, (256, 256), interpolation=cv2.INTER_NEAREST)
            weights[mask_image > 127] = 0.1
        edges = cv2.Canny(gray, 50, 130, L2gradient=True).astype(np.float32) / 255
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        magnitude, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
        magnitude *= weights
        cells: list[np.ndarray] = []
        for row in range(4):
            for col in range(4):
                y0, y1 = row * 64, (row + 1) * 64
                x0, x1 = col * 64, (col + 1) * 64
                histogram, _ = np.histogram(
                    angle[y0:y1, x0:x1], bins=12, range=(0, 360), weights=magnitude[y0:y1, x0:x1],
                )
                edge_density = np.array([np.mean(edges[y0:y1, x0:x1] * weights[y0:y1, x0:x1])])
                intensity = cv2.resize(gray[y0:y1, x0:x1], (4, 4), interpolation=cv2.INTER_AREA).astype(np.float32).ravel() / 255
                cells.append(np.concatenate([histogram.astype(np.float32), edge_density, intensity]))
        descriptor = np.concatenate(cells)
        norm = np.linalg.norm(descriptor)
        return descriptor / norm if norm else descriptor

    def _cached_descriptor(self, path: Path, mask: Path | None = None) -> tuple[np.ndarray, bool]:
        if not self.cache_root:
            return self.descriptor(path, mask), False
        identity = {
            "image_sha256": sha256_file(path), "mask_sha256": sha256_file(mask) if mask else None,
            "model": self.name, "version": self.version,
        }
        key = sha256_bytes(canonical_json(identity))
        destination = self.cache_root / "embeddings" / f"{key}.npy"
        if destination.exists():
            return np.load(destination), True
        destination.parent.mkdir(parents=True, exist_ok=True)
        value = self.descriptor(path, mask)
        np.save(destination, value)
        return value, False

    def rank(self, source_image, tiles, top_k, mask=None):
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        source_descriptor, source_hit = self._cached_descriptor(Path(source_image), Path(mask) if mask else None)
        ranked = []
        for tile in tiles:
            descriptor, cache_hit = self._cached_descriptor(Path(tile["local_path"]))
            score = float(np.clip(np.dot(source_descriptor, descriptor), -1, 1))
            ranked.append({
                "candidate_tile_id": tile["candidate_tile_id"], "score": round(score, 8),
                "retriever": {"name": self.name, "version": self.version},
                "tile": tile, "embedding_cache_hit": cache_hit,
            })
        ranked.sort(key=lambda item: (-item["score"], item["candidate_tile_id"]))
        bounded = ranked[: min(top_k, len(ranked))]
        for rank, record in enumerate(bounded, start=1):
            record["rank"] = rank
            record["source_embedding_cache_hit"] = source_hit
        return bounded

