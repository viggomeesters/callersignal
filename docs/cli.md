# Command-line lookup

The CallerSignal CLI is a read-only presentation layer over `LookupService`. It does not query sources independently, compute a different verdict, persist lookup history, or accept public reports.

## Run from a clone

Until CallerSignal is packaged for distribution, invoke the module through the repository environment:

```bash
PYTHONPATH=src uv run python -m callersignal.cli lookup "0906-8844" --region NL
```

National-format input requires an explicit ISO alpha-2 origin region. International E.164 input carries its own country calling code:

```bash
international="+1""202""555""0147"
PYTHONPATH=src uv run python -m callersignal.cli lookup "$international"
```

The human view starts with the interpreted country, local and international presentations, then shows evidence, unknowns, evidence confidence, and spoofing-aware residual risk. A displayed number is never presented as proof of the caller. The stable JSON view also carries the calibrated `assessment.risk` state; its four states and thresholds are defined in the [risk assessment methodology](methodology.md).

## Stable JSON

Pass `--json` for the shared versioned result used by every surface:

```bash
PYTHONPATH=src uv run python -m callersignal.cli lookup "0906-8844" --region NL --json
```

The emitted object validates against [`lookup-result.schema.json`](../schemas/lookup-result.schema.json). JSON output contains no extra CLI-only fields. IDs and timestamps describe the individual lookup, so consumers should compare contract fields rather than expect byte-identical output across separate requests.

In JSON, `assessment.confidence` refers only to the strength of the available source observations. Use `assessment.risk` for risk presentation and retain its headline, reason codes, recommended action, and explicit uncertainty.

## Source coverage

Use the agent-friendly human readout to separate official numbering context, the enabled unverified FCC complaint aggregate, and unavailable commercial coverage:

```bash
PYTHONPATH=src uv run python -m callersignal.cli coverage
```

It reports the full ACM imported and lookup-compatible range counts, destination and status coverage, freshness, exact FCC rolling window and build/source times, keyed-number and observation counts, nuisance/robocall split, indexed caller-report services, advertised licensing routes, enabled sources, and grouped unavailable reasons. It says explicitly that FCC complaints are consumer-selected and unverified, repeated observations are not corroboration, and coverage counts are not trust or safety scores.

`coverage --json` emits the exact committed `corpus_transparency` object returned by HTTP `GET /v1/coverage`, stdio and hosted MCP `get_source_coverage`, and rendered by the website. It accepts no number, requester field, or source credential.

## Exit behavior

- Successful lookups, including explicit unknown or unavailable outcomes, exit with status `0` because the lookup contract was produced.
- Invalid CLI grammar and national input without `--region` exit with status `2` and actionable guidance on standard error.
- Source failures are represented inside the result as typed gaps; upstream exception text is not exposed.
