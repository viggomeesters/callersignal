"""Tool definitions and public-safe calls for the hosted MCP surface."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any

from callersignal.http_api import LookupHTTPApplication
from callersignal.lookup import LookupService
from callersignal.mcp_server import call_lookup_tool, tool_definition

_ROOT = Path(__file__).resolve().parents[3]
_CAMPAIGN_ID = re.compile(r"^cmp_[A-Za-z0-9_-]{8,64}$")
_EMPTY_OBJECT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {},
}
_PUBLIC_OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
}

PROTECTED_TOOL_SCOPES = {
    "create_private_watch": "callersignal.watch:write",
    "delete_private_watch": "callersignal.watch:delete",
    "submit_organization_portfolio": "callersignal.organizations:write",
    "delete_organization_portfolio": "callersignal.organizations:delete",
}


def tool_definitions() -> list[dict[str, Any]]:
    """Return public reads and accurately locked protected mutation contracts."""
    lookup = deepcopy(tool_definition())
    lookup["annotations"] = _read_annotations()
    return [
        lookup,
        _public_tool(
            "list_public_campaigns",
            "List eligible public caller campaigns",
            (
                "Return the same rights-approved aggregate campaign catalogue as the public "
                "HTTP API. An empty list means no campaign currently meets the publication "
                "bar, not that unfamiliar calls are safe."
            ),
            _EMPTY_OBJECT_SCHEMA,
        ),
        _public_tool(
            "get_public_campaign",
            "Get one eligible public caller campaign",
            (
                "Return one public aggregate campaign by its opaque campaign identifier. "
                "Membership describes displayed values and never proves caller identity."
            ),
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["campaign_id"],
                "properties": {
                    "campaign_id": {
                        "type": "string",
                        "pattern": "^cmp_[A-Za-z0-9_-]{8,64}$",
                    }
                },
            },
        ),
        _public_tool(
            "get_source_coverage",
            "Get public corpus and source coverage",
            (
                "Return the shared public coverage projection: full official ACM catalogue "
                "counts and freshness, indexed and advertised caller-report routes, enabled "
                "reputation feeds, unavailable reasons, and corpus publication boundaries. "
                "Source count is not a trust or safety score."
            ),
            _EMPTY_OBJECT_SCHEMA,
        ),
        _public_tool(
            "get_methodology",
            "Get CallerSignal risk methodology",
            (
                "Return the versioned four-state risk policy and its safety invariants. "
                "Lookup popularity never becomes reputation evidence."
            ),
            _EMPTY_OBJECT_SCHEMA,
        ),
        _protected_tool(
            "create_private_watch",
            "Create a private number watch",
            "Create a consented private watch after OAuth contact verification.",
            "callersignal.watch:write",
            destructive=False,
            input_schema=_watch_create_schema(),
        ),
        _protected_tool(
            "delete_private_watch",
            "Delete a private number watch",
            "Permanently delete a verified private watch and its retained private state.",
            "callersignal.watch:delete",
            destructive=True,
            input_schema=_delete_schema("subscription_id"),
        ),
        _protected_tool(
            "submit_organization_portfolio",
            "Submit an organisation number portfolio",
            (
                "Submit a bounded official-number declaration after OAuth and domain-control "
                "consent. Submission never proves that an individual call originated there."
            ),
            "callersignal.organizations:write",
            destructive=False,
            input_schema=_organization_submit_schema(),
        ),
        _protected_tool(
            "delete_organization_portfolio",
            "Delete an organisation number portfolio",
            "Permanently delete a verified organisation declaration and retained private state.",
            "callersignal.organizations:delete",
            destructive=True,
            input_schema=_delete_schema("organization_id"),
        ),
    ]


def call_public_tool(
    name: str,
    arguments: Mapping[str, Any],
    *,
    lookup_service: LookupService,
    http_application: LookupHTTPApplication,
) -> dict[str, Any]:
    """Call one public tool without creating a second product truth path."""
    if name == "lookup_phone_number":
        return call_lookup_tool(arguments, lookup_service=lookup_service)
    if name == "list_public_campaigns":
        error = _require_no_arguments(arguments)
        if error:
            return error
        return _http_tool_result(http_application, "/v1/campaigns")
    if name == "get_public_campaign":
        if set(arguments) != {"campaign_id"}:
            return _tool_error("Exactly one campaign_id is required.")
        campaign_id = arguments.get("campaign_id")
        if not isinstance(campaign_id, str) or not _CAMPAIGN_ID.fullmatch(campaign_id):
            return _tool_error("campaign_id must be a valid opaque CallerSignal campaign id.")
        return _http_tool_result(http_application, f"/v1/campaigns/{campaign_id}")
    if name == "get_source_coverage":
        error = _require_no_arguments(arguments)
        if error:
            return error
        return _http_tool_result(http_application, "/v1/coverage")
    if name == "get_methodology":
        error = _require_no_arguments(arguments)
        if error:
            return error
        return _tool_success(methodology_contract())
    return _tool_error("Unknown public tool name.")


def methodology_contract() -> dict[str, Any]:
    """Return the compact machine-readable risk policy documented in methodology.md."""
    return {
        "schema_version": "1.0.0",
        "kind": "risk_methodology",
        "methodology_version": "1.0.0",
        "risk_states": [
            {
                "state": "official_warning",
                "minimum_evidence": "one current applicable official regulator warning",
                "meaning": "An authoritative source explicitly warns about the displayed value.",
            },
            {
                "state": "elevated_signals",
                "minimum_evidence": "two distinct current eligible sources with one pattern",
                "meaning": "Independent public observations support one harmful-activity pattern.",
            },
            {
                "state": "no_risk_evidence",
                "minimum_evidence": "one current eligible risk-capable source returning no match",
                "meaning": "Eligible sources returned no match; this is not a safety verdict.",
            },
            {
                "state": "insufficient_evidence",
                "minimum_evidence": "default when a stronger state is unsupported",
                "meaning": (
                    "Coverage, freshness, rights, availability, or consistency is insufficient."
                ),
            },
        ],
        "subject_semantics": "calls_displaying_numbers_or_bounded_patterns",
        "caller_id_spoofing_residual_risk": True,
        "lookup_popularity_used_for_reputation": False,
        "identity_claims_supported": False,
        "source_policy": "official, explicitly licensed, or first-party moderated evidence only",
    }


def _public_tool(
    name: str,
    title: str,
    description: str,
    input_schema: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": deepcopy(input_schema),
        "outputSchema": deepcopy(_PUBLIC_OUTPUT_SCHEMA),
        "annotations": _read_annotations(),
    }


def _protected_tool(
    name: str,
    title: str,
    description: str,
    scope: str,
    *,
    destructive: bool,
    input_schema: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": (
            f"{description} Requires explicit consent and OAuth scope {scope}. "
            "The hosted operation is locked until a production OAuth issuer and audience "
            "validator are configured."
        ),
        "inputSchema": deepcopy(input_schema),
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": destructive,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "_meta": {
            "callersignal.dev/auth": {
                "requiredScopes": [scope],
                "consentRequired": True,
                "availability": "locked_until_oauth_provider_configured",
            }
        },
    }


def _read_annotations() -> dict[str, bool]:
    return {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def _watch_create_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "number",
            "contact_channel",
            "contact",
            "consent_receipt",
            "idempotency_key",
        ],
        "properties": {
            "number": {"type": "string", "minLength": 1, "maxLength": 64},
            "origin_region": {"type": ["string", "null"], "pattern": "^[A-Z]{2}$"},
            "contact_channel": {"enum": ["email"]},
            "contact": {"type": "string", "minLength": 3, "maxLength": 254},
            "consent_receipt": {"type": "string", "minLength": 16, "maxLength": 256},
            "idempotency_key": {"type": "string", "minLength": 16, "maxLength": 128},
        },
    }


def _organization_submit_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "domain",
            "declared_numbers",
            "administrator_contact",
            "consent_receipt",
            "idempotency_key",
        ],
        "properties": {
            "domain": {"type": "string", "minLength": 3, "maxLength": 253},
            "declared_numbers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "uniqueItems": True,
                "items": {"type": "string", "pattern": "^\\+[1-9][0-9]{6,14}$"},
            },
            "administrator_contact": {
                "type": "string",
                "minLength": 3,
                "maxLength": 254,
            },
            "consent_receipt": {"type": "string", "minLength": 16, "maxLength": 256},
            "idempotency_key": {"type": "string", "minLength": 16, "maxLength": 128},
        },
    }


def _delete_schema(identifier: str) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [identifier, "consent_receipt", "idempotency_key"],
        "properties": {
            identifier: {"type": "string", "minLength": 8, "maxLength": 128},
            "consent_receipt": {"type": "string", "minLength": 16, "maxLength": 256},
            "idempotency_key": {"type": "string", "minLength": 16, "maxLength": 128},
        },
    }


def _require_no_arguments(arguments: Mapping[str, Any]) -> dict[str, Any] | None:
    return _tool_error("This tool accepts no arguments.") if arguments else None


def _http_tool_result(application: LookupHTTPApplication, path: str) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def start_response(status: str, headers: Iterable[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        application(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": path,
                "QUERY_STRING": "",
                "wsgi.input": BytesIO(),
            },
            start_response,
        )
    )
    payload = json.loads(body)
    if not str(captured["status"]).startswith("200"):
        return _tool_error(payload.get("error", {}).get("message", "Public record unavailable."))
    return _tool_success(payload)


def _tool_success(payload: Mapping[str, Any]) -> dict[str, Any]:
    public = deepcopy(dict(payload))
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(public, sort_keys=True, ensure_ascii=False),
            }
        ],
        "structuredContent": public,
        "isError": False,
    }


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}
