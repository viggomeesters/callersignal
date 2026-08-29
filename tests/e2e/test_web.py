from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from callersignal.http_api import create_app

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"

PUBLIC_CAMPAIGN = {
    "schema_version": "1.0.0",
    "kind": "caller_campaign",
    "campaign_id": "cmp_reserved_demo",
    "title": "Reserved-number impersonation pattern",
    "status": "active",
    "risk_state": "elevated_signals",
    "subject_semantics": "calls_displaying_numbers_or_patterns",
    "categories": ["impersonation_attempt"],
    "jurisdictions": ["US"],
    "membership": [
        {
            "kind": "displayed_number",
            "value": "+1" + "202" + "555" + "0147",
            "subject_semantics": "call_displayed_value",
            "identity_scope": "no_caller_or_subscriber_identity_claim",
        }
    ],
    "timeline": {
        "first_seen": "2026-08-20T08:00:00Z",
        "last_seen": "2026-08-27T08:00:00Z",
        "published_at": "2026-08-27T09:00:00Z",
        "updated_at": "2026-08-27T09:00:00Z",
    },
    "evidence": {
        "eligible_evidence_ids": ["ev_reserved_one", "ev_reserved_two"],
        "source_ids": ["source_one", "source_two"],
        "source_diversity": 2,
        "reason_codes": ["shared_impersonation_pattern"],
        "excluded_reason_codes": [],
    },
    "confidence": {"level": "high", "score": 0.86},
    "freshness": {"as_of": "2026-08-27T08:00:00Z", "status": "current"},
    "recommended_actions": [
        "avoid_sensitive_actions",
        "verify_through_trusted_channel",
    ],
    "correction": {"status": "none", "updated_at": None, "reason_codes": []},
    "limitations": [
        "Caller ID can be spoofed; this record describes displayed values.",
        "Campaign evidence does not identify who placed an individual call.",
    ],
}


def wsgi_request(app, path: str) -> tuple[str, dict, dict]:
    captured: dict = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        app(
            {"REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": ""},
            start_response,
        )
    )
    return captured["status"], captured["headers"], json.loads(body)


class DocumentFacts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.labels: set[str] = set()
        self.meta_names: set[str] = set()
        self.headings: list[str] = []
        self._heading: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(str(attributes["id"]))
        if tag == "label" and attributes.get("for"):
            self.labels.add(str(attributes["for"]))
        if tag == "meta" and attributes.get("name"):
            self.meta_names.add(str(attributes["name"]))
        if tag in {"h1", "h2", "h3"}:
            self._heading = []

    def handle_data(self, data: str) -> None:
        if self._heading is not None:
            self._heading.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3"} and self._heading is not None:
            self.headings.append(" ".join("".join(self._heading).split()))
            self._heading = None


