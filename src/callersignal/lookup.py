"""Shared source-backed lookup orchestration for every CallerSignal surface."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from callersignal.adapters.base import CountryAdapter, EvidenceGap
from callersignal.adapters.gb import UnitedKingdomProtectedNumbersAdapter
from callersignal.adapters.nl import NetherlandsNumberRegisterAdapter
from callersignal.adapters.us import (
    FCCUnwantedCallAggregateAdapter,
    UnitedStatesNumberingAdapter,
)
from callersignal.assessment import assess_risk
from callersignal.evidence.ledger import EvidenceLedger
from callersignal.numbering import normalize_phone_number

_CALLING_CODE_COUNTRY = {"31": "NL", "44": "GB"}
_CONCLUSION_TYPE = {
    "country_assignment": "country",
    "number_type": "number_type",
    "range_holder": "range_holder",
    "original_carrier": "provider_claim",
    "current_provider_claim": "provider_claim",
    "regulatory_status": "regulatory_status",
    "reserved_status": "regulatory_status",
    "reported_activity_summary": "reported_activity",
    "reputation_status": "reputation_status",
}
_RESIDUAL_RISK = (
    "Caller ID spoofing remains possible; numbering evidence cannot prove who placed a call, "
    "whether the displayed number is reachable, or whether answering is safe."
)


class LookupService:
    """Normalize one request and assemble one versioned cross-surface result."""

    def __init__(
        self,
        *,
        adapters: Iterable[CountryAdapter] | None = None,
        ledger: EvidenceLedger | None = None,
        clock: Callable[[], datetime] | None = None,
        lookup_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._adapters = tuple(adapters) if adapters is not None else (
            NetherlandsNumberRegisterAdapter(),
            UnitedKingdomProtectedNumbersAdapter(),
            UnitedStatesNumberingAdapter(),
            FCCUnwantedCallAggregateAdapter(),
        )
        self._ledger = ledger
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lookup_id_factory = lookup_id_factory or (lambda: f"lkp_{uuid4().hex}")

    def lookup(self, raw_input: str, *, origin_region: str | None = None) -> dict[str, Any]:
        """Return source observations, typed gaps, and an uncertainty-honest assessment."""
        checked_at = self._clock()
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("Lookup clock must return a timezone-aware datetime.")
        phone_number = normalize_phone_number(raw_input, origin_region=origin_region)
        interpretation_status = phone_number["interpretation"]["status"]
        if interpretation_status not in {"valid", "possible"}:
            code = (
                "unsupported_country"
                if interpretation_status == "unsupported"
                else "invalid_input"
            )
            gap = _gap(
                source_id=None,
                code=code,
                message="The phone-number input cannot be checked against country sources.",
                retryable=False,
            )
            return self._result(phone_number, checked_at, [], [], [gap])

        country = _resolved_country(phone_number)
        selected = [
            adapter for adapter in self._adapters if country in adapter.declaration.country_codes
        ]
        if not selected:
            gap = _gap(
                source_id=None,
                code="unsupported_country",
                message=(
                    "CallerSignal has no public country adapter for this numbering jurisdiction."
                ),
                retryable=False,
            )
            return self._result(phone_number, checked_at, [], [], [gap])

        sources_checked: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        gaps: list[EvidenceGap] = []
        for adapter in selected:
            try:
                adapter_result = adapter.lookup(phone_number, checked_at=checked_at)
            except Exception:
                source_gap = _gap(
                    source_id=adapter.declaration.source_id,
                    code="source_error",
                    message="The declared source adapter failed without returning public evidence.",
                    retryable=True,
                )
                gaps.append(source_gap)
                sources_checked.append(
                    {
                        "source_id": adapter.declaration.source_id,
                        "jurisdiction": country,
                        "status": "error",
                        "risk_capable": _risk_capable(adapter.declaration),
                        "checked_at": _format_utc(checked_at),
                        "evidence_ids": [],
                        "gap_ids": [source_gap.gap_id],
                    }
                )
                continue

            returned_evidence = list(adapter_result.evidence)
            returned_gaps = list(adapter_result.gaps)
            evidence.extend(returned_evidence)
            gaps.extend(returned_gaps)
            sources_checked.append(
                {
                    "source_id": adapter_result.declaration.source_id,
                    "jurisdiction": adapter_result.jurisdiction,
                    "status": adapter_result.status.value,
                    "risk_capable": _risk_capable(adapter_result.declaration),
                    "checked_at": _format_utc(adapter_result.checked_at),
                    "evidence_ids": [item["evidence_id"] for item in returned_evidence],
                    "gap_ids": [item.gap_id for item in returned_gaps],
                }
            )

        if self._ledger is not None:
            for observation in evidence:
                self._ledger.append(observation)
        return self._result(phone_number, checked_at, sources_checked, evidence, gaps)

    def _result(
        self,
        phone_number: dict[str, Any],
        checked_at: datetime,
        sources_checked: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        gaps: list[EvidenceGap],
    ) -> dict[str, Any]:
        public_gaps = [_public_gap(item) for item in gaps]
        return {
            "schema_version": "1.0.0",
            "kind": "lookup_result",
            "lookup_id": self._lookup_id_factory(),
            "generated_at": _format_utc(checked_at),
            "phone_number": phone_number,
            "sources_checked": sources_checked,
            "evidence": evidence,
            "gaps": public_gaps,
            "assessment": _assessment(
                evidence,
                public_gaps,
                sources_checked,
                checked_at,
            ),
        }


def _resolved_country(phone_number: Mapping[str, Any]) -> str | None:
    canonical = phone_number["canonical"]
    region = canonical.get("region")
    if region is not None:
        return str(region)
    return _CALLING_CODE_COUNTRY.get(str(canonical.get("country_calling_code")))


def _risk_capable(declaration: Any) -> bool:
    return (
        bool(
            {"reported_activity_summary", "reputation_status"}.intersection(
                declaration.permitted_claim_types
            )
        )
        and declaration.authority_type
        in {
            "official_regulator",
            "licensed_data_provider",
            "moderated_community_aggregate",
        }
    )


def _gap(*, source_id: str | None, code: str, message: str, retryable: bool) -> EvidenceGap:
    identity = f"{source_id or 'lookup'}:{code}"
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    prefix = (source_id or "lookup")[:32]
    return EvidenceGap(
        gap_id=f"gap_{prefix}-{suffix}",
        source_id=source_id,
        code=code,
        message=message,
        retryable=retryable,
    )


def _public_gap(gap: EvidenceGap) -> dict[str, Any]:
    return {
        "gap_id": gap.gap_id,
        "source_id": gap.source_id,
        "code": gap.code,
        "message": gap.message,
        "retryable": gap.retryable,
    }


def _assessment(
    evidence: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    sources_checked: list[dict[str, Any]],
    checked_at: datetime,
) -> dict[str, Any]:
    current_evidence = [
        item for item in evidence if item.get("freshness", {}).get("status") == "current"
    ]
    if current_evidence:
        state = (
            "reported_activity"
            if any(
                item.get("observation", {}).get("claim_type") == "reputation_status"
                for item in current_evidence
            )
            else "numbering_context_only"
        )
        score = min(float(item["observation"]["confidence"]) for item in current_evidence)
        confidence = {
            "level": "high" if score >= 0.8 else "medium" if score >= 0.5 else "low",
            "score": score,
        }
    else:
        unavailable_codes = {"source_unavailable", "source_error"}
        state = (
            "unavailable"
            if any(item["code"] in unavailable_codes for item in gaps)
            else "unknown"
        )
        confidence = {"level": "none", "score": 0}

    reason_codes = sorted(
        {
            reason
            for item in evidence
            for reason in item.get("observation", {}).get("reason_codes", [])
        }
        | {item["code"] for item in gaps}
    )
    if not reason_codes:
        reason_codes = ["no_authoritative_evidence"]

    freshness_values = [item["freshness"]["status"] for item in evidence]
    if not freshness_values:
        freshness_status = "no_evidence"
    elif set(freshness_values) == {"current"}:
        freshness_status = "current"
    elif set(freshness_values) == {"stale"}:
        freshness_status = "stale"
    else:
        freshness_status = "mixed"
    retrieved_values = [item["freshness"]["retrieved_at"] for item in evidence]

    return {
        "state": state,
        "confidence": confidence,
        "reason_codes": reason_codes,
        "provenance": {
            "policy_version": "1.0.0",
            "computed_at": _format_utc(checked_at),
            "evidence_ids": [item["evidence_id"] for item in evidence],
            "gap_ids": [item["gap_id"] for item in gaps],
        },
        "freshness": {
            "as_of": _format_utc(checked_at),
            "oldest_evidence_at": min(retrieved_values) if retrieved_values else None,
            "status": freshness_status,
        },
        "conclusions": [
            _conclusion(item)
            for item in current_evidence
            if item["observation"]["claim_type"] in _CONCLUSION_TYPE
        ],
        "residual_risk": _RESIDUAL_RISK,
        "risk": assess_risk(
            evidence=evidence,
            gaps=gaps,
            sources_checked=sources_checked,
            checked_at=checked_at,
        ),
    }


def _conclusion(evidence: Mapping[str, Any]) -> dict[str, Any]:
    observation = evidence["observation"]
    claim_type = observation["claim_type"]
    raw_value = observation["value"]
    value = (
        ", ".join(str(item) for item in raw_value)
        if isinstance(raw_value, list)
        else str(raw_value)
    )
    conclusion_type = _CONCLUSION_TYPE[claim_type]
    wording = {
        "range_holder": (
            f"The source identifies {value} as the range holder, not as the caller or subscriber."
        ),
        "provider_claim": (
            f"The source states {value} as provider context; portability can make it outdated."
        ),
        "regulatory_status": (
            f"The source records regulatory or numbering-plan status: {value}."
        ),
        "country": f"The source associates this numbering context with {value}.",
        "number_type": f"The source classifies this numbering context as {value}.",
        "reported_activity": f"The source records this reported activity summary: {value}.",
        "reputation_status": (
            (
                "The source returned no current risk match at check time; this does not prove "
                "that a call is safe."
            )
            if value == "no_current_risk_match"
            else (
                "The source classifies aggregate activity associated with this displayed number "
                f"as {value}; this does not identify the caller or subscriber."
            )
        ),
    }[conclusion_type]
    return {
        "type": conclusion_type,
        "value": value,
        "confidence": observation["confidence"],
        "evidence_ids": [evidence["evidence_id"]],
        "wording": wording,
    }


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
