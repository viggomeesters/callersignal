"""Build a privacy-minimized FCC unwanted-call complaint aggregate."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from callersignal.numbering import normalize_phone_number

JSONFetcher = Callable[[str, dict[str, str]], Any]

_SOURCE_ID = "fcc_unwanted_call_complaints"
_DATASET_ID = "vakf-fz8e"
_DATASET_NAME = "Consumer Complaints Data - Unwanted Calls"
_LICENSE = "Public Domain U.S. Government"
_LICENSE_URL = "https://www.usa.gov/government-works"
_ATTRIBUTION = (
    "Federal Communications Commission: Consumer Inquiries and Complaints Division"
)
_PERMITTED_FIELDS = (
    "caller_id_number",
    "issue_date",
    "type_of_call_or_messge",
)
_FORBIDDEN_FIELDS = (
    "id",
    "issue_time",
    "issue_type",
    "method",
    "issue",
    "advertiser_business_phone_number",
    "state",
    "zip",
    "location_1",
)
_EXPECTED_COLUMNS = {
    "id": "number",
    "issue_date": "calendar_date",
    "issue_time": "text",
    "issue_type": "text",
    "method": "text",
    "issue": "text",
    "caller_id_number": "text",
    "type_of_call_or_messge": "text",
    "advertiser_business_phone_number": "text",
    "state": "text",
    "zip": "text",
    "location_1": "point",
}
_ROW_FIELDS = {
    "caller_id_number",
    "type_of_call_or_messge",
    "observation_count",
    "first_issue_date",
    "last_issue_date",
}
_CATEGORY_VALUES = {"nuisance", "robocall"}
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")


class FCCCatalogBuildError(ValueError):
    """Raised when FCC source data cannot safely replace the current catalogue."""


class FCCCatalogReadError(ValueError):
    """Raised when a generated FCC catalogue violates its read contract."""


@dataclass(frozen=True)
class FCCCatalogBuildSummary:
    """Public-safe coverage facts emitted after a successful atomic build."""

    output_path: Path
    generated_at: str
    source_updated_at: str
    window_start: str
    window_end: str
    page_count: int
    grouped_row_count: int
    unique_number_count: int
    source_observation_count: int
    indexed_observation_count: int
    rejected_number_row_count: int
    rejected_observation_count: int
    category_counts: dict[str, int]
    first_issue_date: str
    last_issue_date: str
    source_digest: str


@dataclass(frozen=True)
class FCCCatalogMetadata:
    """Validated public-safe metadata from one immutable FCC catalogue."""

    generated_at: str
    source_updated_at: str
    window_start: str
    window_end: str
    unique_number_count: int
    source_observation_count: int
    indexed_observation_count: int
    rejected_observation_count: int
    category_counts: dict[str, int]
    first_issue_date: str
    last_issue_date: str
    source_digest: str


@dataclass(frozen=True)
class FCCCatalogRecord:
    """One HMAC-selected complaint aggregate without a plaintext number."""

    nuisance_count: int
    robocall_count: int
    observation_count: int
    first_issue_date: str
    last_issue_date: str


def lookup_fcc_catalog(
    catalog_path: Path,
    canonical_e164: str,
    *,
    lookup_key: bytes,
) -> tuple[FCCCatalogMetadata, FCCCatalogRecord | None]:
    """Read one canonical US number from an immutable HMAC-keyed catalogue."""
    if not isinstance(lookup_key, bytes) or len(lookup_key) < 32:
        raise FCCCatalogReadError("FCC catalogue lookup key is missing or too short")
    if re.fullmatch(r"\+1[0-9]{10}", canonical_e164) is None:
        raise FCCCatalogReadError("FCC catalogue lookup requires canonical US E.164")
    path = catalog_path.resolve()
    if not path.is_file():
        raise FCCCatalogReadError("Generated FCC catalogue is unavailable")
    locator = f"file:{quote(str(path))}?mode=ro&immutable=1"
    keyed_number = hmac.new(
        lookup_key, canonical_e164.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    try:
        with sqlite3.connect(locator, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            metadata = _read_catalog_metadata(connection, lookup_key=lookup_key)
            row = connection.execute(
                """
                SELECT nuisance_count, robocall_count, observation_count,
                       first_issue_date, last_issue_date
                  FROM complaint_aggregates
                 WHERE lookup_key = ?
                """,
                (keyed_number,),
            ).fetchone()
    except sqlite3.Error as error:
        raise FCCCatalogReadError(f"Generated FCC catalogue is invalid: {error}") from error
    record = _validated_catalog_record(dict(row)) if row is not None else None
    return metadata, record


def build_fcc_catalog(
    manifest_path: Path,
    output_path: Path,
    *,
    lookup_key: bytes,
    generated_at: datetime | None = None,
    fetch_json: JSONFetcher | None = None,
) -> FCCCatalogBuildSummary:
    """Validate FCC metadata and atomically build an HMAC-keyed SQLite aggregate."""
    if not isinstance(lookup_key, bytes) or len(lookup_key) < 32:
        raise FCCCatalogBuildError("FCC catalogue lookup key must contain at least 32 bytes")
    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise FCCCatalogBuildError("FCC catalogue generated time must be timezone-aware")
    now = now.astimezone(UTC)
    manifest = _load_manifest(manifest_path)
    fetcher = fetch_json or _fetch_json

    metadata_payload = _fetch(fetcher, manifest["urls"]["metadata"], {})
    source_updated_at = _validate_source_metadata(metadata_payload, manifest, now)
    window_start, window_end = _rolling_window(now.date(), manifest["query"])

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _temporary_database_path(output_path)
    try:
        summary = _build_database(
            manifest,
            temporary_path,
            output_path=output_path,
            lookup_key=lookup_key,
            generated_at=now,
            source_updated_at=source_updated_at,
            window_start=window_start,
            window_end=window_end,
            fetcher=fetcher,
        )
        metadata_readback = _fetch(fetcher, manifest["urls"]["metadata"], {})
        readback_updated_at = _validate_source_metadata(
            metadata_readback, manifest, now
        )
        if readback_updated_at != source_updated_at:
            raise FCCCatalogBuildError(
                "FCC dataset changed during pagination; refusing a mixed snapshot"
            )
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return summary


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FCCCatalogBuildError(f"Cannot read FCC manifest: {error}") from error
    if (
        manifest.get("schema_version") != "1.0.0"
        or manifest.get("kind") != "fcc_unwanted_call_complaint_manifest"
        or manifest.get("source_id") != _SOURCE_ID
        or manifest.get("dataset_id") != _DATASET_ID
        or manifest.get("publisher") != "Federal Communications Commission"
    ):
        raise FCCCatalogBuildError("Unsupported FCC manifest identity")
    urls = manifest.get("urls")
    license_record = manifest.get("license")
    fields = manifest.get("fields")
    query = manifest.get("query")
    semantics = manifest.get("semantics")
    storage = manifest.get("storage")
    freshness = manifest.get("freshness")
    category_map = manifest.get("category_map")
    if not all(
        isinstance(item, Mapping)
        for item in (urls, license_record, fields, query, semantics, storage, freshness)
    ) or not isinstance(category_map, Mapping):
        raise FCCCatalogBuildError("FCC manifest sections are incomplete")
    if set(urls) != {"dataset", "metadata", "api", "publisher"} or any(
        not isinstance(value, str) or not value.startswith("https://")
        for value in urls.values()
    ):
        raise FCCCatalogBuildError("FCC manifest source locations must use exact HTTPS routes")
    if not str(urls["metadata"]).endswith(f"/api/views/{_DATASET_ID}") or not str(
        urls["api"]
    ).endswith(f"/resource/{_DATASET_ID}.json"):
        raise FCCCatalogBuildError("FCC manifest dataset routes do not match its dataset ID")
    if license_record.get("name") != _LICENSE or license_record.get(
        "terms_url"
    ) != _LICENSE_URL or license_record.get("attribution") != _ATTRIBUTION:
        raise FCCCatalogBuildError("FCC manifest license metadata is unsupported")
    if tuple(fields.get("permitted", ())) != _PERMITTED_FIELDS or set(
        fields.get("forbidden", ())
    ) != set(_FORBIDDEN_FIELDS):
        raise FCCCatalogBuildError("FCC manifest field boundary is unsupported")
    expected_select = (
        "caller_id_number",
        "type_of_call_or_messge",
        "count(*) as observation_count",
        "min(issue_date) as first_issue_date",
        "max(issue_date) as last_issue_date",
    )
    if (
        query.get("rolling_window_years") != 5
        or isinstance(query.get("page_size"), bool)
        or not isinstance(query.get("page_size"), int)
        or not 100 <= query["page_size"] <= 5000
        or tuple(query.get("select", ())) != expected_select
        or tuple(query.get("group_by", ()))
        != ("caller_id_number", "type_of_call_or_messge")
        or tuple(query.get("order_by", ()))
        != ("caller_id_number ASC", "type_of_call_or_messge ASC")
    ):
        raise FCCCatalogBuildError("FCC manifest query contract is unsupported")
    if not category_map or set(category_map.values()) != _CATEGORY_VALUES or any(
        not isinstance(key, str) or not key.strip() for key in category_map
    ):
        raise FCCCatalogBuildError("FCC manifest category map is unsupported")
    if (
        semantics.get("verification_status") != "consumer_selected_unverified"
        or semantics.get("official_warning_allowed") is not False
        or semantics.get("caller_identity_allowed") is not False
        or semantics.get("safe_verdict_allowed") is not False
        or semantics.get("single_source_elevation_allowed") is not False
        or semantics.get("spoofing_warning_required") is not True
    ):
        raise FCCCatalogBuildError("FCC manifest safety semantics are unsupported")
    if (
        storage.get("plaintext_phone_numbers") != "forbidden"
        or storage.get("raw_rows") != "forbidden"
        or storage.get("free_text") != "forbidden"
        or storage.get("lookup_key") != "hmac_sha256_deployment_secret"
        or storage.get("replacement") != "atomic_after_complete_validation"
    ):
        raise FCCCatalogBuildError("FCC manifest storage boundary is unsupported")
    maximum_age = freshness.get("metadata_max_age_seconds")
    if isinstance(maximum_age, bool) or not isinstance(maximum_age, int) or maximum_age < 1:
        raise FCCCatalogBuildError("FCC manifest freshness contract is invalid")
    if freshness.get("outage_behavior") != "typed_gap":
        raise FCCCatalogBuildError("FCC manifest outage behavior is unsupported")
    return manifest


def _validate_source_metadata(
    payload: Any,
    manifest: Mapping[str, Any],
    generated_at: datetime,
) -> datetime:
    if not isinstance(payload, Mapping):
        raise FCCCatalogBuildError("FCC metadata response is not an object")
    license_record = payload.get("license")
    if (
        payload.get("id") != _DATASET_ID
        or payload.get("name") != _DATASET_NAME
        or payload.get("attribution") != _ATTRIBUTION
    ):
        raise FCCCatalogBuildError("FCC metadata identity drifted")
    if not isinstance(license_record, Mapping) or license_record.get("name") != _LICENSE or (
        license_record.get("termsLink") != _LICENSE_URL
    ):
        raise FCCCatalogBuildError("FCC metadata license drifted")
    description = payload.get("description")
    if not isinstance(description, str) or "does not verify" not in description.casefold():
        raise FCCCatalogBuildError("FCC metadata verification limitation drifted")
    columns = payload.get("columns")
    if not isinstance(columns, list):
        raise FCCCatalogBuildError("FCC metadata schema is unavailable")
    actual_columns: dict[str, str] = {}
    for column in columns:
        if not isinstance(column, Mapping):
            raise FCCCatalogBuildError("FCC metadata schema contains an invalid column")
        field_name = column.get("fieldName")
        data_type = column.get("dataTypeName")
        if not isinstance(field_name, str) or not isinstance(data_type, str):
            raise FCCCatalogBuildError("FCC metadata schema contains an invalid column")
        if field_name in actual_columns:
            raise FCCCatalogBuildError("FCC metadata schema contains a duplicate column")
        actual_columns[field_name] = data_type
    if actual_columns != _EXPECTED_COLUMNS:
        raise FCCCatalogBuildError("FCC metadata schema drifted")
    updated_epoch = payload.get("rowsUpdatedAt")
    if isinstance(updated_epoch, bool) or not isinstance(updated_epoch, (int, float)):
        raise FCCCatalogBuildError("FCC metadata source update is invalid")
    try:
        updated_at = datetime.fromtimestamp(updated_epoch, tz=UTC)
    except (OSError, OverflowError, ValueError) as error:
        raise FCCCatalogBuildError("FCC metadata source update is invalid") from error
    age_seconds = (generated_at - updated_at).total_seconds()
    if age_seconds < -300:
        raise FCCCatalogBuildError("FCC metadata source update is in the future")
    maximum_age = int(manifest["freshness"]["metadata_max_age_seconds"])
    if age_seconds > maximum_age:
        raise FCCCatalogBuildError("FCC metadata is stale")
    return updated_at


def _rolling_window(end: date, query: Mapping[str, Any]) -> tuple[date, date]:
    years = int(query["rolling_window_years"])
    try:
        start = end.replace(year=end.year - years)
    except ValueError:
        start = end.replace(year=end.year - years, day=28)
    return start, end


def _build_database(
    manifest: Mapping[str, Any],
    database_path: Path,
    *,
    output_path: Path,
    lookup_key: bytes,
    generated_at: datetime,
    source_updated_at: datetime,
    window_start: date,
    window_end: date,
    fetcher: JSONFetcher,
) -> FCCCatalogBuildSummary:
    page_size = int(manifest["query"]["page_size"])
    query_params = _query_params(manifest, window_start, window_end)
    category_map = dict(manifest["category_map"])
    grouped_row_count = 0
    source_observation_count = 0
    indexed_observation_count = 0
    rejected_number_row_count = 0
    rejected_observation_count = 0
    category_counts: Counter[str] = Counter()
    first_issue_date: date | None = None
    last_issue_date: date | None = None
    page_count = 0
    seen_groups: set[bytes] = set()
    projection_digest = hmac.new(lookup_key, b"fcc-projection-v1\x00", hashlib.sha256)

    try:
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = OFF;
                PRAGMA synchronous = OFF;
                PRAGMA user_version = 1;
                CREATE TABLE catalog_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                ) WITHOUT ROWID;
                CREATE TABLE complaint_aggregates (
                    lookup_key TEXT PRIMARY KEY CHECK(length(lookup_key) = 64),
                    nuisance_count INTEGER NOT NULL CHECK(nuisance_count >= 0),
                    robocall_count INTEGER NOT NULL CHECK(robocall_count >= 0),
                    observation_count INTEGER NOT NULL CHECK(observation_count > 0),
                    first_issue_date TEXT NOT NULL CHECK(length(first_issue_date) = 10),
                    last_issue_date TEXT NOT NULL CHECK(length(last_issue_date) = 10)
                ) WITHOUT ROWID;
                """
            )
            offset = 0
            while True:
                params = dict(query_params)
                params["$limit"] = str(page_size)
                params["$offset"] = str(offset)
                page = _fetch(fetcher, str(manifest["urls"]["api"]), params)
                if not isinstance(page, list):
                    raise FCCCatalogBuildError("FCC aggregate page is not an array")
                if len(page) > page_size:
                    raise FCCCatalogBuildError("FCC aggregate page exceeds the declared limit")
                page_count += 1
                for row in page:
                    grouped_row_count += 1
                    projected = _project_row(
                        row,
                        category_map=category_map,
                        lookup_key=lookup_key,
                        window_start=window_start,
                        window_end=window_end,
                    )
                    group_digest = projected["group_digest"]
                    if group_digest in seen_groups:
                        raise FCCCatalogBuildError(
                            "FCC pagination returned a duplicate grouped row"
                        )
                    seen_groups.add(group_digest)
                    count = projected["observation_count"]
                    source_observation_count += count
                    if projected["lookup_key"] is None:
                        rejected_number_row_count += 1
                        rejected_observation_count += count
                        continue
                    category = projected["category"]
                    first_date = projected["first_issue_date"]
                    last_date = projected["last_issue_date"]
                    nuisance_count = count if category == "nuisance" else 0
                    robocall_count = count if category == "robocall" else 0
                    connection.execute(
                        """
                        INSERT INTO complaint_aggregates (
                            lookup_key, nuisance_count, robocall_count,
                            observation_count, first_issue_date, last_issue_date
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(lookup_key) DO UPDATE SET
                            nuisance_count = nuisance_count + excluded.nuisance_count,
                            robocall_count = robocall_count + excluded.robocall_count,
                            observation_count = observation_count + excluded.observation_count,
                            first_issue_date = min(first_issue_date, excluded.first_issue_date),
                            last_issue_date = max(last_issue_date, excluded.last_issue_date)
                        """,
                        (
                            projected["lookup_key"],
                            nuisance_count,
                            robocall_count,
                            count,
                            first_date.isoformat(),
                            last_date.isoformat(),
                        ),
                    )
                    digest_row = json.dumps(
                        [
                            projected["lookup_key"],
                            category,
                            count,
                            first_date.isoformat(),
                            last_date.isoformat(),
                        ],
                        separators=(",", ":"),
                    ).encode("utf-8")
                    projection_digest.update(digest_row)
                    projection_digest.update(b"\n")
                    indexed_observation_count += count
                    category_counts[category] += count
                    first_issue_date = (
                        first_date
                        if first_issue_date is None or first_date < first_issue_date
                        else first_issue_date
                    )
                    last_issue_date = (
                        last_date
                        if last_issue_date is None or last_date > last_issue_date
                        else last_issue_date
                    )
                if len(page) < page_size:
                    break
                offset += page_size

            unique_number_count = int(
                connection.execute("SELECT count(*) FROM complaint_aggregates").fetchone()[0]
            )
            if unique_number_count == 0 or indexed_observation_count == 0:
                raise FCCCatalogBuildError("FCC aggregate contains zero valid US numbers")
            if source_observation_count != (
                indexed_observation_count + rejected_observation_count
            ):
                raise FCCCatalogBuildError("FCC aggregate observation accounting is invalid")
            source_digest = projection_digest.hexdigest()
            summary = FCCCatalogBuildSummary(
                output_path=output_path,
                generated_at=_timestamp(generated_at),
                source_updated_at=_timestamp(source_updated_at),
                window_start=window_start.isoformat(),
                window_end=window_end.isoformat(),
                page_count=page_count,
                grouped_row_count=grouped_row_count,
                unique_number_count=unique_number_count,
                source_observation_count=source_observation_count,
                indexed_observation_count=indexed_observation_count,
                rejected_number_row_count=rejected_number_row_count,
                rejected_observation_count=rejected_observation_count,
                category_counts={
                    category: category_counts.get(category, 0)
                    for category in sorted(_CATEGORY_VALUES)
                },
                first_issue_date=first_issue_date.isoformat(),
                last_issue_date=last_issue_date.isoformat(),
                source_digest=source_digest,
            )
            metadata = _catalog_metadata(manifest, summary, lookup_key=lookup_key)
            connection.executemany(
                "INSERT INTO catalog_metadata (key, value) VALUES (?, ?)",
                metadata.items(),
            )
            connection.commit()
    except sqlite3.Error as error:
        raise FCCCatalogBuildError(f"FCC aggregate database build failed: {error}") from error
    return summary


