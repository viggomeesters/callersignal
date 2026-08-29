# HTTP lookup API

CallerSignal exposes the canonical read-only lookup result through a small WSGI application. The adapter delegates every product decision to `LookupService`: it parses HTTP input, applies an optional request-admission hook, serializes the shared result, and does nothing else.

## Run locally

Start a development-only WSGI server from the repository root:

```bash
PYTHONPATH=src uv run python -c \
  'from wsgiref.simple_server import make_server; from callersignal.http_api import application; make_server("127.0.0.1", 8080, application).serve_forever()'
```

Then request a national-format fixture with an explicit origin:

```bash
curl --get http://127.0.0.1:8080/v1/lookup \
  --data-urlencode 'number=0906-8844' \
  --data-urlencode 'origin_region=NL'
```

International-format input carries its own country context and needs no `origin_region`. Clients must URL-encode the leading `+` as `%2B` or use an equivalent query-string encoder.

## Contract

`GET /v1/lookup` accepts exactly these query parameters:

- `number` — required exactly once, with one to 64 characters;
- `origin_region` — optional uppercase ISO alpha-2 code, required for national-format input.

A successful response is the unchanged versioned object defined by [`lookup-result.schema.json`](../schemas/lookup-result.schema.json), identical in meaning and fields to CLI JSON and MCP `structuredContent`. Domain-level invalid, possible, unsupported, no-match, unavailable, and evidence-gap states remain successful lookup results so clients can render their provenance and uncertainty.

The canonical phone-risk result is `assessment.risk`, with one of `official_warning`, `elevated_signals`, `no_risk_evidence`, or `insufficient_evidence`. It includes supporting IDs and a stable recommended action. `assessment.confidence` describes the confidence of source evidence, not caller safety. Each source check exposes `risk_capable`; numbering-plan sources are intentionally false. See the [risk assessment methodology](methodology.md) for exact thresholds and negative invariants.

`GET /v1/coverage` accepts no query parameters and returns the committed `corpus_transparency` projection also used by CLI, MCP, and the website. It exposes privacy-safe ACM catalogue counts, register-status and destination coverage, digest and freshness; exact FCC rolling-window, build, source-update, keyed-number, observation, rejection, and neutral category totals; caller-report index and licensing-route counts; enabled reputation-source count; limitations; and explicit unavailable reasons. It contains no raw or keyed number inventory, range holder, report row, requester data, credential, lookup demand, or safety score. FCC totals are explicitly unverified one-source coverage, not corroboration.

Malformed transport input uses a small versioned `http_error` object. The adapter returns `400` for invalid query semantics, `404` for unknown routes, `405` for non-GET methods, `429` when an injected request gate denies admission, `503` when that gate fails, and a generic `500` when an unexpected lookup failure escapes. Error messages never echo the submitted number.

`GET /healthz` reports only process readiness. Every response is JSON, sets `Cache-Control: no-store`, and prevents MIME sniffing. Cross-origin access is intentionally not enabled; the public site consumes the API on the same origin.

## Privacy-safe operational ports

`create_app` accepts two optional ports, both disabled or permissive by default:

- `request_gate` is a zero-argument, request-scoped admission callback. A deployment wrapper can bind its own rate-limit context without passing personal data into the lookup domain.
- `telemetry` receives only a frozen `LookupMetric` containing schema version, route name, coarse outcome, and HTTP status. It never receives the phone number, origin region, IP address, lookup result, evidence, or requester identity.

Telemetry runs after the response has been constructed, cannot feed data back into `LookupService`, and is failure-isolated: a telemetry exception does not change the HTTP response or any reputation state. CallerSignal does not persist lookup history by default.

## Deployment boundary

The exported `application` object is a standard WSGI callable. Production hosting should add only thin platform entrypoints, same-origin routing, and an independently reviewed rate-limit implementation. `api/coverage.py` maps Vercel to the canonical coverage route; it does not rebuild or broaden the public projection. Hosting must not duplicate lookup logic, log raw query strings, or turn lookup demand into evidence or reputation.
