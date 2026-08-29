from __future__ import annotations

from datetime import UTC, datetime

import pytest

from callersignal.storage import (
    DataStore,
    LocalStore,
    ProviderGateError,
    StorageProviderConfig,
)


def test_local_adapter_conforms_to_replaceable_store_port() -> None:
    store = LocalStore(clock=lambda: datetime(2026, 8, 29, 10, tzinfo=UTC))

    assert isinstance(store, DataStore)


def test_provider_configuration_contains_a_secret_reference_not_a_secret() -> None:
    config = StorageProviderConfig.production_reference(
        provider="approved_relational_provider",
        credential_reference="CALLERSIGNAL_DATABASE_URL",
        approved_for_public_mutation=True,
    )

    assert config.credential_reference == "CALLERSIGNAL_DATABASE_URL"
    assert "postgres://" not in repr(config)
    config.require_public_mutation_ready()


def test_local_adapter_fails_the_public_mutation_provider_gate() -> None:
    config = StorageProviderConfig.local_proof()

    with pytest.raises(ProviderGateError, match="approved durable provider"):
        config.require_public_mutation_ready()
