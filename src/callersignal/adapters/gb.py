"""United Kingdom adapter for Ofcom long-term protected number ranges."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from callersignal.adapters.base import (
    AdapterResult,
    AdapterStatus,
    EvidenceGap,
    SourceDeclaration,
)

_DEFAULT_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures/gb/ofcom_protected_numbers.json"
_LIMITATIONS = (
    "Protected range status describes allocation policy, not assignment to a provider "
    "or subscriber.",
    "A protected number does not identify the caller and caller ID can be spoofed.",
)


class UnitedKingdomProtectedNumbersAdapter:
    """Resolve public Ofcom protection facts without inferring caller identity."""

    declaration = SourceDeclaration(
        adapter_id="gb_ofcom_protected_numbers",
        country_codes=("GB",),
        source_id="ofcom_protected_numbers",
        source_name="Ofcom long-term protected number ranges",
        authority_type="official_regulator",
        source_url="https://www.ofcom.org.uk/phones-and-broadband/phone-numbers/numbering",
        reuse_basis=(
            "Ofcom permits accurate reproduction with Ofcom copyright and publication attribution."
        ),
        license="Ofcom copyright and information re-use terms",
        permitted_claim_types=("reserved_status",),
        freshness_max_age_seconds=2_592_000,
        failure_behavior="typed_gap",
        portability_limitations=_LIMITATIONS,
    )

    def __init__(self, fixture_path: Path = _DEFAULT_FIXTURE) -> None:
        self._fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    def lookup(
        self,
        phone_number: Mapping[str, Any],
        *,
        checked_at: datetime,
    ) -> AdapterResult:
        """Return public Ofcom observations for a normalized GB number."""
        canonical = phone_number.get("canonical", {})
        if canonical.get("country_calling_code") != "44":
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="GB",
                status=AdapterStatus.UNSUPPORTED,
                checked_at=checked_at,
                gaps=(
                    self._gap(
                        "unsupported_country",
                        "This adapter only covers numbers resolved to the United Kingdom.",
                        retryable=False,
                    ),
                ),
            )

        record = self._find_record(str(canonical.get("national_significant_number", "")))
        if record is None:
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="GB",
                status=AdapterStatus.NO_MATCH,
                checked_at=checked_at,
                gaps=(
                    self._gap(
                        "no_authoritative_data",
                        "The pinned Ofcom fixture has no authoritative observation for "
                        "this number.",
                        retryable=False,
                    ),
                ),
            )

        retrieved_at = _parse_utc(self._fixture["source"]["retrieved_at"])
        is_stale = checked_at.astimezone(UTC) > retrieved_at + timedelta(
            seconds=self.declaration.freshness_max_age_seconds
        )
        evidence = (
            self._evidence(
                record,
                canonical_e164=str(canonical["e164"]),
                freshness_status="stale" if is_stale else "current",
            ),
        )
        if is_stale:
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="GB",
                status=AdapterStatus.STALE,
                checked_at=checked_at,
                evidence=evidence,
                gaps=(
                    self._gap(
                        "source_stale",
                        "The pinned Ofcom observation is older than the declared freshness limit.",
                        retryable=True,
                    ),
                ),
            )
        return AdapterResult(
            declaration=self.declaration,
            jurisdiction="GB",
            status=AdapterStatus.MATCHED,
            checked_at=checked_at,
            evidence=evidence,
        )

    def _find_record(self, national_significant_number: str) -> dict[str, Any] | None:
        for record in self._fixture["records"]:
            prefix = record["national_prefix"]
            if not national_significant_number.startswith(prefix):
                continue
            subscriber = national_significant_number[len(prefix) :]
            same_width = len(subscriber) == len(record["subscriber_from"])
            if same_width and record["subscriber_from"] <= subscriber <= record["subscriber_to"]:
                return record
        return None

    def _evidence(
        self,
        record: Mapping[str, Any],
        *,
        canonical_e164: str,
        freshness_status: str,
    ) -> dict[str, Any]:
        source = self._fixture["source"]
        common_subscriber_prefix = _common_prefix(
            record["subscriber_from"], record["subscriber_to"]
        )
        return {
            "schema_version": "1.0.0",
            "kind": "source_evidence",
            "evidence_id": f"ev_ofcom-{record['source_record_id']}",
            "source": {
                "source_id": self.declaration.source_id,
                "name": self.declaration.source_name,
                "authority_type": self.declaration.authority_type,
                "jurisdiction": "GB",
                "locator": self.declaration.source_url,
                "reuse_basis": self.declaration.reuse_basis,
                "license": self.declaration.license,
            },
            "subject": {
                "kind": "number_range",
                "canonical_e164": canonical_e164,
                "range_prefix": (
                    "+44" + record["national_prefix"] + common_subscriber_prefix
                ),
            },
            "observation": {
                "evidence_class": "number_plan_fact",
                "claim_type": "reserved_status",
                "value": record["designation"],
                "publication_status": "public",
                "verification_status": "observed",
                "confidence": 1,
                "reason_codes": ["ofcom_long_term_protected_range"],
                "limitations": list(_LIMITATIONS),
            },
            "freshness": {
                "retrieved_at": source["retrieved_at"],
                "source_published_at": None,
                "valid_until": _format_utc(
                    _parse_utc(source["retrieved_at"])
                    + timedelta(seconds=self.declaration.freshness_max_age_seconds)
                ),
                "status": freshness_status,
                "max_age_seconds": self.declaration.freshness_max_age_seconds,
            },
            "provenance": {
                "source_document_id": f"ofcom-protected-numbers-{source['download_sha256']}",
                "source_record_id": record["source_record_id"],
                "transformation_version": "1.0.0",
                "content_digest": f"sha256:{record['source_row_sha256']}",
            },
        }

    def _gap(self, code: str, message: str, *, retryable: bool) -> EvidenceGap:
        return EvidenceGap(
            gap_id=f"gap_ofcom-{code.replace('_', '-')}",
            source_id=self.declaration.source_id,
            code=code,
            message=message,
            retryable=retryable,
        )


def _common_prefix(first: str, second: str) -> str:
    length = 0
    for left, right in zip(first, second, strict=True):
        if left != right:
            break
        length += 1
    return first[:length]


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
