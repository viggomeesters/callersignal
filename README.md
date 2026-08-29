# CallerSignal

![CallerSignal repository hero](assets/hero.png)

**Evidence-backed international phone-number intelligence for agents, CLIs, MCP clients, and the web.**

CallerSignal is an agent-first open-source project for answering “what can we responsibly say about this displayed phone number?” It normalizes a number with explicit country context, checks lawful country-specific evidence, and returns sources, gaps, confidence, and residual uncertainty instead of guessing a caller's identity.

> **Current maturity:** `v0.3.0` is persistently hosted at [callersignal.vercel.app](https://callersignal.vercel.app/). It implements the read-only NL, GB, and US lookup wedge across CLI, stdio MCP, Streamable HTTP MCP, HTTP, and web. Production NL lookups use a validated, holder-free projection of the complete pinned ACM register. The service does not identify a caller, query live subscriber data, accept reports, persist watches, or publish organisation declarations.

The durable direction is a hybrid reputation model: official evidence first, then explicitly licensed or first-party moderated observations only after source-rights, privacy, and abuse gates pass. Every shared result now contains one calibrated risk state: `official_warning`, `elevated_signals`, `no_risk_evidence`, or `insufficient_evidence`. The website leads with that state, its basis, and a concrete next action while preserving the evidence and uncertainty underneath. `no_risk_evidence` requires a current eligible risk-capable source and never means that a number is safe; numbering context alone remains `insufficient_evidence`.

> **Corpus reality, 29 August 2026:** the official ACM catalogue contains 74,984 ranges, of which 73,409 support canonical lookup. CallerSignal indexes 15 caller-report services and four advertised licensing routes, but enables zero reputation feeds and zero eligible public campaigns. “No matching evidence” therefore does not mean the displayed number is safe. See the versioned [corpus-transparency contract](docs/transparency.md).

## Usage: read-only lookup

A national-format input is never interpreted without an origin region. International input is normalized directly. Every interface renders the same versioned lookup result.

Use the [public website](https://callersignal.vercel.app/) or run any interface locally.

CLI example using a NANPA-reserved fictional number:

```console
PYTHONPATH=src uv run python -m callersignal.cli lookup "202-555-0147" --region US --json
```

The MCP server exposes the same result through `lookup_phone_number`:

```console
PYTHONPATH=src uv run python -m callersignal.mcp_server
```

```json
{
  "name": "lookup_phone_number",
  "arguments": {
    "number": "202-555-0147",
    "origin_region": "US"
  }
}
```

Inspect source coverage without submitting a number:

```console
PYTHONPATH=src uv run python -m callersignal.cli coverage
curl --fail-with-body https://callersignal.vercel.app/v1/coverage
```

CLI `coverage --json`, HTTP `GET /v1/coverage`, and both MCP transports' argument-free `get_source_coverage` tool return the same public-safe projection rendered by the website.

For a local same-origin website and API:

```console
PYTHONPATH=src uv run python tests/e2e/site_server.py
```

Then open `http://127.0.0.1:8765/`. The response contract preserves the raw input and interpretation context, provides canonical E.164 and national display forms, lists every source checked, and distinguishes evidence from gaps and assessments. It also states that caller ID can be spoofed: a displayed number is not proof of the caller, subscriber, provider, safety, or reachability. See the [CLI](docs/cli.md), [MCP](docs/mcp.md), [HTTP](docs/http-api.md), and [web](docs/web.md) guides.

## Why this repository exists

Existing “who called me?” experiences often lead with opaque labels, region assumptions, popularity, or unsupported identity claims. CallerSignal takes a narrower and more inspectable route:

- machine-readable contracts are canonical;
- country interpretation is explicit and reproducible;
- technical facts, source observations, lookup demand, reports, and assessments remain separate;
- every conclusion carries provenance, freshness, reason codes, confidence, gaps, and residual risk;
- unknown stays unknown when evidence cannot support a stronger answer.

The product wedge covers read-only official numbering evidence for the Netherlands, United Kingdom, and United States through shared CLI, MCP, HTTP, and web semantics. Caller-report enrichment remains disabled until compatible extraction and republication rights, credentials, privacy controls, correction, takedown, provenance, and operational gates are all proven.

## Repository map

| Path | Purpose |
| --- | --- |
| [`.go/`](.go/) | Canonical repo-local goals, principles, tasks, evidence, and workflow events |
| [`docs/vision.json`](docs/vision.json) | Schema-validated product, design, engineering, and public-safety contract |
| [`docs/architecture.md`](docs/architecture.md) | Implemented architecture, boundaries, flows, risks, and extension points |
| [`docs/implementation-plan.md`](docs/implementation-plan.md) | Dependency-ordered product backlog with acceptance and verification |
| [`docs/onboarding.md`](docs/onboarding.md) | Fresh-clone setup for developers and agents |
| [`docs/data-safety.md`](docs/data-safety.md) | Privacy, evidence, moderation, and publication boundaries |
| [`docs/transparency.md`](docs/transparency.md) | Reproducible corpus, source coverage, freshness, gaps, and publication thresholds |
| [`docs/agent-spec.md`](docs/agent-spec.md) | Shared agent behavior, four-state evaluations, deployment, and observability contract |
| [`schemas/`](schemas/) | Committed repository and versioned product contracts |
| [`scripts/check.sh`](scripts/check.sh) | One-command local repository gate |

## Installation

Prerequisites are Git, Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and Node.js 22 or newer. The pinned Go workflow stack bootstraps itself through the repository launcher.

```console
git clone https://github.com/viggomeesters/callersignal.git
cd callersignal
make check
./go status .
./go next .
```

`make check` installs only locked development dependencies and validates Python and web tests, schemas, documentation, assets, privacy rules, formatting, and `.go` state. It is the authoritative repository-local gate. See the complete [onboarding guide](docs/onboarding.md) and [agent contract](docs/agent-contract.md).

## Development: continue the backlog

The complete dependency-ordered foundation and first functional release backlog is implemented and reviewed. New work enters through the repo-local workflow rather than an undocumented queue. Read [`AGENTS.md`](AGENTS.md), then run:

```console
Go
```

In Codex this routes through the repo-local Go contract. From a shell, use `./go next .`, claim exactly one task, implement only its declared scope, run its verification commands, and finish it with evidence.

## Public-safety boundary

CallerSignal does not expose private subscriber identities, scrape personal profiles, infer a live location, or treat a valid or allocated range as proof of ownership. Lookup demand cannot affect reputation. Community reporting is deferred until legal, privacy, moderation, abuse, correction, and deletion controls exist.

Do not commit real personal phone numbers, private reports, credentials, raw lookup histories, recordings, screenshots containing personal data, or unlicensed datasets. Use reserved fictional numbers or explicit structural redaction. Read [`docs/data-safety.md`](docs/data-safety.md) before adding a source, fixture, report, log, or metric.

## Contributing and support

Contributions are welcome when they preserve the evidence and safety model. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md), follow the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md), and use [`SUPPORT.md`](SUPPORT.md) for support routes. Security and privacy issues belong in the private process documented in [`SECURITY.md`](SECURITY.md), not a public issue.

## License

CallerSignal is released under the [MIT License](LICENSE). You may use, modify, and distribute it under those terms. Release history is recorded in [`CHANGELOG.md`](CHANGELOG.md).
