# Public Readiness Evidence

## Current release state — 29 August 2026

CallerSignal v0.3.0 is the current functional public release. The repository is
public at `viggomeesters/callersignal`, `main` is the default branch, and the
read-only product is live at `https://callersignal.vercel.app/`. CLI, stdio MCP,
Streamable HTTP MCP, HTTP, and web clients share the same versioned lookup and
four-state risk contract. HTTP, both MCP transports, CLI, and web also share one
public-safe source-coverage projection.

The current official Dutch catalogue has 74,984 ranges, including 73,409
lookup-compatible intervals, three register statuses, and 44 destination
categories. CallerSignal indexes 15 caller-report services and four advertised
licensing routes, but enables zero reputation feeds and zero eligible public
campaigns. It therefore does not call an unmatched number safe, identify its
owner, or prove where a call originated. Permission-required sites are not
scraped. Report collection, watch persistence, organisation publication, and
outbound notifications remain disabled in production until their provider,
identity, consent, moderation, rate, retention, objection, correction, and
deletion controls exist.

## Release gate

The authoritative local gate is:

```console
make check
```

It verifies locked Python and JavaScript dependencies, formatting and linting,
Python and web tests, every committed schema, repository documentation and
assets, the repo-local `.go` state, public-safety rules, whitespace, and package
version consistency. This repository-local proof is authoritative and does not
depend on GitHub Actions.

The v0.3.0 release run completed with 253 Python tests and 8 web tests passing.

Strict public validation uses:

```console
python3 /Users/viggomeesters/Dev/viggo-agent-skills/scripts/repo_complete_bootstrap.py \
  --public --mode validate --path . \
  --remote-policy required --release-policy required --json-schema
```

The v0.3.0 release run returned `JA`, exit code `0`, and zero hard blockers. The
profile covers repository identity and history, vision and design contracts,
onboarding and public policies, local gates, remote metadata, live URL, hero
assets, visual proof, release readiness, secrets, privacy, and large binaries.

## Product and protocol proof

Contract, unit, integration, parity, privacy, and end-to-end tests exercise:

- country-explicit normalization and fail-closed NL, GB, and US adapters;
- immutable evidence, source eligibility, freshness, and typed gaps;
- identical four-state assessment semantics across every interface;
- caller-campaign publication thresholds and correction behavior;
- consent-bound private watches and verified organisation declarations without
  making either feature public in production;
- exact corpus-transparency output with no popularity or raw-report leakage;
- exact cross-surface source coverage with ACM digest, freshness, status and
  destination coverage plus rights-aware reputation activation gaps;
- a zero-request guarantee for every disabled caller-report source and bounded
  ingestion for a separately authorized feed;
- hosted MCP discovery, initialization, nine tool declarations, public reads,
  locked scoped mutations, Origin and protocol validation, bounded bodies,
  notifications, and `no-store` responses;
- privacy-safe operational metrics, incident handling, deletion, correction,
  takedown, and abuse controls.

Production readback proves the homepage and health route, full ACM-backed Dutch
lookup, HTTP source coverage, protocol discovery, public MCP source coverage,
the locked protected-tool boundary, hostile-Origin rejection, and `no-store`
responses. Exact immutable deployment and alias evidence is recorded in the
repo-local release task.

## Visual proof

The README displays `assets/hero.png` at the top and GitHub uses the companion
2:1 `assets/social-preview.png`. Their dimensions, digests, and original-scale
inspection are recorded in [`visual-proof.md`](visual-proof.md).

The responsive website was rendered at 1440-pixel desktop and 375-pixel mobile
widths across default, invalid, insufficient-evidence, no-risk-evidence,
elevated-signals, official-warning, and corpus-coverage states. Twelve committed
captures in `web/proof/` were checked for clipping, overlap, horizontal overflow,
contrast, text hierarchy, readable actions, temporary copy, and console errors.

## Privacy, secrets, and history proof

The current tree and every Git revision are checked for the original session
numbers, high-confidence token formats, private-key headers, secret files,
generated environments, caches, runtime state, exports, recordings, and large
binaries. The repository contains no real personal number, subscriber identity,
contact record, raw report, lookup history, recording, private screenshot,
credential, proprietary dataset, or sensitive log.

The automated filename scanner recognizes the phrase `private-watch` in one
public product-task contract. [`public-readiness-review.md`](public-readiness-review.md)
records the exact paths, git-history review, why they are public-safe false
positives, the forbidden-content boundary, and the rule that any new signal
requires a fresh human decision. No history rewrite is warranted.

`.gitignore` excludes credentials, private data, generated runtime state, local
databases, caches, environments, coverage output, deployment metadata, exports,
recordings, and screenshots that are not deliberate reviewed public assets.

## GitHub and deployment readback

GitHub reports:

- repository: `viggomeesters/callersignal`;
- URL: `https://github.com/viggomeesters/callersignal`;
- visibility: `PUBLIC`;
- default branch: `main`;
- homepage: `https://callersignal.vercel.app/`;
- description: `Evidence-backed international phone-number intelligence for agents, CLIs, MCP clients, and the web.`;
- topics: `agent-first`, `caller-id`, `e164`, `fraud-prevention`, `mcp`,
  `open-source`, `phone-number`, and `telecom`.

Vercel production deployment is intentionally manual because no GitHub-Vercel
integration is configured. Deployment requires the explicit
`viggos-projects-eac4720a` scope. Release readback covers the stable alias,
immutable deployment, health route, MCP version, and function inventory.

## Reproduction

```console
make check
./go validate .
python3 /Users/viggomeesters/Dev/viggo-agent-skills/scripts/repo_complete_bootstrap.py \
  --public --mode validate --path . \
  --remote-policy required --release-policy required --json-schema
gh repo view viggomeesters/callersignal \
  --json name,url,visibility,defaultBranchRef,description,homepageUrl,repositoryTopics
git ls-remote origin refs/heads/main refs/tags/v0.3.0
npx --yes vercel@latest inspect https://callersignal.vercel.app \
  --scope viggos-projects-eac4720a
```
