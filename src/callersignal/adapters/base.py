"""Country-adapter protocol and public evidence boundary."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

_TOKEN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_GAP_ID = re.compile(r"^gap_[A-Za-z0-9_-]{8,64}$")
_AUTHORITY_TYPES = {
    "official_regulator",
    "numbering_administrator",
    "licensed_data_provider",
    "verified_organization",
    "moderated_community_aggregate",
}
_CLAIM_TYPES = {
    "country_assignment",
    "number_type",
    "reserved_status",
    "range_holder",
    "original_carrier",
    "current_provider_claim",
    "reachability_claim",
    "regulatory_status",
    "reported_activity_summary",
    "reputation_status",
}
_REPUTATION_REASONS = {
    "spam": "aggregate_status_spam",
    "phishing": "aggregate_status_phishing",
    "scam": "aggregate_status_scam",
    "telemarketing": "aggregate_status_telemarketing",
    "robocall": "aggregate_status_robocall",
    "nuisance": "aggregate_status_nuisance",
    "no_current_risk_match": "aggregate_status_no_current_risk_match",
}
_REPUTATION_SAMPLE_BASES = {
    "official_regulatory_observation",
    "licensed_provider_aggregate",
    "moderated_community_aggregate",
    "source_no_match",
}
_GAP_CODES = {
    "invalid_input",
    "ambiguous_input",
    "unsupported_country",
    "source_unavailable",
    "source_stale",
    "source_error",
    "no_authoritative_data",
    "conflicting_evidence",
    "reuse_restricted",
}


class AdapterContractError(ValueError):
    """Raised when an adapter declaration or result violates the public contract."""


class AdapterStatus(StrEnum):
    """Outcome of checking one declared source."""

    MATCHED = "matched"
    NO_MATCH = "no_match"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    ERROR = "error"


_REQUIRED_GAP_CODE = {
    AdapterStatus.NO_MATCH: "no_authoritative_data",
    AdapterStatus.UNAVAILABLE: "source_unavailable",
    AdapterStatus.UNSUPPORTED: "unsupported_country",
    AdapterStatus.STALE: "source_stale",
    AdapterStatus.ERROR: "source_error",
}


@dataclass(frozen=True, slots=True)
class SourceDeclaration:
    """Stable metadata an adapter must publish before it can return evidence."""

    adapter_id: str
    country_codes: tuple[str, ...]
    source_id: str
    source_name: str
    authority_type: str
    source_url: str
    reuse_basis: str
    license: str
    permitted_claim_types: tuple[str, ...]
    freshness_max_age_seconds: int
    failure_behavior: str
    portability_limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _TOKEN.fullmatch(self.adapter_id) or not _TOKEN.fullmatch(self.source_id):
            raise AdapterContractError("Adapter and source identifiers must be canonical tokens.")
        if not self.country_codes or any(
            len(code) != 2 or not code.isascii() or not code.isupper()
            for code in self.country_codes
        ):
            raise AdapterContractError("Country coverage requires uppercase ISO alpha-2 codes.")
        if len(set(self.country_codes)) != len(self.country_codes):
            raise AdapterContractError("Country coverage cannot contain duplicates.")
        if len(self.source_name.strip()) < 3:
            raise AdapterContractError("A source name is required.")
        if self.authority_type not in _AUTHORITY_TYPES:
            raise AdapterContractError("The source authority type is not supported.")
        locator = urlparse(self.source_url)
        if locator.scheme not in {"http", "https"} or not locator.netloc:
            raise AdapterContractError("The source URL must be an absolute HTTP(S) URL.")
        if len(self.reuse_basis.strip()) < 20 or len(self.license.strip()) < 3:
            raise AdapterContractError("Source reuse basis and license must be declared.")
        if not self.permitted_claim_types or not set(self.permitted_claim_types) <= _CLAIM_TYPES:
            raise AdapterContractError("Permitted non-identity claim types must be declared.")
        if self.freshness_max_age_seconds <= 0:
            raise AdapterContractError("A positive source freshness limit is required.")
        if self.failure_behavior != "typed_gap":
            raise AdapterContractError("Adapters must fail with a typed gap.")
        if not self.portability_limitations or any(
            len(limitation.strip()) < 12 for limitation in self.portability_limitations
        ):
            raise AdapterContractError("Portability limitations must be explicit.")


@dataclass(frozen=True, slots=True)
class EvidenceGap:
    """A machine-readable statement of evidence the source could not provide."""

    gap_id: str
    source_id: str | None
    code: str
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        if not _GAP_ID.fullmatch(self.gap_id):
            raise AdapterContractError("Gap identifiers must follow the lookup-result schema.")
        if self.source_id is not None and not _TOKEN.fullmatch(self.source_id):
            raise AdapterContractError("Gap source identifiers must be canonical tokens.")
        if self.code not in _GAP_CODES:
            raise AdapterContractError("Gap code is not part of the lookup-result contract.")
        if len(self.message.strip()) < 12:
            raise AdapterContractError("Gap messages must explain the missing evidence.")


@dataclass(frozen=True, slots=True, init=False)
class AdapterResult:
    """Immutable public observations and gaps returned by one country adapter."""

    declaration: SourceDeclaration
    jurisdiction: str
    status: AdapterStatus
    checked_at: datetime
    gaps: tuple[EvidenceGap, ...]
    _canonical_evidence: tuple[str, ...] = field(repr=False)

    def __init__(
        self,
        *,
        declaration: SourceDeclaration,
        jurisdiction: str,
        status: AdapterStatus,
        checked_at: datetime,
        evidence: tuple[Mapping[str, Any], ...] = (),
        gaps: tuple[EvidenceGap, ...] = (),
    ) -> None:
        try:
            normalized_status = AdapterStatus(status)
        except ValueError as exc:
            raise AdapterContractError("Adapter status is not supported.") from exc
        canonical_evidence = tuple(
            json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            for item in evidence
        )
        object.__setattr__(self, "declaration", declaration)
        object.__setattr__(self, "jurisdiction", jurisdiction)
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "checked_at", checked_at)
        object.__setattr__(self, "gaps", tuple(gaps))
        object.__setattr__(self, "_canonical_evidence", canonical_evidence)
        self._validate()

    @property
    def evidence(self) -> tuple[dict[str, Any], ...]:
        """Return detached evidence views so adapter output cannot be mutated."""
        return tuple(json.loads(item) for item in self._canonical_evidence)

    def _validate(self) -> None:
        if self.jurisdiction not in self.declaration.country_codes:
            raise AdapterContractError("Result jurisdiction is outside declared country coverage.")
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise AdapterContractError("Source check time must be timezone-aware.")
        for item in self.evidence:
            source = item.get("source", {})
            observation = item.get("observation", {})
            if source.get("source_id") != self.declaration.source_id:
                raise AdapterContractError("Evidence source differs from the declared source.")
            if (
                observation.get("evidence_class") == "identity_claim"
                or observation.get("claim_type") == "subscriber_identity_claim"
            ):
                raise AdapterContractError(
                    "Subscriber identity evidence is not public adapter output."
                )
            if observation.get("publication_status") != "public":
                raise AdapterContractError("Adapter evidence must be explicitly public.")
            if observation.get("claim_type") not in self.declaration.permitted_claim_types:
                raise AdapterContractError("Evidence claim type is outside the source declaration.")
            if observation.get("claim_type") == "reputation_status":
                self._validate_reputation_status(observation)
        for item in self.gaps:
            if item.source_id not in {None, self.declaration.source_id}:
                raise AdapterContractError("Gap source differs from the declared source.")

        if self.status is AdapterStatus.MATCHED:
            if not self._canonical_evidence:
                raise AdapterContractError("A matched result requires public evidence.")
            return

        required_code = _REQUIRED_GAP_CODE[self.status]
        if not any(item.code == required_code for item in self.gaps):
            raise AdapterContractError(
                f"A {self.status.value} result requires its typed gap: {required_code}."
            )
        if self.status is AdapterStatus.STALE:
            if any(item.get("freshness", {}).get("status") != "stale" for item in self.evidence):
                raise AdapterContractError("Stale evidence must be explicitly marked stale.")
        elif self._canonical_evidence:
            raise AdapterContractError(
                f"A {self.status.value} result cannot include source evidence."
            )

    def _validate_reputation_status(self, observation: Mapping[str, Any]) -> None:
        reputation = observation.get("reputation")
        if not isinstance(reputation, Mapping):
            raise AdapterContractError("Reputation evidence requires bounded status metadata.")
        category = reputation.get("category")
        if category not in _REPUTATION_REASONS or observation.get("value") != category:
            raise AdapterContractError("Reputation category is unsupported or inconsistent.")
        native_value = reputation.get("source_native_value")
        if (
            not isinstance(native_value, str)
            or not native_value.strip()
            or native_value.strip().casefold() == "safe"
        ):
            raise AdapterContractError("A source-native safe verdict cannot enter evidence.")
        sample_basis = reputation.get("sample_basis")
        if sample_basis not in _REPUTATION_SAMPLE_BASES:
            raise AdapterContractError("Reputation sample basis is not supported.")
        if (category == "no_current_risk_match") != (sample_basis == "source_no_match"):
            raise AdapterContractError("No-match status requires the dedicated sample basis.")
        if _REPUTATION_REASONS[category] not in observation.get("reason_codes", []):
            raise AdapterContractError("Reputation status requires its stable reason code.")


@runtime_checkable
class CountryAdapter(Protocol):
    """Structural interface implemented by independently packaged country adapters."""

    declaration: SourceDeclaration

    def lookup(
        self,
        phone_number: Mapping[str, Any],
        *,
        checked_at: datetime,
    ) -> AdapterResult:
        """Return public observations and typed evidence gaps for one number."""