def lookup_validator() -> Draft202012Validator:
    schemas = {
        name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        for name in (
            "phone-number.schema.json",
            "source-evidence.schema.json",
            "lookup-result.schema.json",
        )
    }
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return Draft202012Validator(
        schemas["lookup-result.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )


def test_page_has_semantic_lookup_form_status_and_metadata() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    facts = DocumentFacts()
    facts.feed(html)

    assert {"number", "origin-region"} <= facts.labels
    assert {"lookup-form", "lookup-status", "result"} <= facts.ids
    assert {
        "risk-banner",
        "risk-state",
        "risk-headline",
        "risk-summary",
        "risk-basis",
        "risk-action",
    } <= facts.ids
    assert {"description", "viewport", "theme-color"} <= facts.meta_names
    assert facts.headings[0] == "Check the signal. Know what to do."
    assert "Why this result" in facts.headings
    assert 'aria-live="polite"' in html
    assert 'type="tel"' in html
    assert 'autocomplete="tel"' in html
    assert html.count('class="risk-icon ') == 4
    assert "confidence-bar" not in html
    assert "confidence-track" not in html
    assert {
        "safety-checklist",
        "campaign-history",
        "result-actions",
        "technical-disclosure",
        "campaigns",
        "campaign-list",
        "campaign-detail",
        "coverage",
        "coverage-no-match",
        "metric-acm-ranges",
        "metric-acm-matchable",
        "metric-indexed-services",
        "metric-enabled-reputation",
        "official-catalog-title",
        "catalog-status-list",
        "reputation-coverage-title",
        "reputation-reason-list",
        "reputation-service-list",
        "source-coverage-list",
        "moderation-threshold",
    } <= facts.ids
    assert "Report this call" in html
    assert "Watch this number" in html
    assert "Public campaign index" in facts.headings


def test_page_offers_the_acm_blocked_number_as_a_dutch_public_safe_example() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")

    assert html.count('class="example-button"') == 3
    assert 'data-number="0906-8844" data-region="NL"' in html
    assert "NL ACM-blocked number" in html


def test_page_declares_a_self_contained_icon_without_a_favicon_request() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")

    assert '<link rel="icon" href="data:image/svg+xml,' in html


def test_styles_prove_focus_responsive_reduced_motion_and_overflow_boundaries() -> None:
    css = (WEB / "assets" / "styles.css").read_text(encoding="utf-8")

    assert ":focus-visible" in css
    assert "@media (max-width: 720px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "overflow-wrap: anywhere" in css
    assert "min-height: 44px" in css
    assert "transition: all" not in css
    state_icons = {
        "official_warning": "risk-icon-official",
        "elevated_signals": "risk-icon-elevated",
        "no_risk_evidence": "risk-icon-cautious",
        "insufficient_evidence": "risk-icon-unknown",
    }
    for state, icon_class in state_icons.items():
        assert (
            f'.risk-banner[data-risk-state="{state}"] .{icon_class}' in css
        )


def test_browser_code_uses_the_shared_api_without_a_local_verdict_path() -> None:
    script = (WEB / "assets" / "app.js").read_text(encoding="utf-8")

    assert 'fetch(buildLookupURL(' in script
    assert "`/v1/lookup?${query.toString()}`" in script
    assert "assessment.risk" in script
    assert "assessment.confidence" in script
    assert "assessment.residual_risk" in script
    assert "confidenceScore" not in script
    assert "confidence-bar" not in script
    assert ".innerHTML" not in script
    assert "Math.random" not in script
    assert "localStorage" not in script
    assert 'fetch(buildCampaignURL(' in script
    assert "fetch(buildTransparencyURL()" in script
    assert "resultTitle.textContent = view.number.title" in script


def test_committed_transparency_asset_exposes_coverage_not_vanity_totals() -> None:
    snapshot = json.loads(
        (WEB / "assets" / "transparency.json").read_text(encoding="utf-8")
    )

    assert snapshot["kind"] == "corpus_transparency"
    assert snapshot["coverage"]["enabled_source_count"] == 3
    assert snapshot["coverage"]["risk_capable_source_count"] == 0
    assert snapshot["coverage"]["number_catalog"]["imported_range_count"] == 74_984
    assert snapshot["coverage"]["number_catalog"]["matchable_range_count"] == 73_409
    assert snapshot["coverage"]["reputation_sources"]["indexed_service_count"] == 16
    assert snapshot["coverage"]["reputation_sources"]["licensable_service_count"] == 4
    assert snapshot["coverage"]["reputation_sources"]["enabled_source_count"] == 0
    assert snapshot["corpus"]["eligible_campaigns"] == 0
    assert snapshot["moderation"]["status"] == "not_approved"
    assert snapshot["interpretation"]["lookup_popularity_used_for_reputation"] is False
    serialized = json.dumps(snapshot)
    assert "lookup_count" not in serialized
    assert "raw_report_count" not in serialized


def test_public_campaign_routes_project_only_eligible_aggregate_evidence() -> None:
    monitoring = deepcopy(PUBLIC_CAMPAIGN)
    monitoring["campaign_id"] = "cmp_monitoring_fixture"
    monitoring["status"] = "monitoring"
    incomplete = deepcopy(PUBLIC_CAMPAIGN)
    incomplete["campaign_id"] = "cmp_incomplete_coverage"
    malformed = deepcopy(PUBLIC_CAMPAIGN)
    malformed["campaign_id"] = "cmp_malformed_sources"
    malformed["evidence"]["source_ids"] = [["not", "a", "source", "id"]]
    unexpected = deepcopy(PUBLIC_CAMPAIGN)
    unexpected["campaign_id"] = "cmp_unexpected_status"
    unexpected["status"] = "unexpected"
    app = create_app(
        public_campaigns=[
            {
                "campaign": PUBLIC_CAMPAIGN,
                "verified_organization": {
                    "display_name": "Example Bank",
                    "verification_status": "verified",
                    "declaration_scope": "official_contact_route_only",
                },
                "source_coverage": [
                    {
                        "source_id": "source_one",
                        "status": "matched",
                        "checked_at": "2026-08-27T08:00:00Z",
                    },
                    {
                        "source_id": "source_two",
                        "status": "matched",
                        "checked_at": "2026-08-27T08:01:00Z",
                    },
                ],
                "private_reports": [{"reporter": "must-not-leak"}],
                "lookup_count": 999,
            },
            {"campaign": monitoring, "source_coverage": []},
            {
                "campaign": incomplete,
                "source_coverage": [
                    {
                        "source_id": "source_one",
                        "status": "matched",
                        "checked_at": "2026-08-27T08:00:00Z",
                    }
                ],
            },
            {"campaign": malformed, "source_coverage": []},
            {
                "campaign": unexpected,
                "source_coverage": [
                    {
                        "source_id": "source_one",
                        "status": "matched",
                        "checked_at": "2026-08-27T08:00:00Z",
                    },
                    {
                        "source_id": "source_two",
                        "status": "matched",
                        "checked_at": "2026-08-27T08:01:00Z",
                    },
                ],
            },
        ]
    )

    list_status, _, catalogue = wsgi_request(app, "/v1/campaigns")
    detail_status, _, detail = wsgi_request(
        app, "/v1/campaigns/cmp_reserved_demo"
    )
    missing_status, _, missing = wsgi_request(app, "/v1/campaigns/cmp_missing")

    assert list_status == "200 OK"
    assert catalogue["kind"] == "public_campaign_catalogue"
    assert len(catalogue["campaigns"]) == 1
    assert catalogue["campaigns"][0]["campaign_id"] == "cmp_reserved_demo"
    assert detail_status == "200 OK"
    assert detail["kind"] == "public_campaign"
    assert detail["campaign"] == PUBLIC_CAMPAIGN
    assert len(detail["source_coverage"]) == 2
    serialized = json.dumps({"catalogue": catalogue, "detail": detail})
    assert "private_reports" not in serialized
    assert "reporter" not in serialized
    assert "lookup_count" not in serialized
    assert missing_status == "404 Not Found"
    assert missing["error"]["code"] == "campaign_not_found"


def test_vercel_campaign_entrypoint_maps_list_and_detail_routes() -> None:
    entrypoint = ROOT / "api" / "campaigns.py"
    spec = importlib.util.spec_from_file_location("callersignal_web_campaigns", entrypoint)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured: dict = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    list_body = b"".join(
        module.app(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/campaigns", "QUERY_STRING": ""},
            start_response,
        )
    )
    assert captured["status"] == "200 OK"
    assert json.loads(list_body)["kind"] == "public_campaign_catalogue"

    detail_body = b"".join(
        module.app(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/campaigns",
                "QUERY_STRING": "campaign_id=cmp_missing",
            },
            start_response,
        )
    )
    assert captured["status"] == "404 Not Found"
    assert json.loads(detail_body)["error"]["code"] == "campaign_not_found"


def test_vercel_wsgi_entrypoint_delegates_to_canonical_http_result() -> None:
    entrypoint = ROOT / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("callersignal_web_api", entrypoint)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured: dict = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        module.app(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/index",
                "QUERY_STRING": urlencode(
                    {"number": "202-555-0147", "origin_region": "US"}
                ),
            },
            start_response,
        )
    )
    result = json.loads(body)
    international = "+1" + "202" + "555" + "0147"

    assert captured["status"] == "200 OK"
    assert result["kind"] == "lookup_result"
    assert result["phone_number"]["canonical"]["e164"] == international
    lookup_validator().validate(result)


