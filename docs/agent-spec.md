# CallerSignal Agent Spec

## Overview

CallerSignal gives agents one deterministic lookup for an unfamiliar displayed phone number. It normalizes with explicit origin context, checks eligible evidence, derives a calibrated risk state and caller-campaign context, and returns the same versioned truth through CLI, MCP, HTTP, and web renderers. It does not identify the caller or promise that answering is safe.

## Behavior graph

```text
input + explicit origin
  -> number normalization
  -> source eligibility and country routing
  -> separate evidence and typed gaps
  -> calibrated risk assessment
  -> spoofing-aware caller-campaign context
  -> shared JSON result
  -> CLI | MCP | HTTP | web renderer
```

Each node fails closed. Invalid or ambiguous input returns typed guidance. A missing, stale, contradictory, unavailable, unsupported, or rights-restricted source becomes an explicit gap. No renderer may invent a stronger conclusion than the shared JSON result.

## Risk states

| State | Meaning | Default action |
| --- | --- | --- |
| `official_warning` | A current authoritative source explicitly warns about the displayed number or applicable range. | Do not act on the call; independently contact the claimed organisation through a trusted channel. |
| `elevated_signals` | Multiple independent, recent, eligible observations support a consistent harmful-behaviour pattern. | Avoid sharing data or money and verify the caller independently. |
| `no_risk_evidence` | At least one current, eligible, risk-capable source was checked and returned no matching risk evidence. This is not a safe-number verdict. | Stay cautious and verify unexpected requests independently. |
| `insufficient_evidence` | Risk-capable coverage, freshness, availability, rights, or consistency cannot support a stronger state. Numbering context alone remains here. | Treat the result as unknown and do not rely on it for identity or safety. |

Numbering-plan evidence may improve source context but cannot by itself create `official_warning` or `elevated_signals`. Lookup demand never changes a risk state. One unverified community report remains an observation, not a verdict.

A caller campaign is a durable, correction-aware pattern about calls displaying exact numbers or explicitly bounded patterns. One current official warning can activate a campaign; otherwise at least two independent eligible sources must corroborate the same pattern. Stale, restricted, uncorroborated, or contradictory evidence fails closed to monitoring. Campaign membership never proves caller, subscriber, provider, or organisation identity.

## Representative use cases and evaluations

1. A reserved fictional US number with only current numbering evidence produces `insufficient_evidence` because no risk-capable source was checked, while preserving the useful numbering context.
2. A synthetic current, eligible, risk-capable source with no match produces `no_risk_evidence`, includes “not proof of safety,” and validates unchanged through CLI, MCP, HTTP, and web.
3. Unsupported or source-failed input produces `insufficient_evidence` with the relevant gap and a retry or caution action.
4. A synthetic authoritative-warning fixture produces `official_warning` only when source authority, reuse, freshness, and applicability are valid.
5. A synthetic report set produces `elevated_signals` only with multiple independent, recent, moderated observations; one report and lookup popularity are invariant negatives.
6. Two eligible independent sources with different patterns remain insufficient rather than being combined into a broad campaign.
7. A contradicted campaign opens correction review and is not presented as active.
8. Every result retains provenance, freshness, reason codes, evidence identifiers, gaps, residual spoofing uncertainty, and an explicit action message.

Unit and contract tests grade the deterministic state transition and cross-surface schema parity. Browser proof grades hierarchy, text/icon state distinction, contrast, responsive layout, focus, overflow, and console health rather than exact prose pixels.

## Tools and data

- Python normalization, country adapters, evidence ledger, and assessment policy.
- Versioned JSON Schemas as the canonical product interface.
- Official public numbering fixtures with recorded provenance and reuse basis.
- The versioned caller-campaign contract and deterministic derivation policy.
- Licensed feeds or first-party moderated reports only after their source and privacy gates pass.
- Vercel for the approved public HTTP and web renderer; local CLI and MCP remain first-class.

## Constraints and safety rules

- A displayed number is not proof of caller, subscriber, provider, guilt, reachability, location, or safety.
- Campaign membership describes calls displaying a bounded value and is never an identity or origin claim.
- Only official, explicitly licensed, or first-party moderated evidence may influence reputation.
- Public visibility and `robots.txt` behavior are not reuse licences.
- Real phone numbers, reports, requester identities, IP addresses, narratives, credentials, and production datasets stay out of Git and `.go` evidence.
- Public report ingestion remains blocked until legal basis, notice, minimization, retention, correction, deletion, objection, appeal, moderation, rate limiting, deduplication, anti-brigading, incident, and takedown operations are approved and tested.

## Deployment and observability

The public web and HTTP surfaces deploy to the existing CallerSignal Vercel project only after repository gates, cross-surface tests, visual proof, commit, and push pass. Production observability is metadata-only by default: request id, duration, typed status, source health, and coarse country coverage. Raw or normalized phone numbers, request bodies, identities, full source payloads, prompt/response bodies, and lookup histories are not logged.

Deployment never authorizes new data collection. Enabling a source, accepting public reports, retaining lookup history, or adding content-level telemetry requires its own explicit product, privacy, and operational gate.
