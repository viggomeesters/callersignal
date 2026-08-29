# Changelog

All notable changes to CallerSignal are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No changes have been recorded after v0.2.0.

## [0.2.0] - 2026-08-29

### Added

- Country-aware normalization, immutable evidence records, and fail-closed NL, GB, and US numbering-context adapters backed by attributed public-safe fixtures.
- One versioned lookup and calibrated four-state risk contract shared by the CLI, stdio MCP, Streamable HTTP MCP, HTTP API, and responsive web interface.
- Caller-campaign, structured report, privacy-thresholded aggregation, replaceable storage, private watch, and verified organisation declaration contracts with correction and deletion paths.
- An action-oriented public result with text-and-icon risk states, exact coverage recency, a three-step response checklist, eligible campaign history, and progressive technical disclosure.
- An honest public corpus ledger showing enabled jurisdictions, risk-capable sources, ingest freshness, coverage gaps, publication thresholds, corrections, and methodology version without lookup-popularity or raw-report totals.
- A hosted MCP endpoint at `https://callersignal.vercel.app/mcp` with five anonymous read tools, current discovery, legacy initialization, and four consent- and scope-declared mutation tools that remain locked without a production OAuth provider.
- Privacy-safe operational metrics and incident, deletion, correction, takedown, and abuse runbooks.

### Safety and evidence boundaries

- Public risk uses only current official, explicitly licensed, or approved first-party moderated evidence. Lookup volume and one unverified report never affect reputation.
- `official_warning`, `elevated_signals`, `no_risk_evidence`, and `insufficient_evidence` preserve their source, freshness, confidence, reason, gap, action, and caller-ID spoofing context across every interface.
- CallerSignal does not identify a caller or subscriber, prove call origin, guarantee reachability, or label a number safe. Campaign membership describes displayed values only.
- The live public service is read-only. Report ingestion, watch persistence, organisation publication, and outbound notifications remain disabled until production data, OAuth, consent, moderation, rate, retention, objection, correction, and deletion controls are configured and reviewed.

### Known gaps

- The current corpus has three enabled numbering-context sources and no enabled risk-capable source or eligible public campaign. A no-match result is therefore not a safety verdict.
- `wieheeftmijgebeld_nl` remains a disabled permission-required source with zero permitted fields; no unlicensed third-party caller-report database is copied or farmed.
- Vercel deployment is manual because GitHub integration is not connected. GitHub Actions is configured but remote execution remains unavailable under the repository owner's account setting; `make check` is the proven equivalent gate.

### Upgrade instructions

- Existing v0.1.0 users can pull v0.2.0 without a lookup-schema migration; schema version `1.0.0` remains compatible.
- Run `uv sync --locked --dev`, `npm ci`, and `make check` after upgrading.
- Local stdio clients keep `PYTHONPATH=src uv run python -m callersignal.mcp_server`. Streamable HTTP clients can add `https://callersignal.vercel.app/mcp`; public tools need no bearer token.


## [0.1.0] - 2026-08-26

### Added

- Public repository foundation with MIT licensing, contribution, conduct, support, and security policies.
- Repo-local `.go` workflow with a durable product vision, architecture principles, five foundation tasks, and sixteen dependency-ordered product tasks.
- Schema-validated design contract covering agent-first interfaces, engineering principles, public-safety boundaries, maturity, and acceptance scoring.
- Architecture, fresh-clone onboarding, data-safety, agent-execution, and implementation-plan documentation.
- Locked Python development tooling and a single local repository gate for tests, schemas, docs, workflow state, assets, privacy, and repository consistency.
- Distinctive CallerSignal repository hero and social-preview assets with recorded visual inspection.

### Not included

- Phone-number lookup, normalization, evidence adapters, CLI, MCP, HTTP, web, community reporting, and reputation behavior remain open product work.

[0.1.0]: https://github.com/viggomeesters/callersignal/releases/tag/v0.1.0
[0.2.0]: https://github.com/viggomeesters/callersignal/releases/tag/v0.2.0
[Unreleased]: https://github.com/viggomeesters/callersignal/compare/v0.2.0...HEAD
