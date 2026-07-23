"""Command-line entry point for the local exact-field-resolution worker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .adapters import provider_from_spec, read_json
from .benchmark.runner import describe_manifest
from .benchmark.synthetic import run_synthetic_benchmark
from .config import Settings
from .models import Citation, Clue
from .service import FieldResolutionService


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _service() -> FieldResolutionService:
    return FieldResolutionService(Settings.from_env())


def _clues(values: list[dict[str, Any]]) -> list[Clue]:
    return [
        Clue(
            kind=item["kind"], value=item["value"], confidence=float(item["confidence"]),
            citations=tuple(Citation(**citation) for citation in item.get("citations", [])),
            qualifiers=dict(item.get("qualifiers", {})),
        )
        for item in values
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crop-circle-geo")
    commands = parser.add_subparsers(dest="command", required=True)

    context = commands.add_parser("context"); context.add_argument("formation_id")
    create = commands.add_parser("create-job"); create.add_argument("formation_id")
    clues = commands.add_parser("set-clues"); clues.add_argument("job_id"); clues.add_argument("--clues", required=True)
    area = commands.add_parser("set-search-area"); area.add_argument("job_id"); area.add_argument("--geometry", required=True); area.add_argument("--exclusions", default="[]"); area.add_argument("--query", default="")
    imagery = commands.add_parser("search-imagery"); imagery.add_argument("job_id"); imagery.add_argument("--provider", required=True); imagery.add_argument("--options", default="{}"); imagery.add_argument("--collections", default="[]"); imagery.add_argument("--date-start"); imagery.add_argument("--date-end"); imagery.add_argument("--limit", type=int)
    tiles = commands.add_parser("generate-tiles"); tiles.add_argument("job_id"); tiles.add_argument("--imagery-item", required=True); tiles.add_argument("--tile-size-m", type=float, default=512); tiles.add_argument("--overlap", type=float, default=.25); tiles.add_argument("--scales", default="[1.0]"); tiles.add_argument("--rotations", default="[0.0]")
    rank = commands.add_parser("rank"); rank.add_argument("job_id"); rank.add_argument("--source-image", required=True); rank.add_argument("--tile-manifest", required=True); rank.add_argument("--top-k", type=int, default=20); rank.add_argument("--mask")
    match = commands.add_parser("match"); match.add_argument("job_id"); match.add_argument("--source-image", required=True); match.add_argument("--tile", required=True); match.add_argument("--retrieval-score", type=float, default=0)
    validate = commands.add_parser("validate"); validate.add_argument("job_id"); validate.add_argument("--registration-id", required=True); validate.add_argument("--controls", required=True); validate.add_argument("--checkpoints", required=True); validate.add_argument("--reviewer", required=True); validate.add_argument("--uncertainty-components")
    review = commands.add_parser("review"); review.add_argument("job_id"); review.add_argument("--review", required=True); review.add_argument("--checkpoint-validation")
    measure = commands.add_parser("measure-component"); measure.add_argument("job_id"); measure.add_argument("--registration", required=True); measure.add_argument("--tile", required=True); measure.add_argument("--endpoint-a", required=True); measure.add_argument("--endpoint-b", required=True); measure.add_argument("--uncertainty-m", type=float, required=True); measure.add_argument("--directionality", default="bidirectional")
    overlay = commands.add_parser("generate-overlay"); overlay.add_argument("job_id"); overlay.add_argument("--review", required=True); overlay.add_argument("--registration", required=True); overlay.add_argument("--tile", required=True); overlay.add_argument("--source-image", required=True); overlay.add_argument("--public-export", action="store_true")
    promote = commands.add_parser("promote-reviewed-resolution"); promote.add_argument("job_id"); promote.add_argument("--review", required=True); promote.add_argument("--longitude", type=float, required=True); promote.add_argument("--latitude", type=float, required=True); promote.add_argument("--coordinate-method", required=True); promote.add_argument("--confirm", action="store_true")
    status = commands.add_parser("status"); status.add_argument("job_id")
    benchmark = commands.add_parser("benchmark"); benchmark.add_argument("--manifest", required=True); benchmark.add_argument("--synthetic", action="store_true"); benchmark.add_argument("--output")
    serve = commands.add_parser("serve-api"); serve.add_argument("--host"); serve.add_argument("--port", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "benchmark":
        result = {"real_world_manifest": describe_manifest(Path(args.manifest))}
        if args.synthetic:
            result["synthetic_result"] = run_synthetic_benchmark()
        if args.output:
            Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _emit(result); return 0
    if args.command == "serve-api":
        from .api import run
        settings = Settings.from_env(); run(args.host or settings.api_host, args.port or settings.api_port); return 0
    service = _service()
    if args.command == "context": result = service.get_formation_context(args.formation_id)
    elif args.command == "create-job": result = service.create_job(args.formation_id).to_dict()
    elif args.command == "set-clues": result = service.set_clues(args.job_id, _clues(read_json(args.clues))).to_dict()
    elif args.command == "set-search-area": result = service.set_search_area(args.job_id, read_json(args.geometry), read_json(args.exclusions), query=args.query).to_dict()
    elif args.command == "search-imagery": result = service.search_imagery(args.job_id, provider_from_spec(args.provider, read_json(args.options)), read_json(args.collections), args.date_start, args.date_end, args.limit)
    elif args.command == "generate-tiles": result = service.generate_tiles(args.job_id, read_json(args.imagery_item), args.tile_size_m, args.overlap, read_json(args.scales), read_json(args.rotations))
    elif args.command == "rank": result = service.rank_tiles(args.job_id, Path(args.source_image), read_json(args.tile_manifest), args.top_k, Path(args.mask) if args.mask else None)
    elif args.command == "match": result = service.match_candidate(args.job_id, Path(args.source_image), read_json(args.tile), args.retrieval_score)
    elif args.command == "validate": result = service.validate_registration(args.job_id, args.registration_id, read_json(args.controls), read_json(args.checkpoints), args.reviewer, read_json(args.uncertainty_components) if args.uncertainty_components else None)
    elif args.command == "review": result = service.save_review(args.job_id, read_json(args.review), read_json(args.checkpoint_validation) if args.checkpoint_validation else None)
    elif args.command == "measure-component": result = service.measure_component(args.job_id, read_json(args.registration), read_json(args.tile), read_json(args.endpoint_a), read_json(args.endpoint_b), args.uncertainty_m, args.directionality)
    elif args.command == "generate-overlay": result = service.generate_local_overlay(args.job_id, read_json(args.review), read_json(args.registration), read_json(args.tile), Path(args.source_image), args.public_export)
    elif args.command == "promote-reviewed-resolution": result = service.promote_reviewed_resolution(args.job_id, read_json(args.review), args.longitude, args.latitude, args.coordinate_method, args.confirm)
    elif args.command == "status": result = service.get_job_status(args.job_id)
    else: raise AssertionError(args.command)
    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
