from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from callersignal.fcc_catalog import FCCCatalogBuildError, build_fcc_catalog

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "sources/fcc-complaints-manifest.json"
FIXTURE_PATH = ROOT / "tests/fixtures/fcc_unwanted_calls_sample.json"
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
LOOKUP_KEY = b"test-only-fcc-lookup-key-32-bytes"


class FixtureFetcher:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> Any:
        self.calls.append((url, dict(params)))
        if not params:
            return copy.deepcopy(self.payload["metadata"])
        offset = int(params["$offset"])
        limit = int(params["$limit"])
        return copy.deepcopy(self.payload["rows"][offset : offset + limit])


def _fixture() -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture["metadata"]["rowsUpdatedAt"] = int(
        datetime.fromisoformat(
            fixture.pop("source_updated_at").replace("Z", "+00:00")
        ).timestamp()
    )
    return fixture


def _build(tmp_path: Path, payload: dict[str, Any] | None = None):
    fetcher = FixtureFetcher(payload or _fixture())
    output = tmp_path / "fcc.sqlite3"
    summary = build_fcc_catalog(
        MANIFEST_PATH,
        output,
        lookup_key=LOOKUP_KEY,
        generated_at=NOW,
        fetch_json=fetcher,
    )
    return summary, output, fetcher


def test_builds_hmac_keyed_aggregate_without_plaintext_source_rows(
    tmp_path: Path,
) -> None:
    summary, output, fetcher = _build(tmp_path)

    assert summary.unique_number_count == 2
    assert summary.grouped_row_count == 4
    assert summary.source_observation_count == 8
    assert summary.indexed_observation_count == 6
    assert summary.rejected_number_row_count == 1
    assert summary.rejected_observation_count == 2
    assert summary.category_counts == {"nuisance": 4, "robocall": 2}
    assert summary.first_issue_date == "2026-08-01"
    assert summary.last_issue_date == "2026-08-12"
    assert summary.source_updated_at == "2026-08-29T05:02:20Z"
    assert summary.window_start == "2021-08-29"
    assert summary.window_end == "2026-08-29"
    assert len(summary.source_digest) == 64

    expected_key = hmac.new(LOOKUP_KEY, b"+12025550100", hashlib.sha256).hexdigest()
    with sqlite3.connect(output) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM catalog_metadata"))
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(complaint_aggregates)")
        }
        records = connection.execute(
            "SELECT lookup_key, nuisance_count, robocall_count, observation_count, "
            "first_issue_date, last_issue_date FROM complaint_aggregates ORDER BY lookup_key"
        ).fetchall()

    assert columns == {
        "lookup_key",
        "nuisance_count",
        "robocall_count",
        "observation_count",
        "first_issue_date",
        "last_issue_date",
    }
    matched = next(record for record in records if record[0] == expected_key)
    assert matched[1:] == (3, 2, 5, "2026-08-01", "2026-08-12")
    assert metadata["source_id"] == "fcc_unwanted_call_complaints"
    assert metadata["dataset_id"] == "vakf-fz8e"
    assert metadata["license"] == "Public Domain U.S. Government"
    assert metadata["unique_number_count"] == "2"
    assert json.loads(metadata["category_counts"]) == {"nuisance": 4, "robocall": 2}
    assert metadata["source_digest"] == summary.source_digest

    database_bytes = output.read_bytes()
    for forbidden in (
        b"+12025550100",
        b"2025550100",
        b"202-555-0100",
        b"not-a-number",
        b"Individual informal consumer complaint",
    ):
        assert forbidden not in database_bytes

    metadata_call, page_call, metadata_readback = fetcher.calls
    assert metadata_call == (
        "https://opendata.fcc.gov/api/views/vakf-fz8e",
        {},
    )
    assert page_call[0] == "https://opendata.fcc.gov/resource/vakf-fz8e.json"
    assert metadata_readback == metadata_call
    assert page_call[1]["$select"].split(",") == [
        "caller_id_number",
        "type_of_call_or_messge",
        "count(*) as observation_count",
        "min(issue_date) as first_issue_date",
        "max(issue_date) as last_issue_date",
    ]
    assert page_call[1]["$group"] == "caller_id_number,type_of_call_or_messge"
    assert page_call[1]["$order"] == (
        "caller_id_number ASC,type_of_call_or_messge ASC"
    )
    assert "2021-08-29T00:00:00.000" in page_call[1]["$where"]
    assert "2026-08-29T23:59:59.999" in page_call[1]["$where"]
    for forbidden_field in (
        "id",
        "issue_time",
        "issue_type",
        "method",
        "issue",
        "advertiser_business_phone_number",
        "state",
        "zip",
        "location_1",
    ):
        assert forbidden_field not in page_call[1]["$select"].split(",")


