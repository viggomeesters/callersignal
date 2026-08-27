"""Country-aware phone-number interpretation for CallerSignal."""

from __future__ import annotations

from typing import Any

import phonenumbers

_NUMBER_TYPES = {
    phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
    phonenumbers.PhoneNumberType.MOBILE: "mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_or_mobile",
    phonenumbers.PhoneNumberType.VOIP: "voip",
    phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
    phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium_rate",
    phonenumbers.PhoneNumberType.SHARED_COST: "shared_cost",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal_number",
    phonenumbers.PhoneNumberType.PAGER: "pager",
    phonenumbers.PhoneNumberType.UAN: "uan",
    phonenumbers.PhoneNumberType.VOICEMAIL: "voicemail",
    phonenumbers.PhoneNumberType.UNKNOWN: "unknown",
}


class OriginRegionRequiredError(ValueError):
    """Raised when national-format input has no explicit origin region."""


def _empty_result(
    raw_input: str,
    *,
    origin_region: str | None,
    is_international: bool,
    status: str,
    reason_code: str,
    number_type: str = "unknown",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "kind": "phone_number",
        "raw_input": raw_input,
        "origin_region": None if is_international else origin_region,
        "interpretation": {
            "input_mode": "international" if is_international else "national",
            "region_source": (
                "embedded_country_code" if is_international else "explicit_origin_region"
            ),
            "status": status,
            "reason_codes": [reason_code],
        },
        "canonical": {
            "e164": None,
            "country_calling_code": None,
            "region": None,
            "national_significant_number": None,
            "number_type": number_type,
        },
        "presentation": {"international": None, "national": None},
    }


def normalize_phone_number(raw_input: str, *, origin_region: str | None = None) -> dict[str, Any]:
    """Interpret one national or international phone-number input."""
    is_international = raw_input.strip().startswith("+")
    region = origin_region.upper() if origin_region else None
    if not is_international and region is None:
        raise OriginRegionRequiredError("National phone-number input requires an origin region.")
    try:
        parsed = phonenumbers.parse(raw_input, None if is_international else region)
    except phonenumbers.NumberParseException as exc:
        reason_code = {
            phonenumbers.NumberParseException.INVALID_COUNTRY_CODE: "invalid_country_code",
            phonenumbers.NumberParseException.NOT_A_NUMBER: "not_a_number",
            phonenumbers.NumberParseException.TOO_SHORT_AFTER_IDD: "too_short_after_idd",
            phonenumbers.NumberParseException.TOO_SHORT_NSN: "too_short",
            phonenumbers.NumberParseException.TOO_LONG: "too_long",
        }[exc.error_type]
        return _empty_result(
            raw_input,
            origin_region=region,
            is_international=is_international,
            status="invalid",
            reason_code=reason_code,
        )
    if region and phonenumbers.is_possible_short_number_for_region(parsed, region):
        return _empty_result(
            raw_input,
            origin_region=region,
            is_international=is_international,
            status="unsupported",
            reason_code="short_number_not_supported",
            number_type="short_code",
        )
    if not phonenumbers.is_possible_number(parsed):
        return _empty_result(
            raw_input,
            origin_region=region,
            is_international=is_international,
            status="invalid",
            reason_code="impossible_number",
        )
    resolved_region = phonenumbers.region_code_for_number(parsed)
    input_mode = "international" if is_international else "national"
    is_valid = phonenumbers.is_valid_number(parsed)
    reason_codes = [
        (
            "parsed_from_international_prefix"
            if is_valid and is_international
            else "parsed_with_explicit_region" if is_valid else "possible_but_not_valid"
        )
    ]
    if resolved_region == "001":
        resolved_region = None
        reason_codes.append("non_geographic_number")

    return {
        "schema_version": "1.0.0",
        "kind": "phone_number",
        "raw_input": raw_input,
        "origin_region": None if is_international else region,
        "interpretation": {
            "input_mode": input_mode,
            "region_source": (
                "embedded_country_code" if is_international else "explicit_origin_region"
            ),
            "status": "valid" if is_valid else "possible",
            "reason_codes": reason_codes,
        },
        "canonical": {
            "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
            "country_calling_code": str(parsed.country_code),
            "region": resolved_region,
            "national_significant_number": phonenumbers.national_significant_number(parsed),
            "number_type": _NUMBER_TYPES[phonenumbers.number_type(parsed)],
        },
        "presentation": {
            "international": phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
            ),
            "national": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL),
        },
    }
