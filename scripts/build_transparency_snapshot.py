#!/usr/bin/env python3
"""Build the committed privacy-safe cross-surface coverage snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from callersignal.transparency import build_transparency_snapshot  # noqa: E402


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument(
        "--generated-at",
        required=True,
        help="timezone-aware ISO timestamp recorded in the public snapshot",
    )
    command.add_argument(
        "--output",
        type=Path,
        default=ROOT / "web/assets/transparency.json",
    )
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    generated_at = datetime.fromisoformat(args.generated_at.replace("Z", "+00:00"))
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise SystemExit("--generated-at must include a timezone")
    registry = _load(ROOT / "sources/registry.json")
    acm_manifest = _load(ROOT / "sources/acm-bulk-manifest.json")
    service_index = _load(ROOT / "sources/caller-report-services.json")
    ingest_status = {}
    for fixture_path in sorted((ROOT / "fixtures").glob("*/*.json")):
        fixture = _load(fixture_path)
        ingest_status[fixture["source"]["source_id"]] = {
            "status": "success",
            "last_successful_ingest": fixture["source"]["retrieved_at"],
        }
    ingest_status["acm_number_register"] = {
        "status": "success",
        "last_successful_ingest": acm_manifest["artifact"]["retrieved_at"],
    }
    snapshot = build_transparency_snapshot(
        source_registry=registry,
        ingest_status=ingest_status,
        campaigns=[],
        verified_portfolios=[],
        community_aggregates=[],
        moderation={
            "status": "not_approved",
            "public_aggregate_minimum": None,
            "independent_observer_minimum": 2,
        },
        methodology_version="1.0.0",
        generated_at=generated_at,
        acm_manifest=acm_manifest,
        caller_report_index=service_index,
    )
    args.output.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output.resolve())
    return 0


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
