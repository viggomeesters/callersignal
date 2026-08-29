#!/usr/bin/env python3
"""Build the checksum-pinned, privacy-minimized ACM SQLite catalogue."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from callersignal.acm_catalog import CatalogBuildError, build_acm_catalog  # noqa: E402


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "sources/acm-bulk-manifest.json",
        help="checksum-pinned source manifest",
    )
    command.add_argument(
        "--output",
        type=Path,
        default=ROOT / "downloads/acm-number-register.sqlite3",
        help="generated SQLite catalogue path",
    )
    command.add_argument(
        "--archive",
        type=Path,
        help="use an already downloaded archive; checksum validation still applies",
    )
    command.add_argument("--json", action="store_true", help="emit a JSON summary")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        summary = build_acm_catalog(
            args.manifest,
            args.output,
            archive_path=args.archive,
        )
    except CatalogBuildError as error:
        print(f"ACM catalogue build refused: {error}", file=sys.stderr)
        return 2

    payload = {
        "destination_counts": summary.destination_counts,
        "matchable_row_count": summary.matchable_row_count,
        "newest_mutation": summary.newest_mutation,
        "output_path": str(summary.output_path),
        "row_count": summary.row_count,
        "source_sha256": summary.source_sha256,
        "status_counts": summary.status_counts,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(
            f"built {payload['row_count']} ACM rows "
            f"({payload['matchable_row_count']} lookup ranges) at {payload['output_path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
