#!/usr/bin/env python3
"""Build the public-domain, privacy-minimized FCC complaint aggregate."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from callersignal.fcc_catalog import FCCCatalogBuildError, build_fcc_catalog  # noqa: E402

LOOKUP_KEY_ENV = "CALLERSIGNAL_REPUTATION_INDEX_KEY"


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "sources/fcc-complaints-manifest.json",
        help="reviewed FCC source and query manifest",
    )
    command.add_argument(
        "--output",
        type=Path,
        default=ROOT / "downloads/fcc-unwanted-calls.sqlite3",
        help="generated HMAC-keyed SQLite catalogue path",
    )
    command.add_argument(
        "--generated-at",
        help="optional timezone-aware ISO build time for reproducible verification",
    )
    command.add_argument("--json", action="store_true", help="emit a JSON summary")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    key_value = os.environ.get(LOOKUP_KEY_ENV)
    if key_value is None:
        print(
            f"FCC catalogue build refused: {LOOKUP_KEY_ENV} is required",
            file=sys.stderr,
        )
        return 2
    generated_at = None
    if args.generated_at:
        try:
            generated_at = datetime.fromisoformat(args.generated_at.replace("Z", "+00:00"))
        except ValueError:
            print(
                "FCC catalogue build refused: --generated-at is not valid ISO time",
                file=sys.stderr,
            )
            return 2
    try:
        summary = build_fcc_catalog(
            args.manifest,
            args.output,
            lookup_key=key_value.encode("utf-8"),
            generated_at=generated_at,
        )
    except FCCCatalogBuildError as error:
        print(f"FCC catalogue build refused: {error}", file=sys.stderr)
        return 2

    payload = {
        "category_counts": summary.category_counts,
        "first_issue_date": summary.first_issue_date,
        "generated_at": summary.generated_at,
        "grouped_row_count": summary.grouped_row_count,
        "indexed_observation_count": summary.indexed_observation_count,
        "last_issue_date": summary.last_issue_date,
        "output_path": str(summary.output_path),
        "page_count": summary.page_count,
        "rejected_number_row_count": summary.rejected_number_row_count,
        "rejected_observation_count": summary.rejected_observation_count,
        "source_digest": summary.source_digest,
        "source_observation_count": summary.source_observation_count,
        "source_updated_at": summary.source_updated_at,
        "unique_number_count": summary.unique_number_count,
        "window_end": summary.window_end,
        "window_start": summary.window_start,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    else:
        print(
            f"built {summary.unique_number_count} keyed FCC number aggregates "
            f"from {summary.indexed_observation_count} observations at "
            f"{summary.output_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
