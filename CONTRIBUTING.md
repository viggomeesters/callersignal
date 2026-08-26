# Contributing to CallerSignal

Thank you for helping build evidence-backed caller intelligence without overclaiming what a displayed number proves.

## Before you begin

Read the [vision contract](docs/vision.json), [architecture](docs/architecture.md), [data-safety boundary](docs/data-safety.md), and [agent instructions](AGENTS.md). Product work is managed as dependency-ordered `.go` tasks. Discuss a change before coding when it alters a schema, source-reuse basis, public claim, privacy or retention rule, moderation policy, storage boundary, or release scope.

## Set up and validate

```console
git clone https://github.com/viggomeesters/callersignal.git
cd callersignal
make check
./go next .
```

The repository uses Python 3.12 or newer and `uv`. `make check` synchronizes locked development dependencies and runs the full local quality gate. No private service or credential is needed.

## Choose bounded work

Use `Go` in a compatible agent environment or `./go next .` in a shell. Claim one eligible task and honor its declared scope, acceptance criteria, dependencies, and verification commands. If no task covers the change, propose a small dependency-aware task instead of expanding an unrelated one.

## Safety requirements

- Never commit a real personal phone number, call history, report narrative, contact identity, raw request, IP address, recording, private screenshot, credential, or unlicensed dataset.
- Use officially reserved fictional numbers or structural redaction.
- Describe a call as displaying a number; caller ID is not proof of the caller.
- Keep numbering facts, source observations, identity claims, reports, lookup demand, and assessments separate.
- Treat missing, stale, or conflicting evidence as an explicit gap.
- Document authority, reuse basis, permitted fields, retrieval time, freshness, and limitations for every source.

## Changes and tests

Keep changes small and focused. Update schemas, fixtures, tests, docs, and `.go` contracts together when behavior changes. Run the task-specific verification plus:

```console
make check
git diff --check
```

Review the diff for secrets, private data, generated runtime state, unfinished markers, and maturity claims that exceed implemented behavior.

## Commits and review

Use an imperative, scoped commit subject such as `docs: clarify adapter evidence boundaries`. A pull request should explain the problem, identify the `.go` task, map changes to acceptance criteria, provide exact verification evidence, call out data or source implications, and include visual proof for interface changes.

Review is evidence-based. A passing gate is necessary but does not replace review of privacy, licensing, semantics, accessibility, or public claims. Maintainers may request a narrower change or an explicit design decision before merging.

By contributing, you agree that your contribution is licensed under the repository's [MIT License](LICENSE) and that you will follow the [Code of Conduct](CODE_OF_CONDUCT.md).
