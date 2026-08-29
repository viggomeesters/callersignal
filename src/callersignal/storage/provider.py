"""Secret-reference-only configuration for replaceable storage providers."""

from __future__ import annotations

import re
from dataclasses import dataclass


class ProviderGateError(RuntimeError):
    """Production persistence was requested without an approved adapter gate."""


@dataclass(frozen=True)
class StorageProviderConfig:
    provider: str
    credential_reference: str | None
    durable: bool
    approved_for_public_mutation: bool

    @classmethod
    def local_proof(cls) -> StorageProviderConfig:
        return cls(
            provider="local_memory",
            credential_reference=None,
            durable=False,
            approved_for_public_mutation=False,
        )

    @classmethod
    def production_reference(
        cls,
        *,
        provider: str,
        credential_reference: str,
        approved_for_public_mutation: bool,
    ) -> StorageProviderConfig:
        if re.fullmatch(r"[A-Z][A-Z0-9_]{7,80}", credential_reference) is None:
            raise ValueError("credential_reference must be an environment secret name")
        return cls(
            provider=provider,
            credential_reference=credential_reference,
            durable=True,
            approved_for_public_mutation=approved_for_public_mutation,
        )

    def require_public_mutation_ready(self) -> None:
        if (
            not self.durable
            or not self.credential_reference
            or not self.approved_for_public_mutation
        ):
            raise ProviderGateError(
                "public mutation requires an approved durable provider and secret reference"
            )
