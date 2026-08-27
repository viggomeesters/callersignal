"""United States adapter for pinned public NANPA numbering facts."""

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

_DEFAULT_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures/us/nanpa_public_numbering.json"
_LIMITATIONS = (
    "Area-code assignment or availability does not establish that an exact number is assigned.",
    "Numbering-plan status does not identify a provider, subscriber, caller, or call origin.",
    "Caller ID can be spoofed even when the displayed number is valid or specially reserved.",
)


class UnitedStatesNumberingAdapter:
    """Resolve public US numbering context without inferring assignment or identity."""

    declaration = SourceDeclaration(
        adapter_id="us_nanpa_public_numbering",
        country_codes=("US",),
        source_id="nanpa_public_numbering",
        source_name="NANPA public numbering references",
        authority_type="numbering_administrator",
        source_url="https://nanpa.com/numbering/555-line-numbers",
        reuse_basis=(
            "This fixture reproduces only public numbering status facts with attribution; "
            "the FCC identifies NANPA's public report as an official numbering source."
        ),
        license="Public factual extract with source attribution",
        permitted_claim_types=("regulatory_status", "reserved_status"),
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
        """Return public NANPA observations for a normalized US number."""
        canonical = phone_number.get("canonical", {})
        if canonical.get("region") != "US":
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="US",
                status=AdapterStatus.UNSUPPORTED,
                checked_at=checked_at,
                gaps=(
                    self._gap(
                        "unsupported_country",
                        "This adapter only covers numbers resolved to the United States.",
                        retryable=False,
                    ),
                ),
            )

        national = str(canonical.get("national_significant_number", ""))
        npa_record = self._find_npa(national[:3])
        if npa_record is None:
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="US",
                status=AdapterStatus.NO_MATCH,
                checked_at=checked_at,
                gaps=(
                    self._gap(
                        "no_authoritative_data",
                        "The pinned NANPA fixture has no authoritative observation for "
                        "this area code.",
                        retryable=False,
                    ),
                ),
            )

        retrieved_at = _parse_utc(self._fixture["source"]["retrieved_at"])
        is_stale = checked_at.astimezone(UTC) > retrieved_at + timedelta(
            seconds=self.declaration.freshness_max_age_seconds
        )
        freshness_status = "stale" if is_stale else "current"
        evidence = [
            self._npa_evidence(
                npa_record,
                canonical_e164=str(canonical["e164"]),
                freshness_status=freshness_status,
            )
        ]
        reserved_record = self._find_reserved_line(national[3:6], national[6:])
        if reserved_record is not None:
            evidence.append(
                self._reserved_evidence(
                    npa_record,
                    reserved_record,
                    canonical_e164=str(canonical["e164"]),
                    freshness_status=freshness_status,
                )
            )
        evidence_tuple = tuple(evidence)

        if is_stale:
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="US",
                status=AdapterStatus.STALE,
                checked_at=checked_at,
                evidence=evidence_tuple,
                gaps=(
                    self._gap(
                        "source_stale",
                        "The pinned NANPA observations are older than the freshness limit.",
                        retryable=True,
                    ),
                ),
            )
        return AdapterResult(
            declaration=self.declaration,
            jurisdiction="US",
            status=AdapterStatus.MATCHED,
            checked_at=checked_at,
            evidence=evidence_tuple,
        )

    def _find_npa(self, npa: str) -> dict[str, Any] | None:
        return next(
            (record for record in self._fixture["records"]["npa"] if record["npa"] == npa),
            None,
        )

    def _find_reserved_line(self, nxx: str, line: str) -> dict[str, Any] | None:
        return next(
            (
                record
                for record in self._fixture["records"]["reserved_lines"]
                if record["nxx"] == nxx and record["line_from"] <= line <= record["line_to"]
            ),
            None,
        )

    def _npa_evidence(
        self,
        record: Mapping[str, Any],
        *,
        canonical_e164: str,
        freshness_status: str,
    ) -> dict[str, Any]:
        statuses = []
        if record["assignable"]:
            statuses.append("npa_assignable")
        if record["assigned"]:
            statuses.append("npa_assigned")
        if record["in_service"]:
            statuses.append("npa_in_service")
        document = self._fixture["documents"]["npa_report"]
        return self._evidence(
            evidence_id=f"ev_nanpa-{record['source_record_id']}",
            canonical_e164=canonical_e164,
            subject_kind="numbering_plan",
            range_prefix="+1" + record["npa"],
            evidence_class="number_plan_fact",
            claim_type="regulatory_status",
            value=statuses,
            reason_code="nanpa_npa_status",
            locator=document["url"],
            source_published_at=document["file_date"] + "T00:00:00Z",
            source_document_id=f"nanpa-npa-report-{document['download_sha256']}",
            source_record_id=record["source_record_id"],
            content_digest=record["source_row_sha256"],
            freshness_status=freshness_status,
        )

    def _reserved_evidence(
        self,
        npa_record: Mapping[str, Any],
        record: Mapping[str, Any],
        *,
        canonical_e164: str,
        freshness_status: str,
    ) -> dict[str, Any]:
        document = self._fixture["documents"]["line_555_reference"]
        common_line_prefix = _common_prefix(record["line_from"], record["line_to"])
        return self._evidence(
            evidence_id=f"ev_nanpa-{npa_record['npa']}-{record['source_record_id']}",
            canonical_e164=canonical_e164,
            subject_kind="number_range",
            range_prefix="+1" + npa_record["npa"] + record["nxx"] + common_line_prefix,
            evidence_class="number_plan_fact",
            claim_type="reserved_status",
            value=record["designation"],
            reason_code="nanpa_fictional_line_range",
            locator=document["url"],
            source_published_at=None,
            source_document_id=f"nanpa-555-reference-{document['snapshot_sha256']}",
            source_record_id=record["source_record_id"],
            content_digest=record["source_fact_sha256"],
            freshness_status=freshness_status,
        )

    def _evidence(
        self,
        *,
        evidence_id: str,
        canonical_e164: str,
        subject_kind: str,
        range_prefix: str,
        evidence_class: str,
        claim_type: str,
        value: str | list[str],
        reason_code: str,
        locator: str,
        source_published_at: str | None,
        source_document_id: str,
        source_record_id: str,
        content_digest: str,
        freshness_status: str,
    ) -> dict[str, Any]:
        retrieved_at = self._fixture["source"]["retrieved_at"]
        return {
            "schema_version": "1.0.0",
            "kind": "source_evidence",
            "evidence_id": evidence_id,
            "source": {
                "source_id": self.declaration.source_id,
                "name": self.declaration.source_name,
                "authority_type": self.declaration.authority_type,
                "jurisdiction": "US",
                "locator": locator,
                "reuse_basis": self.declaration.reuse_basis,
                "license": self.declaration.license,
            },
            "subject": {
                "kind": subject_kind,
                "canonical_e164": canonical_e164,
                "range_prefix": range_prefix,
            },
            "observation": {
                "evidence_class": evidence_class,
                "claim_type": claim_type,
                "value": value,
                "publication_status": "public",
                "verification_status": "observed",
                "confidence": 1,
                "reason_codes": [reason_code],
                "limitations": list(_LIMITATIONS),
            },
            "freshness": {
                "retrieved_at": retrieved_at,
                "source_published_at": source_published_at,
                "valid_until": _format_utc(
                    _parse_utc(retrieved_at)
                    + timedelta(seconds=self.declaration.freshness_max_age_seconds)
                ),
                "status": freshness_status,
                "max_age_seconds": self.declaration.freshness_max_age_seconds,
            },
            "provenance": {
                "source_document_id": source_document_id,
                "source_record_id": source_record_id,
                "transformation_version": "1.0.0",
                "content_digest": f"sha256:{content_digest}",
            },
        }

    def _gap(self, code: str, message: str, *, retryable: bool) -> EvidenceGap:
        return EvidenceGap(
            gap_id=f"gap_nanpa-{code.replace('_', '-')}",
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
