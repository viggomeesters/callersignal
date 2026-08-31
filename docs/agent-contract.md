# Agent Contract

## Authority and source of truth

`.go` is CallerSignal's canonical work contract. The repository-local launcher and pinned stack version govern task routing. The explicit user request and the claimed task bound the work; neither broad autonomy nor a terminal instruction expands authority into product, privacy, publication, or external actions not already in scope.

Normative product and safety rules live in [`docs/vision.json`](vision.json). Architecture boundaries live in [`docs/architecture.md`](architecture.md). Scoped machine-readable architecture lives in `.go/architecture/briefs/`, append-only architecture lifecycle evidence in `.go/architecture/events.jsonl`, and governing decisions in `.go/decisions/events.jsonl`. When prose and a machine contract diverge, stop, repair the inconsistency in a scoped task, and validate both.

## Required execution loop

1. Read [`AGENTS.md`](../AGENTS.md), `.go/project.json`, `.go/vision.json`, `.go/hierarchy.json`, and `.go/architecture-principles.json`.
2. Resolve the highest annotated immutable stack release, inspect the tagged update dry run, and require `./go doctor` to report `exact_ref=true`, `compatible=true`, `ready=true`, and `development_override=false`.
3. Run `./go validate .`, `./go status .`, and `./go next .`.
4. Classify architecture impact before claim when deterministic signals or task intent touch sources, public contracts, integrations, trust boundaries, privacy, security, data, storage, migrations, deployment data, or measurable quality attributes.
5. For material or foundational work, run `./go architecture readback . --task-id <id> --json` and require accepted applicable briefs, accepted governing decisions, and measurable quality attributes. Stop for the named human gate required by foundational work or explicit decision/risk ownership.
6. Claim exactly one dependency-eligible task and inspect its full scope, acceptance, verification, and `GO_CONTEXT_JSON.applicable_architecture` contract.
7. Preserve unrelated or user-owned changes; do not use destructive reset or broad cleanup.
8. Implement only the task and architecture contracts. Update tests and documentation with behavior or contract changes.
9. Run every task verification command and `make check`.
10. For each applicable scope, record conformance checks for principles, governing decisions, and quality attributes. A deviation is not green; repair it or use a named-owner, reasoned, expiring waiver.
11. Inspect the diff for secrets, personal data, unsafe fixtures, generated state, placeholders, open deviations, expired waivers, and overclaimed maturity.
12. Finish with structured evidence naming changed files, exact verification commands and exit status, architecture conformance where applicable, and critic outcome.
13. Record an explicit `approved` or `needs_fix` review decision before treating the task as complete.

## Evidence standard

Evidence must be reproducible and specific. “Tests pass” is insufficient. Name the command, record `rc=0`, identify material changed files, and state how critical review was performed or why it was intentionally skipped. Never copy secrets, private data, real numbers, raw reports, or sensitive logs into `.go/evidence` or task history.

Architecture conformance references normal verification evidence instead of creating a second test system. Each applicable scope must independently account for its principles, decisions, and quality attributes. Automation may record technical conformance, but it may not self-declare named human approval or risk acceptance.

## Safety stops

Stop and request direction when work requires a new data source with uncertain reuse rights, a real-person identity claim, public report ingestion, retention of lookup histories, a change in repository visibility, external publication beyond an already approved release, a production credential, or a hard-to-reverse storage or moderation decision without an accepted contract.

The agent must fail closed on unavailable evidence, preserve unknowns, keep lookup demand out of reputation, and describe a number as displayed caller ID rather than the proven caller.

## Repository discipline

- Use `apply_patch` for intentional file edits and deterministic tools for generated lock or asset files.
- Keep canonical `.go` state tracked; keep locks, resumes, run snapshots, caches, and local environments ignored.
- Keep `make check` as the single validation truth; GitHub CI may invoke it but must not reimplement a divergent gate.
- Never commit `.env` files, private keys, credentials, downloaded private datasets, recordings, screenshots with personal data, or raw lookup exports.
- Keep commits scoped and reviewable. Release only from a clean tree after local, privacy, remote, and release readback checks pass.

## Completion standard

A task is complete only when its acceptance criteria are demonstrably met, verification passes, workflow state is valid, documentation reflects reality, review is approved, and no scoped work remains. A repository or release is complete only when public-readiness gates, privacy/history scans, remote metadata, branch, tag, release, and clean-tree readbacks agree with the claim.