def test_vercel_health_entrypoint_delegates_to_canonical_health_result() -> None:
    entrypoint = ROOT / "api" / "healthz.py"
    spec = importlib.util.spec_from_file_location("callersignal_web_health", entrypoint)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured: dict = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        module.app(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/healthz",
                "QUERY_STRING": "",
            },
            start_response,
        )
    )

    assert captured["status"] == "200 OK"
    assert captured["headers"]["Cache-Control"] == "no-store"
    assert json.loads(body) == {
        "schema_version": "1.0.0",
        "service": "callersignal",
        "status": "ok",
    }


def test_vercel_coverage_entrypoint_delegates_to_canonical_projection() -> None:
    entrypoint = ROOT / "api" / "coverage.py"
    spec = importlib.util.spec_from_file_location("callersignal_web_coverage", entrypoint)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured: dict = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        module.app(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/coverage",
                "QUERY_STRING": "",
            },
            start_response,
        )
    )
    coverage = json.loads(body)

    assert captured["status"] == "200 OK"
    assert coverage == json.loads(
        (WEB / "assets/transparency.json").read_text(encoding="utf-8")
    )


def test_vercel_routes_one_public_origin_to_static_web_and_canonical_api() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    rewrites = {
        item["source"]: item["destination"] for item in config["rewrites"]
    }
    assert rewrites == {
        "/v1/lookup": "/api/index",
        "/v1/campaigns": "/api/campaigns",
        "/v1/campaigns/:campaign_id": "/api/campaigns?campaign_id=:campaign_id",
        "/v1/coverage": "/api/coverage",
        "/healthz": "/api/healthz",
        "/mcp": "/api/mcp",
        "/.well-known/oauth-protected-resource": (
            "/api/mcp?route=oauth-protected-resource"
        ),
        "/.well-known/oauth-protected-resource/mcp": (
            "/api/mcp?route=oauth-protected-resource"
        ),
        "/campaigns": "/index",
        "/campaigns/:campaign_id": "/index",
        "/": "/index",
    }
    assert config["functions"]["api/**/*.py"]["includeFiles"] == (
        "{src/callersignal/**,schemas/**,fixtures/**,downloads/acm-number-register.sqlite3,"
        "downloads/fcc-unwanted-calls.sqlite3,web/assets/transparency.json}"
    )
    assert package["scripts"]["build:acm"] == (
        "python3 scripts/build_acm_catalog.py --json"
    )
    assert package["scripts"]["build:fcc"] == (
        "python3 scripts/build_fcc_catalog.py --json"
    )
    assert package["scripts"]["build:vercel"] == (
        "npm run build:acm && npm run build:fcc && node scripts/stage_vercel_static.mjs"
    )
    assert config["buildCommand"] == "npm run build:vercel"
    assert config["outputDirectory"] == "public"
    assert config["env"]["CALLERSIGNAL_ACM_CATALOG_PATH"] == (
        "downloads/acm-number-register.sqlite3"
    )
    assert config["env"]["CALLERSIGNAL_FCC_CATALOG_PATH"] == (
        "downloads/fcc-unwanted-calls.sqlite3"
    )