def _query_params(
    manifest: Mapping[str, Any], window_start: date, window_end: date
) -> dict[str, str]:
    query = manifest["query"]
    categories = tuple(manifest["category_map"])
    category_literals = ",".join(f"'{value.replace("'", "''")}'" for value in categories)
    return {
        "$select": ",".join(query["select"]),
        "$where": (
            "caller_id_number is not null and "
            f"issue_date between '{window_start.isoformat()}T00:00:00.000' and "
            f"'{window_end.isoformat()}T23:59:59.999' and "
            f"type_of_call_or_messge in ({category_literals})"
        ),
        "$group": ",".join(query["group_by"]),
        "$order": ",".join(query["order_by"]),
    }


def _project_row(
    row: Any,
    *,
    category_map: Mapping[str, str],
    lookup_key: bytes,
    window_start: date,
    window_end: date,
) -> dict[str, Any]:
    if not isinstance(row, Mapping) or set(row) != _ROW_FIELDS:
        raise FCCCatalogBuildError("FCC aggregate row schema drifted")
    if any(not isinstance(row[field], str) for field in _ROW_FIELDS):
        raise FCCCatalogBuildError("FCC aggregate row contains a non-text value")
    native_category = row["type_of_call_or_messge"]
    category = category_map.get(native_category)
    if category not in _CATEGORY_VALUES:
        raise FCCCatalogBuildError("FCC aggregate row category drifted")
    count_value = row["observation_count"]
    if not count_value.isdigit() or not 0 < int(count_value) <= 9_223_372_036_854_775_807:
        raise FCCCatalogBuildError("FCC aggregate row count is invalid")
    count = int(count_value)
    first_date = _source_date(row["first_issue_date"])
    last_date = _source_date(row["last_issue_date"])
    if (
        first_date is None
        or last_date is None
        or first_date > last_date
        or first_date < window_start
        or last_date > window_end
    ):
        raise FCCCatalogBuildError("FCC aggregate row date is outside the query window")
    source_number = row["caller_id_number"]
    group_digest = hmac.new(
        lookup_key,
        json.dumps(
            [source_number, native_category], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    canonical = _canonical_us_number(source_number)
    keyed_number = (
        hmac.new(lookup_key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        if canonical is not None
        else None
    )
    return {
        "lookup_key": keyed_number,
        "group_digest": group_digest,
        "category": category,
        "observation_count": count,
        "first_issue_date": first_date,
        "last_issue_date": last_date,
    }


def _canonical_us_number(value: str) -> str | None:
    try:
        normalized = normalize_phone_number(value, origin_region="US")
    except (TypeError, ValueError):
        return None
    canonical = normalized.get("canonical", {})
    if (
        normalized.get("interpretation", {}).get("status") != "valid"
        or canonical.get("region") != "US"
        or not isinstance(canonical.get("e164"), str)
        or not canonical["e164"].startswith("+1")
    ):
        return None
    return str(canonical["e164"])


def _source_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _catalog_metadata(
    manifest: Mapping[str, Any],
    summary: FCCCatalogBuildSummary,
    *,
    lookup_key: bytes,
) -> dict[str, str]:
    metadata = {
        "schema_version": "1.0.0",
        "source_id": _SOURCE_ID,
        "dataset_id": _DATASET_ID,
        "dataset_url": str(manifest["urls"]["dataset"]),
        "metadata_url": str(manifest["urls"]["metadata"]),
        "api_url": str(manifest["urls"]["api"]),
        "license": _LICENSE,
        "license_url": _LICENSE_URL,
        "attribution": _ATTRIBUTION,
        "generated_at": summary.generated_at,
        "source_updated_at": summary.source_updated_at,
        "window_start": summary.window_start,
        "window_end": summary.window_end,
        "page_count": str(summary.page_count),
        "grouped_row_count": str(summary.grouped_row_count),
        "unique_number_count": str(summary.unique_number_count),
        "source_observation_count": str(summary.source_observation_count),
        "indexed_observation_count": str(summary.indexed_observation_count),
        "rejected_number_row_count": str(summary.rejected_number_row_count),
        "rejected_observation_count": str(summary.rejected_observation_count),
        "category_counts": json.dumps(summary.category_counts, separators=(",", ":")),
        "first_issue_date": summary.first_issue_date,
        "last_issue_date": summary.last_issue_date,
        "source_digest": summary.source_digest,
        "verification_status": "consumer_selected_unverified",
        "lookup_key_algorithm": "HMAC-SHA256",
        "lookup_key_verifier": hmac.new(
            lookup_key,
            b"callersignal-fcc-catalog-key-v1",
            hashlib.sha256,
        ).hexdigest(),
    }
    metadata["metadata_authenticator"] = hmac.new(
        lookup_key,
        json.dumps(
            sorted(metadata.items()),
            separators=(",", ":"),
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return metadata


def _read_catalog_metadata(
    connection: sqlite3.Connection,
    *,
    lookup_key: bytes,
) -> FCCCatalogMetadata:
    expected_columns = {
        "lookup_key",
        "nuisance_count",
        "robocall_count",
        "observation_count",
        "first_issue_date",
        "last_issue_date",
    }
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(complaint_aggregates)")
    }
    if columns != expected_columns:
        raise FCCCatalogReadError("Generated FCC catalogue has an unexpected schema")
    try:
        values = dict(connection.execute("SELECT key, value FROM catalog_metadata"))
    except sqlite3.Error as error:
        raise FCCCatalogReadError("Generated FCC catalogue metadata is unavailable") from error
    required = {
        "schema_version",
        "source_id",
        "dataset_id",
        "dataset_url",
        "metadata_url",
        "api_url",
        "license",
        "license_url",
        "attribution",
        "generated_at",
        "source_updated_at",
        "window_start",
        "window_end",
        "page_count",
        "grouped_row_count",
        "unique_number_count",
        "source_observation_count",
        "indexed_observation_count",
        "rejected_number_row_count",
        "rejected_observation_count",
        "category_counts",
        "first_issue_date",
        "last_issue_date",
        "source_digest",
        "verification_status",
        "lookup_key_algorithm",
        "lookup_key_verifier",
        "metadata_authenticator",
    }
    if set(values) != required:
        raise FCCCatalogReadError("Generated FCC catalogue metadata is incomplete")
    if (
        values["schema_version"] != "1.0.0"
        or values["source_id"] != _SOURCE_ID
        or values["dataset_id"] != _DATASET_ID
        or values["license"] != _LICENSE
        or values["license_url"] != _LICENSE_URL
        or values["attribution"] != _ATTRIBUTION
        or values["verification_status"] != "consumer_selected_unverified"
        or values["lookup_key_algorithm"] != "HMAC-SHA256"
    ):
        raise FCCCatalogReadError("Generated FCC catalogue identity is unsupported")
    expected_verifier = hmac.new(
        lookup_key,
        b"callersignal-fcc-catalog-key-v1",
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(values["lookup_key_verifier"], expected_verifier):
        raise FCCCatalogReadError("Generated FCC catalogue lookup key does not match")
    authenticated_values = {
        key: value for key, value in values.items() if key != "metadata_authenticator"
    }
    expected_authenticator = hmac.new(
        lookup_key,
        json.dumps(
            sorted(authenticated_values.items()),
            separators=(",", ":"),
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(
        values["metadata_authenticator"], expected_authenticator
    ):
        raise FCCCatalogReadError("Generated FCC catalogue metadata authentication failed")
    if not all(
        values[name].startswith("https://")
        for name in ("dataset_url", "metadata_url", "api_url")
    ):
        raise FCCCatalogReadError("Generated FCC catalogue source URLs are invalid")
    try:
        generated_at = _parse_utc_timestamp(values["generated_at"])
        source_updated_at = _parse_utc_timestamp(values["source_updated_at"])
        window_start = date.fromisoformat(values["window_start"])
        window_end = date.fromisoformat(values["window_end"])
        first_issue_date = date.fromisoformat(values["first_issue_date"])
        last_issue_date = date.fromisoformat(values["last_issue_date"])
        page_count = int(values["page_count"])
        grouped_row_count = int(values["grouped_row_count"])
        unique_number_count = int(values["unique_number_count"])
        source_observation_count = int(values["source_observation_count"])
        indexed_observation_count = int(values["indexed_observation_count"])
        rejected_number_row_count = int(values["rejected_number_row_count"])
        rejected_observation_count = int(values["rejected_observation_count"])
        category_counts = json.loads(values["category_counts"])
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise FCCCatalogReadError(
            "Generated FCC catalogue metadata values are invalid"
        ) from error
    if (
        generated_at < source_updated_at
        or window_start > window_end
        or not window_start <= first_issue_date <= last_issue_date <= window_end
        or page_count <= 0
        or grouped_row_count <= 0
        or unique_number_count <= 0
        or source_observation_count <= 0
        or indexed_observation_count <= 0
        or rejected_number_row_count < 0
        or rejected_observation_count < 0
        or source_observation_count
        != indexed_observation_count + rejected_observation_count
        or not isinstance(category_counts, dict)
        or set(category_counts) != _CATEGORY_VALUES
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in category_counts.values()
        )
        or sum(category_counts.values()) != indexed_observation_count
        or _DIGEST_PATTERN.fullmatch(values["source_digest"]) is None
    ):
        raise FCCCatalogReadError("Generated FCC catalogue metadata values are invalid")
    return FCCCatalogMetadata(
        generated_at=_timestamp(generated_at),
        source_updated_at=_timestamp(source_updated_at),
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        unique_number_count=unique_number_count,
        source_observation_count=source_observation_count,
        indexed_observation_count=indexed_observation_count,
        rejected_observation_count=rejected_observation_count,
        category_counts=dict(sorted(category_counts.items())),
        first_issue_date=first_issue_date.isoformat(),
        last_issue_date=last_issue_date.isoformat(),
        source_digest=values["source_digest"],
    )


def _validated_catalog_record(row: dict[str, Any]) -> FCCCatalogRecord:
    expected = {
        "nuisance_count",
        "robocall_count",
        "observation_count",
        "first_issue_date",
        "last_issue_date",
    }
    if set(row) != expected:
        raise FCCCatalogReadError("Generated FCC catalogue record schema is invalid")
    nuisance = row["nuisance_count"]
    robocall = row["robocall_count"]
    total = row["observation_count"]
    if (
        isinstance(nuisance, bool)
        or not isinstance(nuisance, int)
        or nuisance < 0
        or isinstance(robocall, bool)
        or not isinstance(robocall, int)
        or robocall < 0
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total <= 0
        or nuisance + robocall != total
    ):
        raise FCCCatalogReadError("Generated FCC catalogue record counts are invalid")
    try:
        first = date.fromisoformat(row["first_issue_date"])
        last = date.fromisoformat(row["last_issue_date"])
    except (TypeError, ValueError) as error:
        raise FCCCatalogReadError("Generated FCC catalogue record dates are invalid") from error
    if first > last:
        raise FCCCatalogReadError("Generated FCC catalogue record dates are invalid")
    return FCCCatalogRecord(
        nuisance_count=nuisance,
        robocall_count=robocall,
        observation_count=total,
        first_issue_date=first.isoformat(),
        last_issue_date=last.isoformat(),
    )


def _parse_utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _fetch(fetcher: JSONFetcher, url: str, params: dict[str, str]) -> Any:
    try:
        return fetcher(url, params)
    except FCCCatalogBuildError:
        raise
    except Exception as error:
        raise FCCCatalogBuildError("FCC source request failed closed") from error


def _fetch_json(url: str, params: dict[str, str]) -> Any:
    if not url.startswith("https://"):
        raise FCCCatalogBuildError("FCC source request requires HTTPS")
    target = f"{url}?{urlencode(params)}" if params else url
    request = urllib.request.Request(
        target,
        headers={"Accept": "application/json", "User-Agent": "CallerSignal/0.3"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            body = response.read(8 * 1024 * 1024 + 1)
    except (OSError, urllib.error.HTTPError) as error:
        raise FCCCatalogBuildError("FCC source request failed") from error
    if len(body) > 8 * 1024 * 1024:
        raise FCCCatalogBuildError("FCC source response exceeded the size limit")
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FCCCatalogBuildError("FCC source response is not valid JSON") from error


def _temporary_database_path(output_path: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(descriptor)
    path = Path(name)
    os.chmod(path, 0o600)
    return path


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_valid_source_digest(value: str) -> bool:
    """Return whether a persisted projection digest has the expected shape."""
    return _DIGEST_PATTERN.fullmatch(value) is not None
