import json
from pathlib import Path

import phonenumbers
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from callersignal.numbering import OriginRegionRequiredError, normalize_phone_number

ROOT = Path(__file__).resolve().parents[2]


def test_normalizes_a_national_nl_number_with_explicit_region() -> None:
    example = phonenumbers.example_number_for_type("NL", phonenumbers.PhoneNumberType.MOBILE)
    national = phonenumbers.format_number(example, phonenumbers.PhoneNumberFormat.NATIONAL)

    result = normalize_phone_number(national, origin_region="NL")

    assert result["origin_region"] == "NL"
    assert result["interpretation"] == {
        "input_mode": "national",
        "region_source": "explicit_origin_region",
        "status": "valid",
        "reason_codes": ["parsed_with_explicit_region"],
    }
    assert result["canonical"]["e164"] == phonenumbers.format_number(
        example, phonenumbers.PhoneNumberFormat.E164
    )
    assert result["canonical"]["region"] == "NL"
    assert result["canonical"]["number_type"] == "mobile"


def test_normalizes_an_international_us_number_without_region() -> None:
    international = "+1" + "202" + "555" + "0147"

    result = normalize_phone_number(international)

    assert result["origin_region"] is None
    assert result["interpretation"] == {
        "input_mode": "international",
        "region_source": "embedded_country_code",
        "status": "valid",
        "reason_codes": ["parsed_from_international_prefix"],
    }
    assert result["canonical"]["e164"] == international
    assert result["canonical"]["region"] == "US"


def test_rejects_ambiguous_national_input_without_origin_region() -> None:
    with pytest.raises(OriginRegionRequiredError, match="origin region"):
        normalize_phone_number("202-555-0147")


def test_normalizes_a_gb_mobile_example() -> None:
    example = phonenumbers.example_number_for_type("GB", phonenumbers.PhoneNumberType.MOBILE)
    national = phonenumbers.format_number(example, phonenumbers.PhoneNumberFormat.NATIONAL)

    result = normalize_phone_number(national, origin_region="gb")

    assert result["origin_region"] == "GB"
    assert result["canonical"]["e164"] == phonenumbers.format_number(
        example, phonenumbers.PhoneNumberFormat.E164
    )
    assert result["canonical"]["region"] == "GB"
    assert result["canonical"]["number_type"] == "mobile"


def test_returns_a_typed_invalid_result_for_malformed_input() -> None:
    result = normalize_phone_number("not-a-number", origin_region="US")

    assert result["interpretation"] == {
        "input_mode": "national",
        "region_source": "explicit_origin_region",
        "status": "invalid",
        "reason_codes": ["not_a_number"],
    }
    assert result["canonical"] == {
        "e164": None,
        "country_calling_code": None,
        "region": None,
        "national_significant_number": None,
        "number_type": "unknown",
    }
    assert result["presentation"] == {"international": None, "national": None}


def test_classifies_short_numbers_without_inventing_e164_identity() -> None:
    result = normalize_phone_number("112", origin_region="NL")

    assert result["interpretation"]["status"] == "unsupported"
    assert result["interpretation"]["reason_codes"] == ["short_number_not_supported"]
    assert result["canonical"]["e164"] is None
    assert result["canonical"]["number_type"] == "short_code"


def test_preserves_possible_but_unvalidated_international_numbers() -> None:
    international = "+1" + "200" + "555" + "0100"

    result = normalize_phone_number(international)

    assert result["interpretation"]["status"] == "possible"
    assert result["interpretation"]["reason_codes"] == ["possible_but_not_valid"]
    assert result["canonical"]["e164"] == international
    assert result["canonical"]["number_type"] == "unknown"


def test_normalizes_non_geographic_numbers_without_a_fake_region() -> None:
    international = "+800" + "1234" + "5678"

    result = normalize_phone_number(international)

    assert result["interpretation"]["status"] == "valid"
    assert result["interpretation"]["reason_codes"] == [
        "parsed_from_international_prefix",
        "non_geographic_number",
    ]
    assert result["canonical"]["e164"] == international
    assert result["canonical"]["country_calling_code"] == "800"
    assert result["canonical"]["region"] is None
    assert result["canonical"]["number_type"] == "toll_free"


@pytest.mark.parametrize(
    ("raw_input", "origin_region"),
    [
        ("202-555-0147", "US"),
        ("+1" + "202" + "555" + "0147", None),
        ("not-a-number", "US"),
        ("112", "NL"),
        ("+1" + "200" + "555" + "0100", None),
        ("+800" + "1234" + "5678", None),
    ],
)
def test_every_result_matches_the_phone_number_contract(
    raw_input: str, origin_region: str | None
) -> None:
    schema = json.loads(
        (ROOT / "schemas/phone-number.schema.json").read_text(encoding="utf-8")
    )
    result = normalize_phone_number(raw_input, origin_region=origin_region)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
