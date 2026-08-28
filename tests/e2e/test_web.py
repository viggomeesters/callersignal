from __future__ import annotations

import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"


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
    assert facts.headings[0] == "A number is a signal. Not an identity."
    assert "Why this result" in facts.headings
    assert 'aria-live="polite"' in html
    assert 'type="tel"' in html
    assert 'autocomplete="tel"' in html
    assert html.count('class="risk-icon ') == 4
    assert "confidence-bar" not in html
    assert "confidence-track" not in html


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


def test_vercel_routes_one_public_origin_to_static_web_and_canonical_api() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    rewrites = {
        item["source"]: item["destination"] for item in config["rewrites"]
    }
    assert rewrites == {
        "/v1/lookup": "/api/index",
        "/healthz": "/api/healthz",
        "/assets/:path*": "/web/assets/:path*",
        "/": "/web/index",
    }
    assert config["functions"]["api/**/*.py"]["includeFiles"] == (
        "src/callersignal/**"
    )
