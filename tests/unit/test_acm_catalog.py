from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from callersignal.acm_catalog import CatalogBuildError, build_acm_catalog

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_CSV = ROOT / "tests/fixtures/acm_register_sample.csv"

EXPECTED_COLUMNS = [
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
]


def _write_archive(path: Path, csv_bytes: bytes | None = None) -> bytes:
    source = csv_bytes if csv_bytes is not None else SAMPLE_CSV.read_bytes()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("nummers.csv", source)
    return path.read_bytes()


def _write_manifest(path: Path, archive_bytes: bytes, **overrides: object) -> None:
    artifact = {
        "download_url": "https://www.acm.nl/sites/default/files/registers/nummers_csv.zip",
        "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "archive_member": "nummers.csv",
        "csv_encoding": "utf-8-sig",
        "csv_delimiter": ";",
        "expected_columns": EXPECTED_COLUMNS,
        "retrieved_at": "2026-08-29T11:23:00Z",
    }
    artifact.update(overrides)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "kind": "acm_bulk_manifest",
                "source": {
                    "source_id": "acm_number_register",
                    "name": "ACM public telephone number register",
                    "registry_url": "https://www.acm.nl/nl/telefoonnummers-zoeken",
                    "dataset_url": "https://data.overheid.nl/dataset/register-van-toegekende-telefoonnummers",
                    "license": "CC0 1.0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                },
                "artifact": artifact,
            }
        ),
        encoding="utf-8",
    )


def test_builds_privacy_minimized_catalog_with_provenance(tmp_path: Path) -> None:
    archive_path = tmp_path / "source.zip"
    archive_bytes = _write_archive(archive_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, archive_bytes)
    output_path = tmp_path / "catalog.sqlite3"

    summary = build_acm_catalog(manifest_path, output_path, archive_path=archive_path)

    assert summary.row_count == 1
    assert summary.status_counts == {"Geblokkeerd": 1}
    assert summary.newest_mutation is None
    with sqlite3.connect(output_path) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM catalog_metadata"))
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(number_ranges)")
        }
        record = connection.execute(
            """
            SELECT source_record_id, national_from, national_to, e164_from,
                   e164_to, destination, number_type, register_status,
                   source_changed_at, source_row_sha256
              FROM number_ranges
            """
        ).fetchone()

    assert metadata["source_url"] == "https://www.acm.nl/nl/telefoonnummers-zoeken"
    assert metadata["dataset_url"].startswith("https://data.overheid.nl/")
    assert metadata["license"] == "CC0 1.0"
    assert metadata["retrieved_at"] == "2026-08-29T11:23:00Z"
    assert metadata["source_sha256"] == hashlib.sha256(archive_bytes).hexdigest()
    assert json.loads(metadata["status_counts"]) == {"Geblokkeerd": 1}
    assert json.loads(metadata["destination_counts"]) == {
        "0906 gratis of betaalde informatiediensten met een lengte van acht cijfers": 1
    }
    assert record[:9] == (
        "74716",
        "09068844",
        "09068844",
        319068844,
        319068844,
        "0906 gratis of betaalde informatiediensten met een lengte van acht cijfers",
        "premium_rate",
        "Geblokkeerd",
        None,
    )
    assert len(record[9]) == 64
    assert {
        "range_holder",
        "relation_name",
        "relation_id",
        "kvk_number",
        "kvk_establishment_number",
        "place",
    }.isdisjoint(columns)
    assert b"Fixture Holder Must Not Persist" not in output_path.read_bytes()


def test_catalog_build_error_is_a_public_exception_type() -> None:
    assert issubclass(CatalogBuildError, ValueError)


def test_build_script_is_one_deterministic_json_command(tmp_path: Path) -> None:
    archive_path = tmp_path / "source.zip"
    archive_bytes = _write_archive(archive_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, archive_bytes)
    output_path = tmp_path / "catalog.sqlite3"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_acm_catalog.py"),
            "--manifest",
            str(manifest_path),
            "--archive",
            str(archive_path),
            "--output",
            str(output_path),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 1
    assert payload["matchable_row_count"] == 1
    assert payload["status_counts"] == {"Geblokkeerd": 1}
    assert payload["output_path"] == str(output_path.resolve())


