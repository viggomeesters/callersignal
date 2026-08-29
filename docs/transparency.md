# Corpus and coverage transparency

CallerSignal publishes a committed, reproducible snapshot of what its public corpus can and cannot support. The snapshot lives at [`web/assets/transparency.json`](../web/assets/transparency.json) and is rendered on the website without substituting browser-computed reputation logic.

## Current public snapshot

Snapshot time: **29 August 2026, 14:10 UTC**. Source registry review date: **29 August 2026**. Methodology version: **1.0.0**.

| Public measure | Value | Meaning |
| --- | ---: | --- |
| ACM ranges imported | 74,984 | Every row in the checksum-pinned official register archive |
| ACM lookup-compatible ranges | 73,409 | Rows with a validated canonical NL interval |
| ACM register-status coverage | 73,221 assigned; 1,740 cooling off; 23 blocked | Neutral source statuses, not reputation labels |
| ACM destination categories | 44 | Distinct official destination labels, without publishing the labels or holder inventory |
| FCC keyed displayed numbers | 238,327 | Syntactically valid NANPA numbers represented only by deployment-keyed HMAC values |
| FCC indexed complaint observations | 260,504 | Admitted nuisance and robocall observations in the rolling window |
| FCC source observations | 461,955 | Admitted plus rejected observations; volume is not corroboration |
| FCC categories | 143,147 nuisance; 114,990 robocall | Neutral source-native groups, always unverified |
| Caller-report services indexed | 16 | Dated rights and integration discovery, not copied site records |
| Advertised licensing routes | 4 | Commercial routes worth evaluating; no CallerSignal agreement is implied |
| Enabled reputation sources | 1 | The public-domain FCC aggregate only; no commercial feed is enabled |
| Jurisdictions with enabled source coverage | 3 | NL, GB, and US have enabled numbering-context sources |
| Enabled risk-capable sources | 1 | FCC can supply evidence, but its unverified rows cannot independently elevate risk |
| Eligible public campaigns | 0 | No campaign passes the public evidence and source-rights threshold |
| Verified organisation portfolios | 0 | No verified declaration portfolio is published |
| Privacy-thresholded community aggregates | 0 | Community publication has not been approved |
| Published corrections | 0 | No eligible campaign or portfolio correction is present |

The zeroes are product facts, not placeholders. Lookup popularity, raw report volume, reporter identities, and watch subscribers are intentionally excluded. A large number of searches would not improve a number's reputation or make a risk conclusion more credible.

## Exact enabled coverage

| Source | Jurisdiction | Evidence scope | Last successful ingest | Freshness |
| --- | --- | --- | --- | --- |
| ACM public telephone number register | NL | Complete generated numbering catalogue | 29 August 2026, 11:23 UTC | Current |
| Ofcom long-term protected number ranges | GB | Numbering context only | 27 August 2026, 07:45 UTC | Current |
| NANPA public numbering references | US | Numbering context only | 27 August 2026, 08:00 UTC | Current |
| FCC Consumer Complaints Data — Unwanted Calls | US | Unverified nuisance/robocall aggregates | 29 August 2026, 14:00 UTC | Current |

NL and GB still carry the explicit gap `no_risk_capable_source`; US has one risk-capable complaint source in addition to numbering context. The registry also names `wieheeftmijgebeld_nl` as unavailable with `reuse_permission_required`: CallerSignal does not ingest that source without permission. “Available on the public web” is not a licence to copy or republish a database.

The caller-report discovery index has the enabled public-domain FCC route, eleven services requiring publisher permission, and four services advertising a licensing or partnership route. The latter fifteen are unavailable to the runtime. Their individual integration channel, jurisdiction scope, reason, and blocking gates are public in the snapshot. The four advertised routes still require a completed commercial agreement, credentials, privacy approval, takedown ownership, and provenance controls. Counts describe coverage only; they are not trust, popularity, reputation, or safety scores.

The FCC projection covers 29 August 2021 through 29 August 2026 and was built from the source update published at 05:02 UTC on 29 August 2026. It contains 241,200 grouped source rows, 238,327 unique keyed displayed numbers, and 260,504 admitted observations. Another 201,451 observations across 572 grouped caller-ID values failed the strict syntactic NANPA boundary and were excluded. These are coverage and minimization facts. FCC complaint data is consumer-selected and unverified; one source and any number of its rows cannot identify a caller, prove harmfulness, create an FCC warning, replace independent corroboration, or establish safety by absence.

## What “no matching evidence” means

No matching evidence means only that the eligible sources checked at that time returned no publishable match. It does not mean that the displayed number is safe, that the call originated from its apparent subscriber, or that caller ID was not spoofed.

A current US lookup now also checks the FCC aggregate. A matching unverified complaint observation remains `insufficient_evidence`; a current no-match may support `no_risk_evidence`, whose wording still says absence is not safety. NL and GB lookups backed only by numbering sources remain `insufficient_evidence`. See [`methodology.md`](methodology.md) for the four-state evaluation order.

## Derivation and publication gates

`callersignal.transparency.build_transparency_snapshot` accepts only explicit source registry, ACM manifest, authenticated or pinned FCC catalogue metadata, caller-report discovery index, ingest, campaign, verified-portfolio, community-aggregate, moderation, methodology, and timestamp inputs. There is deliberately no lookup-demand input. The ACM build refuses to replace a catalogue when its row, matchable-range, status, destination-category, or newest-mutation totals differ from the pinned manifest expectations. FCC observation accounting and category totals must reconcile exactly or its public coverage fails closed.

A public count includes only:

- sources that are enabled, have an enabled adapter, declare a jurisdiction, and pass every rights, privacy, takedown, and provenance gate;
- campaigns in a publishable lifecycle state whose complete eligible evidence comes from enabled risk-capable sources;
- organisation portfolios with current verification and no correction review;
- community aggregates that are verified, public, attached to an enabled risk-capable source, and above an approved privacy threshold.

Community publication is currently `not_approved`, so the public aggregate threshold is intentionally unset and aggregate publication is disabled. Public free text is prohibited. The independent-observer policy minimum is two, but it does not enable community publication by itself.

## Reproduce and verify

From the repository root:

```console
uv run python scripts/build_transparency_snapshot.py --generated-at 2026-08-29T14:10:00Z
uv run pytest tests/integration/test_transparency.py -q
npm --prefix web test
make check
```

The generator reads [`sources/registry.json`](../sources/registry.json), [`sources/acm-bulk-manifest.json`](../sources/acm-bulk-manifest.json), [`sources/fcc-catalog-release.json`](../sources/fcc-catalog-release.json), [`sources/caller-report-services.json`](../sources/caller-report-services.json), and the reserved public fixtures. During deployment it authenticates the newly built FCC SQLite catalogue with `CALLERSIGNAL_REPUTATION_INDEX_KEY` and uses that live metadata instead of the pinned release copy. The integration test rebuilds the committed snapshot and requires exact equality. HTTP `GET /v1/coverage`, CLI `coverage --json`, stdio and hosted MCP `get_source_coverage`, and the website all return or render that same object. Web tests confirm that raw inventory, keyed values, holder names, reports, requester activity, secrets, and vanity totals remain absent. Browser proof is recorded in [`web/proof/browser-proof.json`](../web/proof/browser-proof.json), with dedicated desktop and mobile coverage captures.

To change a public total, change the underlying eligible records or source gates, regenerate the projection deterministically, update this document, and pass the same checks. Never edit the number merely to improve how the project appears.
