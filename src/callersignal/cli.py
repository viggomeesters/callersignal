"""Read-only CallerSignal command-line interface."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from typing import Any

from callersignal.lookup import LookupService
from callersignal.numbering import OriginRegionRequiredError
from callersignal.transparency import load_public_coverage_snapshot

_COUNTRY_NAMES = {"NL": "Netherlands", "GB": "United Kingdom", "US": "United States"}
_CALLING_CODE_COUNTRY = {"31": "NL", "44": "GB", "1": "US"}


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI grammar."""
    parser = argparse.ArgumentParser(
        prog="callersignal",
        description="Evidence-backed international phone-number lookup.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    lookup = commands.add_parser("lookup", help="Check public numbering evidence.")
    lookup.add_argument("number", help="National or +prefixed international number.")
    lookup.add_argument(
        "--region",
        help="ISO alpha-2 origin region required for national input, for example NL.",
    )
    lookup.add_argument(
        "--json",
        action="store_true",
        help="Emit the versioned lookup-result JSON contract.",
    )
    coverage = commands.add_parser(
        "coverage",
        help="Show official catalogue and reputation-source coverage.",
    )
    coverage.add_argument(
        "--json",
        action="store_true",
        help="Emit the shared public corpus-transparency JSON contract.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    lookup_service: LookupService | None = None,
    source_coverage: Mapping[str, Any] | None = None,
) -> int:
    """Execute one CLI command and return its process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "coverage":
        snapshot = (
            dict(source_coverage)
            if source_coverage is not None
            else load_public_coverage_snapshot()
        )
        if args.json:
            print(json.dumps(snapshot, sort_keys=True, ensure_ascii=False))
        else:
            print(_human_coverage(snapshot))
        return 0
    service = lookup_service or LookupService()
    try:
        result = service.lookup(args.number, origin_region=args.region)
    except OriginRegionRequiredError:
        parser.error("National phone-number input requires an origin region via --region.")
    if args.json:
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    else:
        print(_human_result(result))
    return 0


def _human_result(result: dict[str, Any]) -> str:
    phone = result["phone_number"]
    canonical = phone["canonical"]
    country = canonical.get("region") or _CALLING_CODE_COUNTRY.get(
        canonical.get("country_calling_code")
    )
    country_name = _COUNTRY_NAMES.get(country, "Unsupported jurisdiction")
    presentation = phone["presentation"]
    assessment = result["assessment"]
    confidence = assessment["confidence"]
    lines = [
        f"Checking from {country_name} ({country or 'unknown'})",
        f"Input: {phone['raw_input']}",
        f"Local: {presentation['national'] or 'unavailable'}",
        f"International: {presentation['international'] or 'unavailable'}",
        "",
        f"Assessment: {assessment['state'].replace('_', ' ')}",
        f"Confidence: {confidence['level']} ({confidence['score']:.2f})",
        "Evidence:",
    ]
    if result["evidence"]:
        for item in result["evidence"]:
            observation = item["observation"]
            value = observation["value"]
            display_value = (
                ", ".join(str(part) for part in value)
                if isinstance(value, list)
                else value
            )
            lines.append(
                f"- {item['source']['name']}: {observation['claim_type']} = {display_value}"
            )
    else:
        lines.append("- No current public source evidence.")
    if result["gaps"]:
        lines.append("Unknowns:")
        lines.extend(f"- {item['code']}: {item['message']}" for item in result["gaps"])
    else:
        lines.append("Unknowns: none reported by the checked source")
    lines.extend(("", assessment["residual_risk"]))
    return "\n".join(lines)


def _human_coverage(snapshot: Mapping[str, Any]) -> str:
    coverage = snapshot["coverage"]
    catalog = coverage["number_catalog"]
    reputation = coverage["reputation_sources"]
    status_counts = ", ".join(
        f"{item['status'].replace('_', ' ')} {item['range_count']:,}"
        for item in catalog["register_statuses"]
    )
    reasons = ", ".join(
        f"{item['reason'].replace('_', ' ')} ({item['service_count']})"
        for item in reputation["unavailable_reasons"]
    )
    return "\n".join(
        (
            f"Official NL number catalogue: {catalog['status']}",
            f"- {catalog['imported_range_count']:,} imported ranges",
            f"- {catalog['matchable_range_count']:,} lookup-compatible ranges",
            f"- {catalog['destination_category_count']:,} destination categories",
            f"- Register status coverage: {status_counts}",
            f"- Freshness: {catalog['freshness']} as of {catalog['retrieved_at']}",
            "",
            "Caller-reputation coverage: unavailable",
            f"- {reputation['indexed_service_count']:,} caller-report services indexed",
            f"- {reputation['licensable_service_count']:,} advertised licensing routes",
            f"- {reputation['enabled_source_count']:,} reputation feeds enabled",
            f"- Unavailable reasons: {reasons}",
            "",
            "Coverage counts are not trust or safety scores.",
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