@pytest.mark.parametrize(
    "unsafe_case",
    ["checksum", "malformed_zip", "schema_drift", "duplicate_id", "invalid_range", "zero_rows"],
)
def test_unsafe_inputs_fail_closed_without_replacing_catalog(
    tmp_path: Path, unsafe_case: str
) -> None:
    source = SAMPLE_CSV.read_bytes()
    manifest_overrides: dict[str, object] = {}
    archive_path = tmp_path / "source.zip"
    if unsafe_case == "malformed_zip":
        archive_path.write_bytes(b"not a ZIP archive")
        archive_bytes = archive_path.read_bytes()
    else:
        if unsafe_case == "schema_drift":
            source = b"id;unexpected\n74716;value\n"
        elif unsafe_case == "duplicate_id":
            source = source + source.splitlines(keepends=True)[1]
        elif unsafe_case == "invalid_range":
            source = source.replace(b"0906-8844;0906-8844", b"0000-0001;0000-0002")
        elif unsafe_case == "zero_rows":
            source = source.splitlines(keepends=True)[0]
        archive_bytes = _write_archive(archive_path, source)
    if unsafe_case == "checksum":
        manifest_overrides["sha256"] = "f" * 64

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, archive_bytes, **manifest_overrides)
    output_path = tmp_path / "catalog.sqlite3"
    original = b"previous valid catalogue"
    output_path.write_bytes(original)

    with pytest.raises(CatalogBuildError):
        build_acm_catalog(manifest_path, output_path, archive_path=archive_path)

    assert output_path.read_bytes() == original


def test_manifest_rejects_non_https_source_locations(tmp_path: Path) -> None:
    archive_path = tmp_path / "source.zip"
    archive_bytes = _write_archive(archive_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, archive_bytes, download_url="file:///private/source.zip")

    with pytest.raises(CatalogBuildError, match="HTTPS"):
        build_acm_catalog(
            manifest_path,
            tmp_path / "catalog.sqlite3",
            archive_path=archive_path,
        )


def test_pinned_catalog_expectations_fail_closed_before_replacement(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "source.zip"
    archive_bytes = _write_archive(archive_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, archive_bytes)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["catalog_expectations"] = {
        "row_count": 2,
        "matchable_row_count": 1,
        "status_counts": {"Geblokkeerd": 2},
        "destination_category_count": 1,
        "newest_mutation": None,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output_path = tmp_path / "catalog.sqlite3"
    output_path.write_bytes(b"previous valid catalogue")

    with pytest.raises(CatalogBuildError, match="expectations"):
        build_acm_catalog(manifest_path, output_path, archive_path=archive_path)

    assert output_path.read_bytes() == b"previous valid catalogue"


def test_download_uses_https_only_curl_fallback_without_bypassing_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "fixture.zip"
    archive_bytes = _write_archive(archive_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, archive_bytes)
    commands: list[list[str]] = []

    def fail_urlopen(*args, **kwargs):
        del args, kwargs
        raise OSError("fixture TLS failure")

    def fake_curl(command: list[str], **kwargs) -> None:
        del kwargs
        commands.append(command)
        destination = Path(command[command.index("--output") + 1])
        destination.write_bytes(archive_bytes)

    monkeypatch.setattr("callersignal.acm_catalog.urllib.request.urlopen", fail_urlopen)
    monkeypatch.setattr("callersignal.acm_catalog.subprocess.run", fake_curl)

    summary = build_acm_catalog(manifest_path, tmp_path / "catalog.sqlite3")

    assert summary.source_sha256 == hashlib.sha256(archive_bytes).hexdigest()
    assert commands
    assert ["--proto", "=https"] == commands[0][2:4]
    assert ["--proto-redir", "=https"] == commands[0][4:6]
