"""Cross-registry activation and source-only scheduling for reputation feeds."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from callersignal.adapters.base import AdapterResult
from callersignal.reputation.feed import (
    AuthorizedReputationAdapter,
    FeedConfigurationError,
    ReputationFeedDefinition,
    ReputationFeedTransport,
)

_ALLOWED_INTAKE_FIELDS = {
    "reputation_status",
    "source_native_value",
    "sample_basis",
    "confidence",
    "observed_at",
    "source_record_id",
}
_REQUIRED_INTAKE_FIELDS = _ALLOWED_INTAKE_FIELDS
_PASSING_GATES = {"passed", "not_applicable"}
_REQUIRED_GATES = {
    "robots_access",
    "reuse_permission",
    "copyright",
    "database_rights",
    "privacy",
    "takedown",
    "provenance",
}


@dataclass(frozen=True, slots=True)
class SourceActivation:
    source_id: str
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReputationFeedActivation:
    indexed_count: int
    licensable_count: int
    enabled_count: int
    adapters: tuple[AuthorizedReputationAdapter, ...]
    sources: tuple[SourceActivation, ...]


def activate_reputation_feeds(
    *,
    registry: Mapping[str, Any],
    service_index: Mapping[str, Any],
    environment: Mapping[str, str],
    transport_factory: Callable[[ReputationFeedDefinition], ReputationFeedTransport],
) -> ReputationFeedActivation:
    """Activate only the exact intersection of reviewed index and registry state."""
    services = tuple(service_index.get("services", ()))
    registered = {
        item.get("source_id"): item for item in registry.get("sources", ())
    }
    adapters: list[AuthorizedReputationAdapter] = []
    states: list[SourceActivation] = []
    licensable = 0
    for service in services:
        source_id = str(service.get("service_id") or "")
        rights = service.get("rights", {})
        integration = service.get("integration", {})
        activation = service.get("activation", {})
        if rights.get("reuse_status") in {"licensed_access_available", "enabled"}:
            licensable += 1
        if rights.get("reuse_status") != "enabled":
            states.append(SourceActivation(source_id, "disabled", "rights_not_enabled"))
            continue
        if (
            integration.get("status") != "enabled"
            or activation.get("decision") != "enabled"
            or activation.get("blocking_gates")
        ):
            states.append(SourceActivation(source_id, "disabled", "integration_not_enabled"))
            continue
        source = registered.get(source_id)
        if not isinstance(source, Mapping):
            states.append(SourceActivation(source_id, "disabled", "registry_entry_missing"))
            continue
        try:
            definition = _definition_from_records(source, service)
        except (FeedConfigurationError, KeyError, TypeError, ValueError):
            states.append(SourceActivation(source_id, "disabled", "registry_contract_invalid"))
            continue
        credential = environment.get(definition.credential_env, "")
        if not credential.strip():
            states.append(SourceActivation(source_id, "disabled", "credentials_unavailable"))
            continue
        try:
            transport = transport_factory(definition)
            adapter = AuthorizedReputationAdapter(
                definition,
                credential=credential,
                transport=transport,
            )
        except Exception:
            states.append(SourceActivation(source_id, "disabled", "adapter_unavailable"))
            continue
        adapters.append(adapter)
        states.append(SourceActivation(source_id, "enabled", "all_activation_gates_passed"))
    return ReputationFeedActivation(
        indexed_count=len(services),
        licensable_count=licensable,
        enabled_count=len(adapters),
        adapters=tuple(adapters),
        sources=tuple(states),
    )


def _definition_from_records(
    source: Mapping[str, Any],
    service: Mapping[str, Any],
) -> ReputationFeedDefinition:
    if source.get("source_id") != service.get("service_id"):
        raise FeedConfigurationError("Registry and discovery source identifiers differ.")
    if (
        source.get("status") != "enabled"
        or source.get("source_type") != "licensed_reputation"
        or source.get("adapter_enabled") is not True
        or source.get("risk_capable") is not True
    ):
        raise FeedConfigurationError("Registry source is not an enabled reputation source.")
    if "licensed_reputation_observation" not in source.get("evidence_classes", ()):
        raise FeedConfigurationError("Registry source lacks the aggregate evidence class.")
    gates = source.get("gates", {})
    if set(gates) != _REQUIRED_GATES or any(
        gate.get("status") not in _PASSING_GATES for gate in gates.values()
    ):
        raise FeedConfigurationError("Registry source has an incomplete activation gate.")
    intake = source.get("intake", {})
    permitted_fields = set(intake.get("permitted_fields", ()))
    if (
        permitted_fields != _REQUIRED_INTAKE_FIELDS
        or intake.get("personal_data_allowed") is not False
        or intake.get("free_text_allowed") is not False
        or intake.get("outage_behavior") != "typed_gap"
    ):
        raise FeedConfigurationError("Registry intake is not aggregate-only and fail-closed.")
    service_integration = service.get("integration", {})
    permission_reference = service.get("rights", {}).get("permission_reference")
    if (
        service_integration.get("channel") not in {"licensed_api", "partner_feed"}
        or service_integration.get("requires_contract") is not True
        or service_integration.get("requires_credentials") is not True
        or not service_integration.get("permitted_fields")
        or not isinstance(permission_reference, str)
        or not permission_reference.startswith("https://")
    ):
        raise FeedConfigurationError("Discovery index lacks a licensed credentialed route.")
    feed = source.get("feed")
    if not isinstance(feed, Mapping):
        raise FeedConfigurationError("Registry source lacks a feed contract.")
    native_map = feed.get("native_category_map")
    if not isinstance(native_map, Mapping):
        raise FeedConfigurationError("Registry source lacks reviewed status mappings.")
    if feed.get("transport") != "licensed_https_json_api":
        raise FeedConfigurationError("Registry source does not use the bounded feed transport.")
    return ReputationFeedDefinition(
        source_id=str(source["source_id"]),
        adapter_id=str(source["adapter_id"]),
        source_name=str(source["name"]),
        stable_url=str(source["stable_url"]),
        endpoint=str(feed["endpoint"]),
        jurisdictions=tuple(source["jurisdictions"]),
        reuse_basis=str(source["reuse"]["basis"]),
        license=str(source["reuse"]["license"]),
        credential_env=str(feed["credential_env"]),
        requests_per_window=_required_integer(feed, "requests_per_window"),
        window_seconds=_required_integer(feed, "window_seconds"),
        request_timeout_seconds=_required_integer(feed, "request_timeout_seconds"),
        max_response_bytes=_required_integer(feed, "max_response_bytes"),
        schedule_seconds=_required_integer(feed, "schedule_seconds"),
        freshness_max_age_seconds=_required_integer(
            intake, "freshness_max_age_seconds"
        ),
        native_category_map=tuple(
            (str(native), str(category)) for native, category in native_map.items()
        ),
    )


def _required_integer(record: Mapping[str, Any], field: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise FeedConfigurationError(f"Feed field {field} must be an integer.")
    return value


class ReputationRefreshScheduler:
    """Refresh due sources without retaining lookup subjects or request history."""

    def __init__(self, adapters: Iterable[AuthorizedReputationAdapter]) -> None:
        self._adapters = tuple(adapters)
        self._last_attempts: dict[str, datetime] = {}

    @property
    def last_attempts(self) -> dict[str, datetime]:
        return dict(self._last_attempts)

    def run_due(
        self,
        phone_numbers: Iterable[Mapping[str, Any]],
        *,
        checked_at: datetime,
    ) -> tuple[AdapterResult, ...]:
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("Scheduler time must be timezone-aware.")
        transient_subjects = tuple(phone_numbers)
        results: list[AdapterResult] = []
        for adapter in self._adapters:
            source_id = adapter.declaration.source_id
            previous = self._last_attempts.get(source_id)
            if previous is not None and checked_at < previous + timedelta(
                seconds=adapter.schedule_seconds
            ):
                continue
            self._last_attempts[source_id] = checked_at
            results.extend(
                adapter.lookup(phone_number, checked_at=checked_at)
                for phone_number in transient_subjects
            )
        return tuple(results)
