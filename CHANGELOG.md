# Changelog

All notable changes to CallerSignal are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Versioned phone-number, source-evidence, lookup-result, and call-report contracts.
- Country-aware normalization, immutable evidence records, and fail-closed NL, GB, and US numbering adapters backed by public-safe fixtures.
- One read-only lookup service shared by CLI, MCP, HTTP, and responsive web interfaces.
- A thin Vercel WSGI/static deployment adapter with same-origin routing and response-security headers.
- An owned production deployment at `https://callersignal.vercel.app/` with a privacy-safe health endpoint.

### Not included

- Public report ingestion, reputation aggregation, and broader production operations remain gated work.

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
[Unreleased]: https://github.com/viggomeesters/callersignal/compare/v0.1.0...HEAD
