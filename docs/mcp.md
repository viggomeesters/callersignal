# MCP servers

CallerSignal exposes the same evidence and uncertainty contracts through a local stdio server and a stateless Streamable HTTP server. Neither transport maintains a lookup history or computes a browser-only verdict.

## Hosted endpoint

The production endpoint is `https://callersignal.vercel.app/mcp`. It supports the current stateless MCP revision `2026-07-28` through `server/discover` and remains compatible with `initialize` clients using `2025-11-25` or `2025-06-18`. Each JSON-RPC message is one HTTP `POST`; this deployment does not offer a server-sent-event stream, so `GET /mcp` returns `405 Method Not Allowed` as permitted by Streamable HTTP.

The implementation follows the official [Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), including JSON responses, `202` for accepted notifications, protocol-version validation, bounded request bodies, and Origin validation. It is stateless and issues no session identifier. Every response uses `Cache-Control: no-store`.

Add the deployed service to Codex with:

```console
codex mcp add callersignal --url https://callersignal.vercel.app/mcp
codex mcp get callersignal
```

No bearer token is needed for the five public read tools. This command is the locally verified syntax from `codex mcp add --help`; clients that support Streamable HTTP can use the same endpoint URL.

### Public tools

| Tool | Purpose | Data boundary |
| --- | --- | --- |
| `lookup_phone_number` | Normalize with explicit country semantics and return canonical evidence, gaps, calibrated risk, and action | Pinned rights-approved public sources; no lookup persistence |
| `list_public_campaigns` | List campaigns that pass aggregate evidence and publication gates | Exact public HTTP campaign catalogue |
| `get_public_campaign` | Read one eligible campaign by opaque identifier | Public aggregate fields and exact source coverage only |
| `get_source_coverage` | Read complete ACM catalogue coverage plus indexed, advertised, enabled, and unavailable reputation-source coverage | Exact committed transparency snapshot; no raw number or report inventory |
| `get_methodology` | Read the versioned four-state risk policy | Machine-readable form of [`methodology.md`](methodology.md) |

All five tools advertise `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, and `openWorldHint: false`. “Closed world” means they read CallerSignal's bounded published corpus; it does not imply complete coverage or a safe-number guarantee.

The lookup tool requires `origin_region` for national-format input. Before calling it, an agent should say which country interpretation it is checking. International `+` input determines the country independently. The returned `assessment.risk` is the canonical risk conclusion. `no_risk_evidence` is not proof of safety, and numbering context alone remains `insufficient_evidence`.

### Protected tools are discoverable but locked

The server lists four locked protected operations so clients can inspect their exact risk and permission boundary:

| Tool | OAuth scope | Destructive hint | Current availability |
| --- | --- | ---: | --- |
| `create_private_watch` | `callersignal.watch:write` | false | Locked |
| `delete_private_watch` | `callersignal.watch:delete` | true | Locked |
| `submit_organization_portfolio` | `callersignal.organizations:write` | false | Locked |
| `delete_organization_portfolio` | `callersignal.organizations:delete` | true | Locked |

Every protected schema requires a consent receipt and idempotency key. Calls are intercepted at the HTTP boundary and return a privacy-safe `401 Unauthorized` with a scoped `WWW-Authenticate` challenge. Tool handlers are never reached.

Protected Resource Metadata is published at `/.well-known/oauth-protected-resource` and `/.well-known/oauth-protected-resource/mcp`. It names the canonical resource and scopes but reports `callersignal.dev/authorization_status: not_configured` and an empty `authorization_servers` list. That is deliberate: CallerSignal does not invent an issuer, accept unvalidated bearer tokens, or pretend that OAuth is ready. The [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) requires issuer discovery, audience-bound token validation, and least-privilege scopes before protected operations can run. A future release must configure a real OAuth 2.1 issuer, PKCE/client discovery, resource indicators, audience validation, consent, rate, privacy, retention, and deletion controls before changing this status.

## Remote protocol smoke tests

Start the local HTTP transport on loopback only:

```console
PYTHONPATH=src uv run python -m callersignal.remote_mcp
```

Discover its supported revisions:

```console
curl --silent --show-error \
  --request POST http://127.0.0.1:8766/mcp \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --header 'MCP-Protocol-Version: 2026-07-28' \
  --data '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{}}}'
```

Call the lookup tool with the NANPA-reserved fictional number:

```console
curl --silent --show-error \
  --request POST http://127.0.0.1:8766/mcp \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"lookup_phone_number","arguments":{"number":"202-555-0147","origin_region":"US"}}}'
```

Run the deterministic protocol gate:

```console
uv run pytest tests/integration/test_remote_mcp.py -q
make check
```

The integration suite covers discovery, initialization, tool listing, representative public calls, canonical campaign parity, the committed transparency snapshot, unauthorized protected calls, arbitrary bearer-token rejection, Origin and protocol rejection, notification handling, no-store headers, privacy-safe errors, Vercel rewrites, and protected-resource metadata.

### Live production proof

Deployment `dpl_8t4545JvbgcDtbCqZKiRw9bsVfHm`, built from pushed commit `2002a63`, reported `Ready` and owned the stable `https://callersignal.vercel.app` alias on 29 August 2026. Direct alias readback proved:

- homepage and `/healthz` returned `200`, with health status `ok`;
- `server/discover` returned `2026-07-28`, `2025-11-25`, and `2025-06-18`;
- legacy `initialize` negotiated `2025-11-25`;
- `tools/list` returned all five public reads and four locked protected operations;
- the NANPA-reserved lookup returned its expected fictional canonical value with `insufficient_evidence`;
- campaign research returned the canonical empty eligible catalogue, and source coverage returned the committed three-enabled-source snapshot;
- every public MCP call and protected failure returned `Cache-Control: no-store`;
- a protected watch call returned `401` with only `callersignal.watch:write` in its challenge;
- an unapproved Origin returned `403`, `GET /mcp` returned the documented `405`, and protected-resource metadata reported OAuth as not configured;
- Vercel readback listed `api/mcp` beside the lookup, campaigns, and health functions.

These checks used only reserved fictional input and recorded no request bodies or lookup history. A later release deployment may replace the alias owner while this acceptance deployment remains immutable.

## Local stdio server

The stdio transport remains useful for local clients and exposes `lookup_phone_number` plus argument-free `get_source_coverage`:

```console
PYTHONPATH=src uv run python -m callersignal.mcp_server
```

Configure a client to launch `uv` with `run python -m callersignal.mcp_server`, set `PYTHONPATH=src`, and use the repository root as its working directory. The process writes only newline-delimited JSON-RPC to standard output and writes no lookup data to standard error.

Both stdio tools return the same canonical object in `structuredContent` and as JSON text for older clients. Invalid arguments return `isError: true` without structured content. Source unavailability remains a successful lookup containing typed evidence gaps, not a protocol failure. Coverage lists official ACM totals and explicit reputation activation gaps; it never accepts a phone number and never presents source volume as trust.

## Deployment and observability boundary

Vercel bundles the shared source, schemas, pinned fictional/public-safe fixtures, and committed transparency snapshot. The MCP endpoint delegates lookup to `LookupService` and campaign reads to the canonical HTTP application; it does not maintain a parallel database or assessment policy.

Production observability is metadata-only: route, method, status class, duration bucket, and bounded source-health dimensions. Do not log authorization headers, JSON-RPC bodies, raw or normalized numbers, contacts, consent receipts, organisation declarations, prompt/response text, IP addresses, or lookup histories. Deployment does not authorize report collection, watch persistence, organisation publication, or any other protected mutation.
