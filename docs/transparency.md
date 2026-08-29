# Corpus and coverage transparency

CallerSignal publishes a committed, reproducible snapshot of what its public corpus can and cannot support. The snapshot lives at [`web/assets/transparency.json`](../web/assets/transparency.json) and is rendered on the website without substituting browser-computed reputation logic.

## Current public snapshot

Snapshot time: **29 August 2026, 08:35 UTC**. Source registry review date: **28 August 2026**. Methodology version: **1.0.0**.

| Public measure | Value | Meaning |
| --- | ---: | --- |
| Jurisdictions with enabled source coverage | 3 | NL, GB, and US have enabled numbering-context sources |
| Enabled risk-capable sources | 0 | No enabled source can currently support a public risk verdict |
| Eligible public campaigns | 0 | No campaign passes the public evidence and source-rights threshold |
| Verified organisation portfolios | 0 | No verified declaration portfolio is published |
| Privacy-thresholded community aggregates | 0 | Community publication has not been approved |
| Published corrections | 0 | No eligible campaign or portfolio correction is present |

The zeroes are product facts, not placeholders. Lookup popularity, raw report volume, reporter identities, and watch subscribers are intentionally excluded. A large number of searches would not improve a number's reputation or make a risk conclusion more credible.

## Exact enabled coverage

| Source | Jurisdiction | Evidence scope | Last successful ingest | Freshness |
| --- | --- | --- | --- | --- |
| ACM public telephone number register | NL | Numbering context only | 27 August 2026, 07:30 UTC | Current |
| Ofcom long-term protected number ranges | GB | Numbering context only | 27 August 2026, 07:45 UTC | Current |
| NANPA public numbering references | US | Numbering context only | 27 August 2026, 08:00 UTC | Current |

All three jurisdictions therefore carry the explicit gap `no_risk_capable_source`. The registry also names `wieheeftmijgebeld_nl` as unavailable with `reuse_permission_required`: CallerSignal does not ingest that source without permission. “Available on the public web” is not a licence to copy or republish a database.

## What “no matching evidence” means

No matching evidence means only that the eligible sources checked at that time returned no publishable match. It does not mean that the displayed number is safe, that the call originated from its apparent subscriber, or that caller ID was not spoofed.

This is why a lookup backed only by the three current numbering sources resolves to `insufficient_evidence`, not `no_risk_evidence`. The latter state requires at least one current, eligible, risk-capable source that returned no match. See [`methodology.md`](methodology.md) for the four-state evaluation order.

## Derivation and publication gates

`callersignal.transparency.build_transparency_snapshot` accepts only explicit source registry, ingest, campaign, verified-portfolio, community-aggregate, moderation, methodology, and timestamp inputs. There is deliberately no lookup-demand input.

A public count includes only:

- sources that are enabled, have an enabled adapter, declare a jurisdiction, and pass every rights, privacy, takedown, and provenance gate;
- campaigns in a publishable lifecycle state whose complete eligible evidence comes from enabled risk-capable sources;
- organisation portfolios with current verification and no correction review;
- community aggregates that are verified, public, attached to an enabled risk-capable source, and above an approved privacy threshold.

Community publication is currently `not_approved`, so the public aggregate threshold is intentionally unset and aggregate publication is disabled. Public free text is prohibited. The independent-observer policy minimum is two, but it does not enable community publication by itself.

## Reproduce and verify

From the repository root:

```console
uv run pytest tests/integration/test_transparency.py -q
npm --prefix web test
make check
```

The integration test rebuilds the committed snapshot from [`sources/registry.json`](../sources/registry.json) and the reserved public fixtures, then requires exact equality. Web tests verify the public zero state and confirm that private activity and vanity totals are absent. Browser proof is recorded in [`web/proof/browser-proof.json`](../web/proof/browser-proof.json), with dedicated desktop and mobile coverage captures.

To change a public total, change the underlying eligible records or source gates, regenerate the projection deterministically, update this document, and pass the same checks. Never edit the number merely to improve how the project appears.