def test_paginates_until_a_short_page_and_rejects_duplicate_group_keys(
    tmp_path: Path,
) -> None:
    payload = _fixture()
    rows = []
    for line in range(100, 200):
        row = copy.deepcopy(payload["rows"][0])
        row["caller_id_number"] = f"202555{line:04d}"
        row["observation_count"] = "1"
        rows.append(row)
    rows.append(copy.deepcopy(rows[0]))
    payload["rows"] = rows
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["query"]["page_size"] = 100
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    fetcher = FixtureFetcher(payload)
    output = tmp_path / "fcc.sqlite3"
    output.write_bytes(b"prior valid catalogue")

    with pytest.raises(FCCCatalogBuildError, match="duplicate grouped row"):
        build_fcc_catalog(
            manifest_path,
            output,
            lookup_key=LOOKUP_KEY,
            generated_at=NOW,
            fetch_json=fetcher,
        )

    assert [params.get("$offset") for _, params in fetcher.calls] == [
        None,
        "0",
        "100",
    ]
    assert output.read_bytes() == b"prior valid catalogue"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["metadata"]["license"].update(name="Unknown"), "license"),
        (
            lambda data: data["metadata"]["columns"].append(
                {"fieldName": "unexpected", "dataTypeName": "text"}
            ),
            "schema",
        ),
        (
            lambda data: data["metadata"].update(
                rowsUpdatedAt=int((NOW - timedelta(days=31)).timestamp())
            ),
            "stale",
        ),
        (
            lambda data: data["rows"][0].update(type_of_call_or_messge="Email"),
            "category",
        ),
        (lambda data: data["rows"][0].update(observation_count="0"), "count"),
        (
            lambda data: data["rows"][0].update(
                last_issue_date="2021-08-28T00:00:00.000"
            ),
            "date",
        ),
    ],
)
def test_metadata_and_row_drift_fail_closed_before_atomic_replacement(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    payload = _fixture()
    mutation(payload)
    output = tmp_path / "fcc.sqlite3"
    output.write_bytes(b"prior valid catalogue")

    with pytest.raises(FCCCatalogBuildError, match=message):
        build_fcc_catalog(
            MANIFEST_PATH,
            output,
            lookup_key=LOOKUP_KEY,
            generated_at=NOW,
            fetch_json=FixtureFetcher(payload),
        )

    assert output.read_bytes() == b"prior valid catalogue"


@pytest.mark.parametrize("lookup_key", [b"", b"short", "not-bytes"])
def test_missing_or_weak_lookup_key_fails_before_network_or_replacement(
    tmp_path: Path, lookup_key: object
) -> None:
    fetcher = FixtureFetcher(_fixture())
    output = tmp_path / "fcc.sqlite3"
    output.write_bytes(b"prior valid catalogue")

    with pytest.raises(FCCCatalogBuildError, match="lookup key"):
        build_fcc_catalog(
            MANIFEST_PATH,
            output,
            lookup_key=lookup_key,  # type: ignore[arg-type]
            generated_at=NOW,
            fetch_json=fetcher,
        )

    assert fetcher.calls == []
    assert output.read_bytes() == b"prior valid catalogue"


def test_zero_valid_numbers_fails_closed(tmp_path: Path) -> None:
    payload = _fixture()
    payload["rows"] = [payload["rows"][-1]]

    with pytest.raises(FCCCatalogBuildError, match="zero valid"):
        build_fcc_catalog(
            MANIFEST_PATH,
            tmp_path / "fcc.sqlite3",
            lookup_key=LOOKUP_KEY,
            generated_at=NOW,
            fetch_json=FixtureFetcher(payload),
        )


def test_source_update_during_pagination_refuses_atomic_replacement(
    tmp_path: Path,
) -> None:
    payload = _fixture()
    fetcher = FixtureFetcher(payload)
    metadata_url = "https://opendata.fcc.gov/api/views/vakf-fz8e"
    metadata_calls = 0

    def mutate_on_readback(url: str, params: dict[str, str]) -> Any:
        nonlocal metadata_calls
        result = fetcher(url, params)
        if url == metadata_url:
            metadata_calls += 1
            if metadata_calls == 2:
                result["rowsUpdatedAt"] += 1
        return result

    output = tmp_path / "fcc.sqlite3"
    output.write_bytes(b"prior valid catalogue")

    with pytest.raises(FCCCatalogBuildError, match="changed during"):
        build_fcc_catalog(
            MANIFEST_PATH,
            output,
            lookup_key=LOOKUP_KEY,
            generated_at=NOW,
            fetch_json=mutate_on_readback,
        )

    assert metadata_calls == 2
    assert output.read_bytes() == b"prior valid catalogue"


def test_build_script_fails_before_network_when_secret_is_missing(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment.pop("CALLERSIGNAL_REPUTATION_INDEX_KEY", None)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_fcc_catalog.py"),
            "--output",
            str(tmp_path / "fcc.sqlite3"),
            "--json",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "CALLERSIGNAL_REPUTATION_INDEX_KEY is required" in result.stderr
    assert not (tmp_path / "fcc.sqlite3").exists()
