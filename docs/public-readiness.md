# Public Readiness Evidence

## Current `main` revalidation — 2026-08-27

The public/professional profile was revalidated after the read-only CLI, MCP, HTTP, and web surfaces were added. The current gate includes 106 Python tests, three web unit tests, schema and `.go` validation, documentation and asset checks, and privacy protections. A least-privilege GitHub workflow is configured to invoke the same `make check` command with immutable action revisions; it does not create a second validation path.

The current web-profile command is:

```console
python3 /Users/viggomeesters/Dev/viggo-agent-skills/scripts/repo_complete_bootstrap.py \
  --public --mode validate --path . --kind web-app \
  --remote-policy required --release-policy required --url-policy required --json-schema
```

After authenticated production deployment, the command returned `JA`, exit code `0`, and zero hard blockers with deploy-URL checks required. GitHub homepage metadata and the README both point to the live `https://callersignal.vercel.app/` alias; homepage, lookup, health, security-header, and real-browser readbacks all passed.

Post-push readback registered `.github/workflows/ci.yml` as an active workflow. GitHub nevertheless rejected a manual run with HTTP `422` because Actions is disabled for the repository owner's account. The repository does not change that account-level setting autonomously. Until the owner enables Actions, the repeatedly green local `make check` execution is the authoritative equivalent gate; remote execution remains explicitly unproven.

## Verdict

CallerSignal's repository foundation passed the strict public/professional validation profile on 2026-08-26. `repo-complete` returned `JA`, exit code `0`, and `0` hard blockers with remote, release, and metadata policies required. The validated publication revision was `95572648d71e4df6ec2a7f0372a45d12112a8583`.

This certification covers repository foundation only. Phone-number normalization, evidence adapters, lookup orchestration, CLI, MCP, HTTP, web, reporting, assessment, and production operations remain sixteen dependency-ordered product tasks.

## Local quality proof

`make check` completed with exit code `0` immediately before publication review. It reported:

- locked dependency synchronization succeeded;
- Ruff completed with no findings;
- all 13 repository tests passed;
- repo-local `.go` validation passed;
- documentation, asset, public-safety, and whitespace checks passed.

The vision contract validates against the committed schema and contains eleven explicit product, design, engineering, and safety principles. The `.go` contract contains twenty-one tasks: five repository-foundation tasks and sixteen product tasks.

## Repository-complete proof

The strict command was:

```console
python3 /Users/viggomeesters/Dev/viggo-agent-skills/scripts/repo_complete_bootstrap.py \
  --public --mode validate --path . --kind generic \
  --remote-policy required --release-policy required --url-policy none --json-schema
```

All hard checks reported `OK`, including README, license, Git metadata, design vision, contribution policy, changelog, local validation quality, remote strategy, public documentation, security policy, secret scrub, private filenames, Git-history privacy, large binaries, public visibility, GitHub description, GitHub topics, rendered hero, visual proof, and release readiness. A deploy URL is not applicable to this repository-foundation release and was explicitly disabled with `--url-policy none`.

## Visual proof

The README renders `assets/hero.png` near the top. A separate 2:1 `assets/social-preview.png` is committed. Both rasters passed automated dimension and ratio checks and original-resolution inspection for clipping, overlap, contrast, readability, private data, text, watermarks, edge safety, and non-alarmist semantics. Exact dimensions and digests are recorded in [`docs/visual-proof.md`](visual-proof.md).

## Privacy, secrets, and history proof

The current tree and every Git revision were checked for the original session numbers, high-confidence token formats, private-key headers, secret or private filenames, generated environments, caches, and non-canonical `.go` runtime state. No disallowed value or tracked runtime artifact was found.

Repository history contains one root foundation revision at the certification point. The largest tracked files are the two reviewed public visual assets at less than 2 MB each; no tracked file exceeds 5 MB. `.gitignore` was read back against representative environment, credential, private-data, export, recording, cache, lock, and run-state paths.

The committed documentation uses one NANPA-reserved fictional number for interface examples. No real personal phone number, contact record, lookup history, report, recording, private screenshot, credential, proprietary dataset, or raw sensitive log is included.

## GitHub readback

GitHub reported:

- repository: `viggomeesters/callersignal`;
- URL: `https://github.com/viggomeesters/callersignal`;
- visibility: `PUBLIC`;
- default branch: `main`;
- description: `Evidence-backed international phone-number intelligence for agents, CLIs, MCP clients, and the web.`;
- topics: `agent-first`, `caller-id`, `e164`, `fraud-prevention`, `mcp`, `open-source`, `phone-number`, and `telecom`.

The publication checkpoint `v0.1.0-rc.1` is a non-draft prerelease and resolves to the validated revision. The definitive release is created only from the clean, fully certified repository HEAD.

## Reproduction

```console
make check
./go validate .
python3 /Users/viggomeesters/Dev/viggo-agent-skills/scripts/repo_complete_bootstrap.py \
  --public --mode validate --path . --kind generic \
  --remote-policy required --release-policy required --url-policy none --json-schema
gh repo view viggomeesters/callersignal \
  --json name,url,visibility,defaultBranchRef,description,repositoryTopics
git ls-remote origin refs/heads/main refs/tags/v0.1.0
```
