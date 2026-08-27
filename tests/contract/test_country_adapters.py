from datetime import UTC, datetime

import pytest

from callersignal.adapters.base import (
    AdapterContractError,
    AdapterResult,
    AdapterStatus,
    CountryAdapter,
    EvidenceGap,
    SourceDeclaration,
)

CHECKED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)


def declaration(**overrides: object) -> SourceDeclaration:
    values = {
        "adapter_id": "example_registry",
        "country_codes": ("US",),
        "source_id": "example_registry",
        "source_name": "Example public numbering registry",
        "authority_type": "official_regulator",
        "source_url": "https://example.invalid/numbering-register",
        "reuse_basis": "Public facts may be reused with source attribution.",
        "license": "Example Open Data Licence 1.0",
        "permitted_claim_types": ("range_holder", "number_type"),
        "freshness_max_age_seconds": 86_400,
        "failure_behavior": "typed_gap",
        "portability_limitations": (
            "A range holder is not necessarily the current provider or caller.",
        ),
    }
    values.update(overrides)
    return SourceDeclaration(**values)


def public_evidence() -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "source_evidence",
        "evidence_id": "ev_example-range-holder",
        "source": {"source_id": "example_registry"},
        "subject": {"canonical_e164": "+1" + "202" + "555" + "0147"},
        "observation": {
            "evidence_class": "range_allocation",
            "claim_type": "range_holder",
            "publication_status": "public",
            "value": "Example Telecommunications B.V.",
        },
        "freshness": {"status": "current"},
    }


def gap(code: str, *, retryable: bool) -> EvidenceGap:
    return EvidenceGap(
        gap_id=f"gap_{code}-example",
        source_id="example_registry",
        code=code,
        message="The source did not provide current authoritative evidence.",
        retryable=retryable,
    )


def test_source_declaration_requires_complete_rights_and_freshness_metadata() -> None:
    declared = declaration()

    assert declared.country_codes == ("US",)
    assert declared.authority_type == "official_regulator"
    assert declared.reuse_basis.startswith("Public facts")
    assert declared.license == "Example Open Data Licence 1.0"
    assert declared.freshness_max_age_seconds == 86_400
    assert declared.failure_behavior == "typed_gap"
    assert "current provider" in declared.portability_limitations[0]

    for missing in (
        "country_codes",
        "source_url",
        "reuse_basis",
        "license",
        "permitted_claim_types",
        "freshness_max_age_seconds",
        "portability_limitations",
    ):
        empty: object = () if missing.endswith(("codes", "types", "limitations")) else ""
        if missing == "freshness_max_age_seconds":
            empty = 0
        with pytest.raises(AdapterContractError):
            declaration(**{missing: empty})


def test_unavailable_source_fails_closed_with_a_retryable_gap() -> None:
    result = AdapterResult(
        declaration=declaration(),
        jurisdiction="US",
        status=AdapterStatus.UNAVAILABLE,
        checked_at=CHECKED_AT,
        gaps=(gap("source_unavailable", retryable=True),),
    )

    assert result.evidence == ()
    assert result.gaps[0].code == "source_unavailable"
    assert result.status is AdapterStatus.UNAVAILABLE
    assert not hasattr(result, "assessment")
    assert not hasattr(result, "safe")
    assert not hasattr(result, "identity")


def test_stale_source_exposes_only_marked_stale_evidence_and_remains_unknown() -> None:
    with pytest.raises(AdapterContractError, match="marked stale"):
        AdapterResult(
            declaration=declaration(),
            jurisdiction="US",
            status=AdapterStatus.STALE,
            checked_at=CHECKED_AT,
            evidence=(public_evidence(),),
            gaps=(gap("source_stale", retryable=True),),
        )

    stale_evidence = public_evidence()
    stale_evidence["freshness"]["status"] = "stale"
    stale = AdapterResult(
        declaration=declaration(),
        jurisdiction="US",
        status=AdapterStatus.STALE,
        checked_at=CHECKED_AT,
        evidence=(stale_evidence,),
        gaps=(gap("source_stale", retryable=True),),
    )
    assert stale.status is AdapterStatus.STALE
    assert not hasattr(stale, "assessment")
    assert stale.evidence[0]["freshness"]["status"] == "stale"


