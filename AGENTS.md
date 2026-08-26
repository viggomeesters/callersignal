# Agent Instructions

## Repository contract

CallerSignal uses repo-local `.go` state as the source of truth. Never mirror workflow state to a vault or global task queue. Read `.go/project.json`, `.go/vision.json`, `.go/hierarchy.json`, `.go/architecture-principles.json`, the selected task, and `docs/vision.json` before changing product or foundation state.

Run `./go validate .`, `./go status .`, and `./go next .`. Claim exactly one dependency-eligible task. Its `scope.modify`, acceptance criteria, and verification commands bound the work. Preserve unrelated and user-owned changes; do not use destructive reset or broad cleanup.

## Required completion loop

1. Implement only the claimed task.
2. Update tests, schemas, and public docs with contract changes.
3. Run every task verification command and `make check`.
4. Inspect the diff for secrets, personal data, unsafe fixtures, generated state, unfinished markers, and overclaimed maturity.
5. Finish with structured evidence containing changed files, exact verification commands with `rc=0`, and critic outcome.
6. Record an explicit approved or needs-fix review decision.

Canonical task and ledger events belong in `.go`; locks, per-run directories, resume files, and latest-run snapshots do not. The pinned launcher may cache the workflow stack outside the repository.

## Product boundaries

- A displayed number is not proof of caller, subscriber, provider, safety, reachability, or live location.
- National input requires explicit origin-region context; never infer it from locale or deployment.
- Keep number facts, source observations, identity claims, reports, lookup demand, and assessments separate.
- Every assessment exposes provenance, retrieval time, confidence, reason codes, gaps, and residual uncertainty.
- Source failure, staleness, conflict, or unsupported coverage fails closed to a typed unknown.
- Lookup popularity cannot affect reputation.
- Never scrape or publish a source without documented authority and reuse rights.

## Public-repository safety

Never commit real personal phone numbers, contacts, call histories, reports, requester identities, IP addresses, recordings, private screenshots, exports, downloaded private datasets, tokens, credentials, cookies, private keys, `.env` files, or raw sensitive logs. Use reserved fictional values or structural redaction. Keep sensitive evidence out of `.go` events as well as source files.

Stop for explicit direction when a change requires uncertain data rights, real-person identity, report ingestion, lookup-history retention, a privacy or moderation policy, production credentials, repository visibility changes, or publication beyond an approved release.

## Validation and release

`make check` is the canonical local gate. GitHub Actions are intentionally not used. A public release additionally requires strict `repo-complete` validation, visual inspection, privacy and Git-history scans, a clean tree, and GitHub readback of visibility, default branch, metadata, tag, and release.

See [`docs/agent-contract.md`](docs/agent-contract.md) for the full execution and evidence standard.
