# Agent Contract

## Authority and source of truth

`.go` is CallerSignal's canonical work contract. The repository-local launcher and pinned stack version govern task routing. The explicit user request and the claimed task bound the work; neither broad autonomy nor a terminal instruction expands authority into product, privacy, publication, or external actions not already in scope.

Normative product and safety rules live in [`docs/vision.json`](vision.json). Architecture boundaries live in [`docs/architecture.md`](architecture.md). When prose and a machine contract diverge, stop, repair the inconsistency in a scoped task, and validate both.

## Required execution loop

1. Read [`AGENTS.md`](../AGENTS.md), `.go/project.json`, `.go/vision.json`, `.go/hierarchy.json`, and `.go/architecture-principles.json`.
2. Run `./go validate .`, `./go status .`, and `./go next .`.
3. Claim exactly one dependency-eligible task and inspect its full scope, acceptance, and verification.
4. Preserve unrelated or user-owned changes; do not use destructive reset or broad cleanup.
5. Implement only the task contract. Update tests and documentation with behavior or contract changes.
6. Run every task verification command and `make check`.
7. Inspect the diff for secrets, personal data, unsafe fixtures, generated state, placeholders, and overclaimed maturity.
8. Finish with structured evidence naming changed files, exact verification commands and exit status, and critic outcome.
9. Record an explicit `approved` or `needs_fix` review decision before treating the task as complete.

## Evidence standard

Evidence must be reproducible and specific. “Tests pass” is insufficient. Name the command, record `rc=0`, identify material changed files, and state how critical review was performed or why it was intentionally skipped. Never copy secrets, private data, real numbers, raw reports, or sensitive logs into `.go/evidence` or task history.

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
