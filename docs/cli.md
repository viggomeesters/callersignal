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

The human view starts with the interpreted country, local and international presentations, then shows evidence, unknowns, confidence, and spoofing-aware residual risk. A displayed number is never presented as proof of the caller.

## Stable JSON

Pass `--json` for the shared versioned result used by every surface:

```bash
PYTHONPATH=src uv run python -m callersignal.cli lookup "0906-8844" --region NL --json
```

The emitted object validates against [`lookup-result.schema.json`](../schemas/lookup-result.schema.json). JSON output contains no extra CLI-only fields. IDs and timestamps describe the individual lookup, so consumers should compare contract fields rather than expect byte-identical output across separate requests.

## Exit behavior

- Successful lookups, including explicit unknown or unavailable outcomes, exit with status `0` because the lookup contract was produced.
- Invalid CLI grammar and national input without `--region` exit with status `2` and actionable guidance on standard error.
- Source failures are represented inside the result as typed gaps; upstream exception text is not exposed.
