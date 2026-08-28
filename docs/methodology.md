# Risk assessment methodology

CallerSignal separates **source evidence quality** from **phone-number risk**. The top-level `assessment.state` and `assessment.confidence` describe the available evidence and its provenance. They do not estimate whether a call is safe. The nested `assessment.risk` is the only canonical risk presentation contract.

## Four calibrated states

Risk states are evaluated in this order:

1. `official_warning` — a current, public warning from an official regulator explicitly associates the displayed number with fraud, scams, or abuse. The recommended action is to stop and independently contact the claimed organisation.
2. `elevated_signals` — at least two distinct eligible sources contain current, public, verified observations of the same supported harmful-activity pattern. Repeated records from one source do not count as independent corroboration.
3. `no_risk_evidence` — at least one eligible risk-capable source was checked and every such source returned `no_match`. This means only that those sources had no matching observation at check time; it is never a safe-number claim.
4. `insufficient_evidence` — the default whenever none of the stronger conditions is met. Numbering-plan facts, range-holder data, lookup volume, a single report, unverified observations, or missing risk-capable sources cannot determine call risk.

An authoritative official warning remains visible even when another source is unavailable. Without an official warning, stale, failed, conflicting, unsupported, or reuse-restricted risk coverage forces `insufficient_evidence` rather than a confident result.

## Eligible risk sources

A source check is marked `risk_capable: true` only when its declaration:

- permits the non-identity claim type `reported_activity_summary`; and
- identifies the source as an official regulator, licensed data provider, or moderated community aggregate.

That flag declares capability, not truth. Evidence still has to be public, current, within the source declaration, and sufficiently verified for the state it supports. Source use also remains subject to the repository's rights and provenance controls.

## Stable actions and provenance

Each risk result provides a headline, plain-language summary, stable reason codes, supporting evidence and source IDs, and one recommended-action code:

- `avoid_and_verify`
- `avoid_sensitive_actions`
- `stay_cautious`
- `treat_as_unknown`

Consumers should render the text and icon as well as colour. They must preserve the spoofing warning: caller ID can be forged, so evidence about a displayed number cannot prove who placed a specific call. Query popularity and lookup demand are operational metrics only and never feed the assessment.