def test_matched_result_accepts_only_public_non_identity_observations() -> None:
    result = AdapterResult(
        declaration=declaration(),
        jurisdiction="US",
        status=AdapterStatus.MATCHED,
        checked_at=CHECKED_AT,
        evidence=(public_evidence(),),
    )

    returned = result.evidence[0]
    returned["observation"]["value"] = "mutated"
    assert result.evidence[0]["observation"]["value"] == "Example Telecommunications B.V."

    restricted = public_evidence()
    restricted["observation"].update(
        {
            "evidence_class": "identity_claim",
            "claim_type": "subscriber_identity_claim",
            "publication_status": "restricted",
        }
    )
    with pytest.raises(AdapterContractError, match="identity"):
        AdapterResult(
            declaration=declaration(),
            jurisdiction="US",
            status=AdapterStatus.MATCHED,
            checked_at=CHECKED_AT,
            evidence=(restricted,),
        )


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (AdapterStatus.NO_MATCH, "no_authoritative_data", False),
        (AdapterStatus.UNAVAILABLE, "source_unavailable", True),
        (AdapterStatus.UNSUPPORTED, "unsupported_country", False),
        (AdapterStatus.STALE, "source_stale", True),
        (AdapterStatus.ERROR, "source_error", True),
    ],
)
def test_every_non_match_status_requires_its_typed_gap(
    status: AdapterStatus,
    code: str,
    retryable: bool,
) -> None:
    with pytest.raises(AdapterContractError, match="typed gap"):
        AdapterResult(
            declaration=declaration(),
            jurisdiction="US",
            status=status,
            checked_at=CHECKED_AT,
        )

    result = AdapterResult(
        declaration=declaration(),
        jurisdiction="US",
        status=status,
        checked_at=CHECKED_AT,
        gaps=(gap(code, retryable=retryable),),
    )
    assert result.gaps[0].code == code


def test_result_rejects_wrong_jurisdiction_source_or_naive_time() -> None:
    with pytest.raises(AdapterContractError, match="jurisdiction"):
        AdapterResult(
            declaration=declaration(),
            jurisdiction="GB",
            status=AdapterStatus.MATCHED,
            checked_at=CHECKED_AT,
            evidence=(public_evidence(),),
        )

    wrong_source = public_evidence()
    wrong_source["source"]["source_id"] = "another_registry"
    with pytest.raises(AdapterContractError, match="source"):
        AdapterResult(
            declaration=declaration(),
            jurisdiction="US",
            status=AdapterStatus.MATCHED,
            checked_at=CHECKED_AT,
            evidence=(wrong_source,),
        )

    with pytest.raises(AdapterContractError, match="timezone"):
        AdapterResult(
            declaration=declaration(),
            jurisdiction="US",
            status=AdapterStatus.MATCHED,
            checked_at=datetime(2026, 8, 27, 8, 0),
            evidence=(public_evidence(),),
        )


def test_protocol_is_implementable_without_inheriting_a_base_class() -> None:
    class ExampleAdapter:
        declaration = declaration()

        def lookup(self, phone_number: dict, *, checked_at: datetime) -> AdapterResult:
            assert phone_number["canonical"]["region"] == "US"
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction="US",
                status=AdapterStatus.NO_MATCH,
                checked_at=checked_at,
                gaps=(gap("no_authoritative_data", retryable=False),),
            )

    normalized = {
        "canonical": {"region": "US", "e164": "+1" + "202" + "555" + "0147"}
    }
    adapter = ExampleAdapter()
    assert isinstance(adapter, CountryAdapter)
    assert adapter.lookup(normalized, checked_at=CHECKED_AT).status is AdapterStatus.NO_MATCH
