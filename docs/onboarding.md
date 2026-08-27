# Developer and Agent Onboarding

## What you are joining

CallerSignal is an agent-first international phone-number intelligence project. The repository foundation and read-only lookup wedge are implemented: one domain service powers CLI, MCP, HTTP, and web surfaces for pinned public-safe NL, GB, and US numbering evidence. The `.go` backlog keeps privacy-sensitive reporting, reputation, production operations, and release work explicitly separate.

## Prerequisites

- Git
- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js 22 or newer for the web unit suite
- Network access on the first `./go` run so the pinned workflow stack can be cached

No private account, API key, database, or proprietary dataset is required for repository validation.

## Fresh-clone setup

```console
git clone https://github.com/viggomeesters/callersignal.git
cd callersignal
make check
npm --prefix web ci
npm --prefix web test
./go status .
./go next .
```

`make check` synchronizes the locked development environment and runs every repository gate, including the Python and web suites. The GitHub workflow is configured to invoke the same command. The `go` launcher reads `.go/project.json`, installs the exact required stack version in a user cache, and validates repo-local workflow state before routing commands.

## Read in this order

1. [`README.md`](../README.md) for the promise and maturity.
2. [`docs/vision.json`](vision.json) for normative product and safety principles.
3. [`docs/architecture.md`](architecture.md) for boundaries and target flow.
4. [`docs/data-safety.md`](data-safety.md) before touching numbers, evidence, sources, reports, logs, or metrics.
5. [`docs/implementation-plan.md`](implementation-plan.md) for the dependency-ordered backlog.
6. [`AGENTS.md`](../AGENTS.md) before an agent changes repository state.

## Choose and execute work

Run `Go` in an agent environment that supports the repository workflow, or inspect the next eligible item with:

```console
./go validate .
./go next .
```

Claim one task only. Treat its `scope.modify`, acceptance criteria, and verification commands as a bounded contract. Preserve unrelated changes. When complete, run the task-specific verification and `make check`, then finish with structured evidence and obtain an explicit review decision. The process is described in [`docs/agent-contract.md`](agent-contract.md).

Do not implement a downstream surface before its dependencies are done. CLI, MCP, HTTP, and web already share the same lookup result; preserve that boundary rather than adding surface-specific business logic.

## Development conventions

- Canonical structured contracts are JSON Schema and typed domain records.
- Python development tooling is locked with `uv.lock`; update it with `uv lock` only when dependencies change.
- Formatting and lint rules live in `pyproject.toml`.
- Tests use only public-safe fixtures. A NANPA `555-01xx` fictional number is suitable for documentation; real personal numbers are not.
- New source adapters document authority, reuse basis, permitted fields, freshness, and portability limits.
- User-visible conclusions are calm, evidence-led, and honest about gaps.
- Runtime files, caches, local environments, credentials, downloaded datasets, recordings, and private exports stay untracked.

## Useful commands

```console
make check              # complete local gate
make test               # repository contract tests
make lint               # static checks
npm --prefix web test   # browser-logic unit tests
make validate-go        # repo-local workflow validation
./go status .           # task and workflow summary
./go next .             # next dependency-eligible task
git diff --check        # whitespace and conflict-marker check
```

## Before requesting review

Confirm that the scoped acceptance criteria are demonstrably met, the relevant verification commands pass, `make check` passes, public copy does not overstate maturity, no real personal number or secret appears in the diff, generated state remains ignored, and documentation changes match contract changes.

If a change affects legal reuse, personal data, public reporting, moderation, retention, identity claims, source publication, or repository visibility, stop and request an explicit product, privacy, or publication decision.
