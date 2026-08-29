"""Netherlands adapter for a pinned public-safe ACM number-register fixture."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from callersignal.acm_catalog import (
    CatalogMetadata,
    CatalogReadError,
    CatalogRecord,
    lookup_acm_catalog,
)
from callersignal.adapters.base import (
    AdapterResult,
    AdapterStatus,
    EvidenceGap,
    SourceDeclaration,
)

_DEFAULT_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures/nl/acm_number_register.json"
_LIMITATIONS = (
    "The registered range holder is not necessarily the current provider or subscriber.",
    "A register allocation does not identify the caller and caller ID can be spoofed.",
)
_CATALOG_LIMITATIONS = (
    "Register status and number type do not identify a subscriber, caller, or current provider.",
    "Caller ID can be spoofed; a source match does not prove call origin or call safety.",
)
_REGISTER_STATUS = {
    "Toegekend": "assigned",
    "Afkoelen": "cooling_off",
    "Geblokkeerd": "blocked",
}


class NetherlandsNumberRegisterAdapter:
    """Resolve NL range facts without treating allocations as caller identity."""

    declaration = SourceDeclaration(
        adapter_id="nl_acm_number_register",
        country_codes=("NL",),
        source_id="acm_number_register",
        source_name="ACM public telephone number register",
        authority_type="official_regulator",
        source_url="https://www.acm.nl/nl/telefoonnummers-zoeken",
        reuse_basis=(
            "The Dutch government data catalogue publishes the ACM register as public CC0 data."
        ),
        license="CC0 1.0",
        permitted_claim_types=("number_type", "range_holder", "regulatory_status"),
        freshness_max_age_seconds=2_592_000,
        failure_behavior="typed_gap",
        portability_limitations=_LIMITATIONS,
    )

    def __init__(
        self,
        fixture_path: Path = _DEFAULT_FIXTURE,
        *,
        catalog_path: Path | None = None,
    ) -> None:
        self._fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        configured_path = os.environ.get("CALLERSIGNAL_ACM_CATALOG_PATH")
        self._catalog_path = catalog_path or (
            Path(configured_path) if configured_path else None
        )

    def lookup(
        self,
        phone_number: Mapping[str, Any],
        *,
        checked_at: datetime,
    ) -> AdapterResult:
        """Return ACM observations for a normalized NL number."""
        canonical = phone_number.get("canonical", {})
        if canonical.get("region") != "NL":
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="NL",
                status=AdapterStatus.UNSUPPORTED,
                checked_at=checked_at,
                gaps=(
                    self._gap(
                        "unsupported_country",
                        "This adapter only covers numbers resolved to the Netherlands.",
                        retryable=False,
                    ),
                ),
            )

        if self._catalog_path is not None:
            try:
                metadata, catalog_record = lookup_acm_catalog(
                    self._catalog_path,
                    str(canonical["e164"]),
                )
            except CatalogReadError:
                return self._fixture_or_unavailable(canonical, checked_at=checked_at)
            if catalog_record is None:
                return AdapterResult(
                    declaration=self.declaration,
                    jurisdiction="NL",
                    status=AdapterStatus.NO_MATCH,
                    checked_at=checked_at,
                    gaps=(
                        self._gap(
                            "no_authoritative_data",
                            "The current full ACM catalogue has no matching numbering record.",
                            retryable=False,
                        ),
                    ),
                )
            return self._catalog_result(
                catalog_record,
                metadata,
                canonical_e164=str(canonical["e164"]),
                checked_at=checked_at,
            )

        return self._fixture_result(canonical, checked_at=checked_at)

    def _fixture_or_unavailable(
        self,
        canonical: Mapping[str, Any],
        *,
        checked_at: datetime,
    ) -> AdapterResult:
        record = self._find_record(str(canonical.get("national_significant_number", "")))
        if record is not None:
            return self._fixture_result(canonical, checked_at=checked_at)
        return AdapterResult(
            declaration=self.declaration,
            jurisdiction="NL",
            status=AdapterStatus.UNAVAILABLE,
            checked_at=checked_at,
            gaps=(
                self._gap(
                    "source_unavailable",
                    "The generated ACM catalogue is unavailable or invalid for this lookup.",
                    retryable=True,
                ),
            ),
        )

    def _fixture_result(
        self,
        canonical: Mapping[str, Any],
        *,
        checked_at: datetime,
    ) -> AdapterResult:
        record = self._find_record(str(canonical.get("national_significant_number", "")))
        if record is None:
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="NL",
                status=AdapterStatus.NO_MATCH,
                checked_at=checked_at,
                gaps=(
                    self._gap(
                        "no_authoritative_data",
                        "The pinned ACM fixture has no authoritative observation for this number.",
                        retryable=False,
                    ),
                ),
            )

        retrieved_at = _parse_utc(self._fixture["source"]["retrieved_at"])
        is_stale = checked_at.astimezone(UTC) > retrieved_at + timedelta(
            seconds=self.declaration.freshness_max_age_seconds
        )
        evidence = self._evidence(
            record,
            canonical_e164=str(canonical["e164"]),
            freshness_status="stale" if is_stale else "current",
        )
        if is_stale:
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="NL",
                status=AdapterStatus.STALE,
                checked_at=checked_at,
                evidence=evidence,
                gaps=(
                    self._gap(
                        "source_stale",
                        "The pinned ACM observation is older than the declared freshness limit.",
                        retryable=True,
                    ),
                ),
            )
        return AdapterResult(
            declaration=self.declaration,
            jurisdiction="NL",
            status=AdapterStatus.MATCHED,
            checked_at=checked_at,
            evidence=evidence,
        )

    def _catalog_result(
        self,
        record: CatalogRecord,
        metadata: CatalogMetadata,
        *,
        canonical_e164: str,
        checked_at: datetime,
    ) -> AdapterResult:
        retrieved_at = _parse_utc(metadata.retrieved_at)
        is_stale = checked_at.astimezone(UTC) > retrieved_at + timedelta(
            seconds=self.declaration.freshness_max_age_seconds
        )
        evidence = self._catalog_evidence(
            record,
            metadata,
            canonical_e164=canonical_e164,
            freshness_status="stale" if is_stale else "current",
        )
        if is_stale:
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="NL",
                status=AdapterStatus.STALE,
                checked_at=checked_at,
                evidence=evidence,
                gaps=(
                    self._gap(
                        "source_stale",
                        "The generated ACM catalogue is older than the freshness limit.",
                        retryable=True,
                    ),
                ),
            )
        return AdapterResult(
            declaration=self.declaration,
            jurisdiction="NL",
            status=AdapterStatus.MATCHED,
            checked_at=checked_at,
            evidence=evidence,
        )

    def _find_record(self, national_significant_number: str) -> dict[str, Any] | None:
        for record in self._fixture["records"]:
            start = _national_significant_number(record["national_range_from"])
            end = _national_significant_number(record["national_range_to"])
            same_width = len(national_significant_number) == len(start)
            if same_width and start <= national_significant_number <= end:
                return record
        return None

    def _evidence(
        self,
        record: Mapping[str, Any],
        *,
        canonical_e164: str,
        freshness_status: str,
    ) -> tuple[dict[str, Any], ...]:
        source = self._fixture["source"]
        common = {
            "schema_version": "1.0.0",
            "kind": "source_evidence",
            "source": {
                "source_id": self.declaration.source_id,
                "name": self.declaration.source_name,
                "authority_type": self.declaration.authority_type,
                "jurisdiction": "NL",
                "locator": self.declaration.source_url,
                "reuse_basis": self.declaration.reuse_basis,
                "license": self.declaration.license,
            },
            "subject": {
                "kind": "number_range",
                "canonical_e164": canonical_e164,
                "range_prefix": canonical_e164,
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
                "source_document_id": f"acm-number-register-{source['download_sha256']}",
                "source_record_id": record["source_record_id"],
                "transformation_version": "1.0.0",
                "content_digest": f"sha256:{record['source_row_sha256']}",
            },
        }
        return (
            {
                **common,
                "evidence_id": f"ev_acm-{record['source_record_id']}-range-holder",
                "observation": self._observation(
                    evidence_class="range_allocation",
                    claim_type="range_holder",
                    value=record["range_holder"],
                    reason_code="official_register_range_holder",
                ),
            },
            {
                **common,
                "evidence_id": f"ev_acm-{record['source_record_id']}-regulatory-status",
                "observation": self._observation(
                    evidence_class="regulatory_notice",
                    claim_type="regulatory_status",
                    value=record["register_status"],
                    reason_code="official_register_status",
                ),
            },
        )

    def _catalog_evidence(
        self,
        record: CatalogRecord,
        metadata: CatalogMetadata,
        *,
        canonical_e164: str,
        freshness_status: str,
    ) -> tuple[dict[str, Any], ...]:
        common = {
            "schema_version": "1.0.0",
            "kind": "source_evidence",
            "source": {
                "source_id": self.declaration.source_id,
                "name": self.declaration.source_name,
                "authority_type": self.declaration.authority_type,
                "jurisdiction": "NL",
                "locator": self.declaration.source_url,
                "reuse_basis": self.declaration.reuse_basis,
                "license": self.declaration.license,
            },
            "subject": {
                "kind": "number_range",
                "canonical_e164": canonical_e164,
                "range_prefix": canonical_e164,
            },
            "freshness": {
                "retrieved_at": metadata.retrieved_at,
                "source_published_at": None,
                "valid_until": _format_utc(
                    _parse_utc(metadata.retrieved_at)
                    + timedelta(seconds=self.declaration.freshness_max_age_seconds)
                ),
                "status": freshness_status,
                "max_age_seconds": self.declaration.freshness_max_age_seconds,
            },
            "provenance": {
                "source_document_id": f"acm-number-register-{metadata.source_sha256}",
                "source_record_id": record.source_record_id,
                "transformation_version": "1.0.0",
                "content_digest": f"sha256:{record.source_row_sha256}",
            },
        }
        return (
            {
                **common,
                "evidence_id": f"ev_acm-{record.source_record_id}-number-type",
                "observation": self._observation(
                    evidence_class="number_plan_fact",
                    claim_type="number_type",
                    value=record.number_type,
                    reason_code="official_register_number_type",
                    limitations=_CATALOG_LIMITATIONS,
                ),
            },
            {
                **common,
                "evidence_id": f"ev_acm-{record.source_record_id}-regulatory-status",
                "observation": self._observation(
                    evidence_class="regulatory_notice",
                    claim_type="regulatory_status",
                    value=_REGISTER_STATUS[record.register_status],
                    reason_code="official_register_status",
                    limitations=_CATALOG_LIMITATIONS,
                ),
            },
        )

    @staticmethod
    def _observation(
        *,
        evidence_class: str,
        claim_type: str,
        value: str,
        reason_code: str,
        limitations: tuple[str, ...] = _LIMITATIONS,
    ) -> dict[str, Any]:
        return {
            "evidence_class": evidence_class,
            "claim_type": claim_type,
            "value": value,
            "publication_status": "public",
            "verification_status": "observed",
            "confidence": 1,
            "reason_codes": [reason_code],
            "limitations": list(limitations),
        }

    def _gap(self, code: str, message: str, *, retryable: bool) -> EvidenceGap:
        return EvidenceGap(
            gap_id=f"gap_acm-{code.replace('_', '-')}",
            source_id=self.declaration.source_id,
            code=code,
            message=message,
            retryable=retryable,
        )


def _national_significant_number(national: str) -> str:
    digits = re.sub(r"\D", "", national)
    return digits[1:] if digits.startswith("0") else digits


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
