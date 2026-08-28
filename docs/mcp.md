# MCP lookup server

CallerSignal exposes one read-only MCP tool, `lookup_phone_number`, over the standard stdio transport. The server is dependency-free beyond the repository runtime and delegates every lookup to `LookupService`; it does not maintain a second truth path or persist lookup history.

## Start the server

From the repository root:

```bash
PYTHONPATH=src uv run python -m callersignal.mcp_server
```

Configure an MCP client to launch `uv` with arguments `run python -m callersignal.mcp_server`, set `PYTHONPATH` to `src`, and use the repository root as the process working directory. The server writes only newline-delimited JSON-RPC messages to standard output and writes no lookup data to standard error.

## Tool contract

`lookup_phone_number` accepts:

- `number` — required national-format or `+`-prefixed international input, one to 64 characters;
- `origin_region` — optional uppercase ISO alpha-2 code, but required whenever `number` is national-format.

The tool description instructs agents to state which origin country they are checking before presenting the result. International input determines its country independently. The annotations declare the tool read-only and closed-world because the current adapters query pinned public fixtures without runtime network access.

The tool advertises a bundled JSON Schema 2020-12 `outputSchema` derived from [`lookup-result.schema.json`](../schemas/lookup-result.schema.json). A successful call returns the same lookup object twice as required for compatibility:

- `structuredContent` contains the machine-readable lookup result;
- the first text content block contains its JSON serialization for older clients.

Invalid arguments and missing national-origin context return `isError: true` without `structuredContent`. Source unavailability is a successful lookup contract containing typed evidence gaps, not a protocol failure.

Agents must present `assessment.risk` as the risk conclusion and preserve its calibrated language. `no_risk_evidence` means eligible sources returned no match, not that the number or caller is safe; `insufficient_evidence` must never be upgraded from numbering context or lookup popularity. `sources_checked[].risk_capable`, reason codes, evidence IDs, and the spoofing-aware residual-risk text provide the auditable explanation. The full decision policy is documented in the [risk assessment methodology](methodology.md).

## Protocol support

The stdio server implements MCP initialization, initialized notifications, ping, tool listing, and tool calls using newline-delimited JSON-RPC 2.0. It supports protocol revisions `2025-11-25` and `2025-06-18`, advertises no list-change notifications, and rejects operational requests before initialization completes.

The server intentionally exposes no resources, prompts, sampling, write tools, report ingestion, or remote HTTP transport. Remote website access uses the separately tested read-only HTTP adapter.
