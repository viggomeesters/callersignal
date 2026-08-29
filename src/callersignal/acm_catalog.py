"""Build a privacy-minimized SQLite read model from the official ACM register."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import urllib.request
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

EXPECTED_COLUMNS = (
    "id",
    "apl_code",
    "twn_aanvraagnummer",
    "twn_bestemming",
    "twn_datumbeschikking",
    "twn_datumeind",
    "twn_netnummer",
    "twn_nummerstatus",
    "twn_nummertm",
    "twn_nummervan",
    "twn_plaats",
    "twn_relatienaam",
    "datummutatie",
    "twn_relatieid",
    "twn_kvknummer",
    "twn_kvkvestigingsnummer",
)
_RANGE_PATTERN = re.compile(r"[0-9 .()-]+")


class CatalogBuildError(ValueError):
    """Raised when the source cannot safely replace the current catalogue."""


@dataclass(frozen=True)
class CatalogBuildSummary:
    """Non-sensitive coverage facts emitted after a successful atomic build."""

    output_path: Path
    row_count: int
    matchable_row_count: int
    status_counts: dict[str, int]
    destination_counts: dict[str, int]
    newest_mutation: str | None
    source_sha256: str


def build_acm_catalog(
    manifest_path: Path,
    output_path: Path,
    *,
    archive_path: Path | None = None,
) -> CatalogBuildSummary:
    """Validate and atomically project the declared ACM archive into SQLite."""
    manifest = _load_manifest(manifest_path)
    artifact = manifest["artifact"]
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="callersignal-acm-") as temporary:
        if archive_path is None:
            selected_archive = Path(temporary) / "source.zip"
            _download(str(artifact["download_url"]), selected_archive)
        else:
            selected_archive = archive_path.resolve()

        source_sha256 = _sha256_file(selected_archive)
        if source_sha256 != artifact["sha256"]:
            raise CatalogBuildError(
                f"ACM archive checksum mismatch: expected {artifact['sha256']}, "
                f"received {source_sha256}"
            )
        expected_archive_size = artifact.get("byte_size")
        if expected_archive_size is not None and selected_archive.stat().st_size != int(
            expected_archive_size
        ):
            raise CatalogBuildError("ACM archive size differs from the pinned manifest")

        temporary_db = _temporary_database_path(output_path)
        try:
            summary = _build_database(
                manifest,
                selected_archive,
                temporary_db,
                output_path=output_path,
                source_sha256=source_sha256,
            )
            os.replace(temporary_db, output_path)
        except Exception:
            temporary_db.unlink(missing_ok=True)
            raise
    return summary


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogBuildError(f"Cannot read ACM manifest: {error}") from error

    if manifest.get("schema_version") != "1.0.0" or manifest.get("kind") != (
        "acm_bulk_manifest"
    ):
        raise CatalogBuildError("Unsupported ACM manifest contract")
    source = manifest.get("source")
    artifact = manifest.get("artifact")
    required_source = {
        "source_id",
        "name",
        "registry_url",
        "dataset_url",
        "license",
        "license_url",
    }
    required_artifact = {
        "download_url",
        "sha256",
        "archive_member",
        "csv_encoding",
        "csv_delimiter",
        "expected_columns",
        "retrieved_at",
    }
    if not isinstance(source, dict) or not required_source <= set(source):
        raise CatalogBuildError("ACM manifest source metadata is incomplete")
    if not isinstance(artifact, dict) or not required_artifact <= set(artifact):
        raise CatalogBuildError("ACM manifest artifact metadata is incomplete")
    if source["source_id"] != "acm_number_register":
        raise CatalogBuildError("ACM manifest declares an unexpected source")
    declared_urls = (
        source["registry_url"],
        source["dataset_url"],
        source["license_url"],
        artifact["download_url"],
    )
    if any(not isinstance(url, str) or not url.startswith("https://") for url in declared_urls):
        raise CatalogBuildError("ACM manifest source locations must use HTTPS")
    if not re.fullmatch(r"[0-9a-f]{64}", str(artifact["sha256"])):
        raise CatalogBuildError("ACM manifest SHA-256 is invalid")
    if tuple(artifact["expected_columns"]) != EXPECTED_COLUMNS:
        raise CatalogBuildError("ACM manifest does not declare the exact supported CSV columns")
    if artifact["csv_delimiter"] != ";" or artifact["csv_encoding"] != "utf-8-sig":
        raise CatalogBuildError("ACM manifest declares unsupported CSV encoding or delimiter")
    try:
        datetime.fromisoformat(str(artifact["retrieved_at"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise CatalogBuildError("ACM manifest retrieval time is invalid") from error
    return manifest


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "CallerSignal/0.2"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            with destination.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
    except OSError as error:
        raise CatalogBuildError(f"Could not download the pinned ACM archive: {error}") from error


def _temporary_database_path(output_path: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(descriptor)
    return Path(name)


def _build_database(
    manifest: dict[str, Any],
    archive_path: Path,
    database_path: Path,
    *,
    output_path: Path,
    source_sha256: str,
) -> CatalogBuildSummary:
    artifact = manifest["artifact"]
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise CatalogBuildError(f"Malformed ACM ZIP archive: {error}") from error

    with archive:
        members = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
        if members != [artifact["archive_member"]]:
            raise CatalogBuildError("ACM archive must contain exactly the declared CSV member")
        info = archive.getinfo(artifact["archive_member"])
        expected_csv_size = artifact.get("csv_byte_size")
        if expected_csv_size is not None and info.file_size != int(expected_csv_size):
            raise CatalogBuildError("ACM CSV size differs from the pinned manifest")

        try:
            raw_csv = archive.open(info)
            text_csv = io.TextIOWrapper(raw_csv, encoding=artifact["csv_encoding"], newline="")
            reader = csv.DictReader(text_csv, delimiter=artifact["csv_delimiter"])
            if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
                raise CatalogBuildError("ACM CSV header drifted from the exact supported contract")
            return _ingest_rows(
                manifest,
                reader,
                database_path,
                output_path=output_path,
                source_sha256=source_sha256,
            )
        except UnicodeError as error:
            raise CatalogBuildError(f"ACM CSV encoding is invalid: {error}") from error


def _ingest_rows(
    manifest: dict[str, Any],
    rows: csv.DictReader,
    database_path: Path,
    *,
    output_path: Path,
    source_sha256: str,
) -> CatalogBuildSummary:
    status_counts: Counter[str] = Counter()
    destination_counts: Counter[str] = Counter()
    newest_mutation: str | None = None
    row_count = 0
    matchable_row_count = 0

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
                CREATE TABLE number_ranges (
                    source_record_id TEXT PRIMARY KEY,
                    national_from TEXT NOT NULL,
                    national_to TEXT NOT NULL,
                    e164_from INTEGER,
                    e164_to INTEGER,
                    destination TEXT NOT NULL,
                    number_type TEXT NOT NULL,
                    register_status TEXT NOT NULL,
                    source_changed_at TEXT,
                    source_row_sha256 TEXT NOT NULL
                        CHECK(length(source_row_sha256) = 64),
                    CHECK((e164_from IS NULL) = (e164_to IS NULL)),
                    CHECK(e164_from IS NULL OR e164_from <= e164_to)
                ) WITHOUT ROWID;
                """
            )
            for source_row in rows:
                projection = _project_row(source_row)
                connection.execute(
                    """
                    INSERT INTO number_ranges (
                        source_record_id, national_from, national_to, e164_from,
                        e164_to, destination, number_type, register_status,
                        source_changed_at, source_row_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    projection,
                )
                row_count += 1
                if projection[3] is not None:
                    matchable_row_count += 1
                destination_counts[projection[5]] += 1
                status_counts[projection[7]] += 1
                changed_at = projection[8]
                if changed_at is not None and (
                    newest_mutation is None or changed_at > newest_mutation
                ):
                    newest_mutation = changed_at

            if row_count == 0:
                raise CatalogBuildError("ACM CSV contains zero data rows")
            connection.execute(
                "CREATE INDEX number_ranges_lookup ON number_ranges(e164_from, e164_to) "
                "WHERE e164_from IS NOT NULL"
            )
            metadata = _metadata(
                manifest,
                source_sha256=source_sha256,
                row_count=row_count,
                matchable_row_count=matchable_row_count,
                status_counts=status_counts,
                destination_counts=destination_counts,
                newest_mutation=newest_mutation,
            )
            connection.executemany(
                "INSERT INTO catalog_metadata (key, value) VALUES (?, ?)", metadata.items()
            )
            connection.commit()
    except sqlite3.IntegrityError as error:
        message = f"ACM CSV contains duplicate or invalid records: {error}"
        raise CatalogBuildError(message) from error

    return CatalogBuildSummary(
        output_path=output_path,
        row_count=row_count,
        matchable_row_count=matchable_row_count,
        status_counts=dict(sorted(status_counts.items())),
        destination_counts=dict(sorted(destination_counts.items())),
        newest_mutation=newest_mutation,
        source_sha256=source_sha256,
    )


def _project_row(row: dict[str, str | None]) -> tuple[Any, ...]:
    if set(row) != set(EXPECTED_COLUMNS) or any(row[column] is None for column in EXPECTED_COLUMNS):
        raise CatalogBuildError("ACM CSV row does not match the exact supported columns")
    source_record_id = str(row["id"]).strip()
    destination = str(row["twn_bestemming"]).strip()
    register_status = str(row["twn_nummerstatus"]).strip()
    if not source_record_id or not destination or not register_status:
        raise CatalogBuildError("ACM CSV row is missing required public fields")
    national_from = _range_digits(str(row["twn_nummervan"]), source_record_id)
    national_to = _range_digits(str(row["twn_nummertm"]), source_record_id)
    if len(national_from) != len(national_to) or int(national_from) > int(national_to):
        raise CatalogBuildError(f"ACM source row {source_record_id} has an invalid range")
    e164_from, e164_to = _e164_interval(national_from, national_to)
    source_changed_at = _source_changed_at(str(row["datummutatie"]), source_record_id)
    row_digest = hashlib.sha256(
        json.dumps(
            [row[column] for column in EXPECTED_COLUMNS],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return (
        source_record_id,
        national_from,
        national_to,
        e164_from,
        e164_to,
        destination,
        _number_type(destination),
        register_status,
        source_changed_at,
        row_digest,
    )


def _range_digits(value: str, source_record_id: str) -> str:
    value = value.strip()
    if not value or _RANGE_PATTERN.fullmatch(value) is None:
        raise CatalogBuildError(f"ACM source row {source_record_id} has malformed range text")
    digits = re.sub(r"\D", "", value)
    if not digits:
        raise CatalogBuildError(f"ACM source row {source_record_id} has an empty range")
    return digits


def _e164_interval(national_from: str, national_to: str) -> tuple[int | None, int | None]:
    if not national_from.startswith("0") or not 7 <= len(national_from) <= 11:
        return None, None
    return int(f"31{national_from[1:]}"), int(f"31{national_to[1:]}")


def _source_changed_at(value: str, source_record_id: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as error:
        raise CatalogBuildError(
            f"ACM source row {source_record_id} has an invalid mutation timestamp"
        ) from error
    return value


def _number_type(destination: str) -> str:
    lowered = destination.casefold()
    if "geografische nummers" in lowered:
        return "geographic"
    if "mobiele telefonie" in lowered:
        return "mobile"
    if lowered.startswith("0800"):
        return "freephone"
    if lowered.startswith(("0900", "0906", "0909")):
        return "premium_rate"
    if "geautomatiseerde toepassingen" in lowered:
        return "machine_to_machine"
    if "ondernemingen en instellingen" in lowered:
        return "business_access"
    if "signaleringspuntcode" in lowered or "netwerkcode" in lowered:
        return "network_code"
    return "other"


def _metadata(
    manifest: dict[str, Any],
    *,
    source_sha256: str,
    row_count: int,
    matchable_row_count: int,
    status_counts: Counter[str],
    destination_counts: Counter[str],
    newest_mutation: str | None,
) -> dict[str, str]:
    source = manifest["source"]
    artifact = manifest["artifact"]
    return {
        "schema_version": "1.0.0",
        "source_id": source["source_id"],
        "source_url": source["registry_url"],
        "dataset_url": source["dataset_url"],
        "download_url": artifact["download_url"],
        "license": source["license"],
        "license_url": source["license_url"],
        "retrieved_at": artifact["retrieved_at"],
        "source_sha256": source_sha256,
        "row_count": str(row_count),
        "matchable_row_count": str(matchable_row_count),
        "status_counts": json.dumps(dict(sorted(status_counts.items())), separators=(",", ":")),
        "destination_counts": json.dumps(
            dict(sorted(destination_counts.items())), ensure_ascii=False, separators=(",", ":")
        ),
        "newest_mutation": newest_mutation or "",
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise CatalogBuildError(f"Cannot read ACM archive: {error}") from error
    return digest.hexdigest()
