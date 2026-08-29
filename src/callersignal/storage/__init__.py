"""Replaceable persistence port and deterministic local adapter."""

from callersignal.storage.local import LocalStore
from callersignal.storage.model import (
    AuditReceipt,
    EntityKind,
    OutboxMessage,
    PrivacyBoundaryError,
    RecordNotFound,
    StoredRecord,
    VersionConflict,
)
from callersignal.storage.ports import DataStore, StorageTransaction
from callersignal.storage.provider import ProviderGateError, StorageProviderConfig

__all__ = [
    "AuditReceipt",
    "DataStore",
    "EntityKind",
    "LocalStore",
    "OutboxMessage",
    "PrivacyBoundaryError",
    "ProviderGateError",
    "RecordNotFound",
    "StoredRecord",
    "StorageProviderConfig",
    "StorageTransaction",
    "VersionConflict",
]
