"""Bounded HTTPS adapter for explicitly licensed aggregate reputation feeds."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from callersignal.adapters.base import (
    AdapterResult,
    AdapterStatus,
    EvidenceGap,
    SourceDeclaration,
)

_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_ENVIRONMENT_KEY = re.compile(r"^[A-Z][A-Z0-9_]{5,79}$")
_CATEGORIES = {
    "spam",
    "phishing",
    "scam",
    "telemarketing",
    "robocall",
    "nuisance",
    "no_current_risk_match",
}
_REASON_CODES = {category: f"aggregate_status_{category}" for category in _CATEGORIES}
_LIMITATIONS = (
    "This is an aggregate provider status, not proof of caller or subscriber identity.",
    "Caller ID can be spoofed and a current source status does not prove call safety.",
)


class FeedConfigurationError(ValueError):
    """A registry record cannot safely activate a feed."""


class FeedTransportError(RuntimeError):
    """The bounded network transport could not return an eligible response."""


class FeedResponseError(ValueError):
    """A provider response drifted outside the admitted aggregate contract."""


@dataclass(frozen=True, slots=True)
class FeedHttpResponse:
    """Transport response after bounded JSON decoding."""

    status_code: int
    content_type: str
    body: Mapping[str, Any]
    body_bytes: int


class ReputationFeedTransport(Protocol):
    """Injected network boundary; implementations must not log request payloads."""

    def post_json(
        self,
        *,
        endpoint: str,
        credential: str,
        payload: Mapping[str, str],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> FeedHttpResponse: ...


@dataclass(frozen=True, slots=True)
class ReputationFeedDefinition:
    """Fully reviewed feed controls copied from the source registry."""

    source_id: str
    adapter_id: str
    source_name: str
    stable_url: str
    endpoint: str
    jurisdictions: tuple[str, ...]
    reuse_basis: str
    license: str
    credential_env: str
    requests_per_window: int
    window_seconds: int
    request_timeout_seconds: int
    max_response_bytes: int
    schedule_seconds: int
    freshness_max_age_seconds: int
    native_category_map: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        for locator in (self.stable_url, self.endpoint):
            parsed = urlparse(locator)
            if parsed.scheme != "https" or not parsed.netloc:
                raise FeedConfigurationError("Reputation feeds require absolute HTTPS locators.")
        if not _ENVIRONMENT_KEY.fullmatch(self.credential_env):
            raise FeedConfigurationError("Feed credentials require an explicit environment key.")
        if not self.jurisdictions or any(
            len(item) != 2 or not item.isascii() or not item.isupper()
            for item in self.jurisdictions
        ):
            raise FeedConfigurationError("Enabled feed jurisdictions must be explicit ISO codes.")
        if not 1 <= self.requests_per_window <= 10_000:
            raise FeedConfigurationError("Feed request limit is outside the bounded range.")
        if not 1 <= self.window_seconds <= 86_400:
            raise FeedConfigurationError("Feed rate window is outside the bounded range.")
        if not 1 <= self.request_timeout_seconds <= 30:
            raise FeedConfigurationError("Feed timeout is outside the bounded range.")
        if not 1_024 <= self.max_response_bytes <= 1_048_576:
            raise FeedConfigurationError("Feed response limit is outside the bounded range.")
        if not 60 <= self.schedule_seconds <= 2_592_000:
            raise FeedConfigurationError("Feed schedule is outside the bounded range.")
        if self.freshness_max_age_seconds <= 0:
            raise FeedConfigurationError("Feed freshness must be positive.")
        if not self.native_category_map:
            raise FeedConfigurationError("At least one reviewed native status mapping is required.")
        native_values = [native for native, _canonical in self.native_category_map]
        if len(native_values) != len(set(native_values)):
            raise FeedConfigurationError("Native status mappings cannot contain duplicates.")
        for native, canonical in self.native_category_map:
            if not native.strip() or len(native) > 120 or native.strip().casefold() == "safe":
                raise FeedConfigurationError("Source-native safe or empty labels are prohibited.")
            if canonical not in _CATEGORIES:
                raise FeedConfigurationError("A native status maps to an unsupported category.")


class _HttpsOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        raise FeedTransportError("Licensed feed redirects require a new reviewed endpoint.")


class HttpsJsonTransport:
    """Small dependency-free POST client with strict size, type, and TLS limits."""

    def post_json(
        self,
        *,
        endpoint: str,
        credential: str,
        payload: Mapping[str, str],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> FeedHttpResponse:
        if urlparse(endpoint).scheme != "https":
            raise FeedTransportError("Feed endpoint must use HTTPS.")
        encoded = json.dumps(
            dict(payload), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=encoded,
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
                "User-Agent": "CallerSignal/0.2 authorized-feed",
            },
        )
        opener = build_opener(
            _HttpsOnlyRedirectHandler(),
            HTTPSHandler(context=ssl.create_default_context()),
        )
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                body_bytes = response.read(max_response_bytes + 1)
                status_code = int(response.status)
                content_type = str(response.headers.get("Content-Type", ""))
        except HTTPError as exc:
            return FeedHttpResponse(
                status_code=exc.code,
                content_type=str(exc.headers.get("Content-Type", "")),
                body={},
                body_bytes=0,
            )
        except (OSError, TimeoutError, URLError) as exc:
            raise FeedTransportError("The licensed feed is unavailable.") from exc
        if len(body_bytes) > max_response_bytes:
            raise FeedTransportError("The licensed feed response exceeded its byte limit.")
        if not content_type.casefold().startswith("application/json"):
            raise FeedTransportError("The licensed feed did not return JSON.")
        try:
            body = json.loads(body_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FeedTransportError("The licensed feed returned invalid JSON.") from exc
        if not isinstance(body, Mapping):
            raise FeedTransportError("The licensed feed response must be an object.")
        return FeedHttpResponse(
            status_code=status_code,
            content_type=content_type,
            body=body,
            body_bytes=len(body_bytes),
        )


class FixedWindowRateLimiter:
    """Fail-fast per-source request limiter; it never sleeps or queues numbers."""

    def __init__(self, *, requests: int, window_seconds: int) -> None:
        self._requests = requests
        self._window = timedelta(seconds=window_seconds)
        self._attempts: deque[datetime] = deque()
        self._lock = RLock()

    def acquire(self, at: datetime) -> bool:
        with self._lock:
            boundary = at - self._window
            while self._attempts and self._attempts[0] <= boundary:
                self._attempts.popleft()
            if self._attempts and at < self._attempts[-1]:
                return False
            if len(self._attempts) >= self._requests:
                return False
            self._attempts.append(at)
            return True


class AuthorizedReputationAdapter:
    """Convert one licensed aggregate response into the shared evidence contract."""

    def __init__(
        self,
        definition: ReputationFeedDefinition,
        *,
        credential: str,
        transport: ReputationFeedTransport,
    ) -> None:
        if not credential.strip():
            raise FeedConfigurationError("A non-empty runtime credential is required.")
        self.definition = definition
        self._credential = credential
        self._transport = transport
        self._category_map = dict(definition.native_category_map)
        self._rate_limiter = FixedWindowRateLimiter(
            requests=definition.requests_per_window,
            window_seconds=definition.window_seconds,
        )
        self.declaration = SourceDeclaration(
            adapter_id=definition.adapter_id,
            country_codes=definition.jurisdictions,
            source_id=definition.source_id,
            source_name=definition.source_name,
            authority_type="licensed_data_provider",
            source_url=definition.stable_url,
            reuse_basis=definition.reuse_basis,
            license=definition.license,
            permitted_claim_types=("reputation_status",),
            freshness_max_age_seconds=definition.freshness_max_age_seconds,
            failure_behavior="typed_gap",
            portability_limitations=_LIMITATIONS,
        )

    @property
    def schedule_seconds(self) -> int:
        return self.definition.schedule_seconds

    def lookup(
        self,
        phone_number: Mapping[str, Any],
        *,
        checked_at: datetime,
    ) -> AdapterResult:
        canonical = phone_number.get("canonical", {})
        jurisdiction = str(canonical.get("region") or "")
        if jurisdiction not in self.declaration.country_codes:
            return self._gap_result(
                AdapterStatus.UNSUPPORTED,
                jurisdiction=self.declaration.country_codes[0],
                checked_at=checked_at,
                code="unsupported_country",
                message="This licensed feed does not cover the resolved jurisdiction.",
                retryable=False,
            )
        canonical_e164 = str(canonical.get("e164") or "")
        if not _E164.fullmatch(canonical_e164):
            return self._gap_result(
                AdapterStatus.ERROR,
                jurisdiction=jurisdiction,
                checked_at=checked_at,
                code="source_error",
                message="The licensed feed received no valid canonical lookup subject.",
                retryable=False,
            )
        if not self._rate_limiter.acquire(checked_at):
            return self._gap_result(
                AdapterStatus.UNAVAILABLE,
                jurisdiction=jurisdiction,
                checked_at=checked_at,
                code="source_unavailable",
                message="The licensed feed request limit is currently exhausted.",
                retryable=True,
            )
        try:
            response = self._transport.post_json(
                endpoint=self.definition.endpoint,
                credential=self._credential,
                payload={"phone_number": canonical_e164},
                timeout_seconds=self.definition.request_timeout_seconds,
                max_response_bytes=self.definition.max_response_bytes,
            )
        except Exception:
            return self._gap_result(
                AdapterStatus.UNAVAILABLE,
                jurisdiction=jurisdiction,
                checked_at=checked_at,
                code="source_unavailable",
                message="The licensed reputation source is currently unavailable.",
                retryable=True,
            )
        if response.status_code != 200:
            return self._gap_result(
                AdapterStatus.UNAVAILABLE,
                jurisdiction=jurisdiction,
                checked_at=checked_at,
                code="source_unavailable",
                message="The licensed reputation source returned no eligible response.",
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        try:
            evidence, is_stale = self._normalize_response(
                response,
                canonical_e164=canonical_e164,
                jurisdiction=jurisdiction,
                checked_at=checked_at,
            )
        except FeedResponseError:
            return self._gap_result(
                AdapterStatus.ERROR,
                jurisdiction=jurisdiction,
                checked_at=checked_at,
                code="source_error",
                message="The licensed reputation response failed its aggregate contract.",
                retryable=True,
            )
        if is_stale:
            return AdapterResult(
                declaration=self.declaration,
                jurisdiction=jurisdiction,
                status=AdapterStatus.STALE,
                checked_at=checked_at,
                evidence=(evidence,),
                gaps=(
                    self._gap(
                        "source_stale",
                        "The licensed reputation observation is older than its freshness limit.",
                        retryable=True,
                    ),
                ),
            )
        return AdapterResult(
            declaration=self.declaration,
            jurisdiction=jurisdiction,
            status=AdapterStatus.MATCHED,
            checked_at=checked_at,
            evidence=(evidence,),
        )

    def _normalize_response(
        self,
        response: FeedHttpResponse,
        *,
        canonical_e164: str,
        jurisdiction: str,
        checked_at: datetime,
    ) -> tuple[dict[str, Any], bool]:
        if response.body_bytes < 2 or response.body_bytes > self.definition.max_response_bytes:
            raise FeedResponseError("Response size is outside the reviewed boundary.")
        if not response.content_type.casefold().startswith("application/json"):
            raise FeedResponseError("Response type drifted outside JSON.")
        record_id = response.body.get("record_id")
        native_value = response.body.get("category")
        observed_value = response.body.get("observed_at")
        confidence = response.body.get("confidence")
        if not isinstance(record_id, str) or not _RECORD_ID.fullmatch(record_id):
            raise FeedResponseError("Provider record identity is not opaque and bounded.")
        if record_id.isdigit() or re.search(r"\d{8,}", record_id):
            raise FeedResponseError("Provider record identity cannot resemble a phone number.")
        if record_id in canonical_e164 or canonical_e164.removeprefix("+") in record_id:
            raise FeedResponseError("Provider record identity cannot repeat the phone number.")
        if not isinstance(native_value, str) or native_value.strip().casefold() == "safe":
            raise FeedResponseError("Source-native safety claims are prohibited.")
        try:
            category = self._category_map[native_value]
        except KeyError as exc:
            raise FeedResponseError("Provider category is not mapped by the review.") from exc
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise FeedResponseError("Provider confidence must be numeric.")
        numeric_confidence = float(confidence)
        if not 0 <= numeric_confidence <= 1:
            raise FeedResponseError("Provider confidence is outside the bounded range.")
        observed_at = _parse_utc(observed_value)
        if observed_at > checked_at.astimezone(UTC) + timedelta(minutes=5):
            raise FeedResponseError("Provider observation time is implausibly in the future.")
        valid_until = observed_at + timedelta(
            seconds=self.definition.freshness_max_age_seconds
        )
        is_stale = checked_at.astimezone(UTC) > valid_until
        sample_basis = (
            "source_no_match"
            if category == "no_current_risk_match"
            else "licensed_provider_aggregate"
        )
        admitted = {
            "record_id": record_id,
            "native_value": native_value,
            "category": category,
            "sample_basis": sample_basis,
            "observed_at": _format_utc(observed_at),
            "confidence": numeric_confidence,
        }
        canonical = json.dumps(
            admitted, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        evidence_suffix = hashlib.sha256(
            f"{self.definition.source_id}:{record_id}:{digest}".encode()
        ).hexdigest()[:24]
        return (
            {
                "schema_version": "1.0.0",
                "kind": "source_evidence",
                "evidence_id": f"ev_{self.definition.source_id}-{evidence_suffix}",
                "source": {
                    "source_id": self.definition.source_id,
                    "name": self.definition.source_name,
                    "authority_type": "licensed_data_provider",
                    "jurisdiction": jurisdiction,
                    "locator": self.definition.stable_url,
                    "reuse_basis": self.definition.reuse_basis,
                    "license": self.definition.license,
                },
                "subject": {
                    "kind": "phone_number",
                    "canonical_e164": canonical_e164,
                },
                "observation": {
                    "evidence_class": "licensed_reputation_observation",
                    "claim_type": "reputation_status",
                    "value": category,
                    "publication_status": "public",
                    "verification_status": "verified",
                    "confidence": numeric_confidence,
                    "reason_codes": [_REASON_CODES[category]],
                    "limitations": list(_LIMITATIONS),
                    "reputation": {
                        "category": category,
                        "source_native_value": native_value,
                        "sample_basis": sample_basis,
                    },
                },
                "freshness": {
                    "retrieved_at": _format_utc(checked_at),
                    "source_published_at": _format_utc(observed_at),
                    "valid_until": _format_utc(valid_until),
                    "status": "stale" if is_stale else "current",
                    "max_age_seconds": self.definition.freshness_max_age_seconds,
                },
                "provenance": {
                    "source_document_id": f"{self.definition.source_id}-licensed-feed",
                    "source_record_id": record_id,
                    "transformation_version": "1.0.0",
                    "content_digest": f"sha256:{digest}",
                },
            },
            is_stale,
        )

    def _gap_result(
        self,
        status: AdapterStatus,
        *,
        jurisdiction: str,
        checked_at: datetime,
        code: str,
        message: str,
        retryable: bool,
    ) -> AdapterResult:
        return AdapterResult(
            declaration=self.declaration,
            jurisdiction=jurisdiction,
            status=status,
            checked_at=checked_at,
            gaps=(self._gap(code, message, retryable=retryable),),
        )

    def _gap(self, code: str, message: str, *, retryable: bool) -> EvidenceGap:
        suffix = hashlib.sha256(
            f"{self.definition.source_id}:{code}".encode()
        ).hexdigest()[:12]
        return EvidenceGap(
            gap_id=f"gap_{self.definition.source_id[:32]}-{suffix}",
            source_id=self.definition.source_id,
            code=code,
            message=message,
            retryable=retryable,
        )


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise FeedResponseError("Provider observation time is missing.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FeedResponseError("Provider observation time is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FeedResponseError("Provider observation time requires a timezone.")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
