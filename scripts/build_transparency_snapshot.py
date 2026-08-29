#!/usr/bin/env python3
"""Build the committed privacy-safe cross-surface coverage snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from callersignal.fcc_catalog import (  # noqa: E402
    FCCCatalogReadError,
    read_fcc_catalog_metadata,
)
from callersignal.transparency import build_transparency_snapshot  # noqa: E402


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument(
        "--generated-at",
        help="timezone-aware ISO timestamp; defaults to the current UTC time",
    )
    command.add_argument(
        "--output",
        type=Path,
        default=ROOT / "web/assets/transparency.json",
    )
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    generated_at = (
        datetime.fromisoformat(args.generated_at.replace("Z", "+00:00"))
        if args.generated_at
        else datetime.now(UTC)
    )
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise SystemExit("--generated-at must include a timezone")
    registry = _load(ROOT / "sources/registry.json")
    acm_manifest = _load(ROOT / "sources/acm-bulk-manifest.json")
    service_index = _load(ROOT / "sources/caller-report-services.json")
    fcc_catalog = _fcc_catalog_metadata()
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
    ingest_status["fcc_unwanted_call_complaints"] = {
        "status": "success",
        "last_successful_ingest": fcc_catalog["generated_at"],
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
        fcc_catalog=fcc_catalog,
    )
    args.output.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output.resolve())
    return 0


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fcc_catalog_metadata() -> dict:
    configured_key = os.environ.get("CALLERSIGNAL_REPUTATION_INDEX_KEY")
    if not configured_key:
        return _load(ROOT / "sources/fcc-catalog-release.json")
    configured_path = os.environ.get("CALLERSIGNAL_FCC_CATALOG_PATH")
    catalog_path = (
        Path(configured_path)
        if configured_path
        else ROOT / "downloads/fcc-unwanted-calls.sqlite3"
    )
    try:
        metadata = read_fcc_catalog_metadata(
            catalog_path,
            lookup_key=configured_key.encode("utf-8"),
        )
    except FCCCatalogReadError as error:
        raise SystemExit(f"Cannot authenticate generated FCC coverage: {error}") from error
    return {
        "schema_version": "1.0.0",
        "kind": "fcc_unwanted_call_catalog_release",
        "source_id": "fcc_unwanted_call_complaints",
        "dataset_id": "vakf-fz8e",
        **asdict(metadata),
    }


if __name__ == "__main__":
    raise SystemExit(main())
