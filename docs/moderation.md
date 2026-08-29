# First-Party Report Moderation

CallerSignal can accept a structured first-party observation through the transport-independent [`ReportService`](../src/callersignal/reports/service.py). This capability is not exposed by the public website, HTTP API, or hosted MCP until the production data, privacy, legal-basis, authentication, operations, and provider gates are approved. The in-memory implementation is deterministic proof of the domain controls, not a production datastore.

## Claim boundary

A report says that a person directly observed an inbound interaction displaying a phone number. It never asserts that the subscriber, range holder, declared organisation, or any named person placed the call. Caller ID can be spoofed. Every stored report therefore keeps:

- `subject_semantics: call_displayed_number`;
- `verification_status: unverified_observation`, including after moderation acceptance;
- an explicit displayed-number-not-identity attestation;
- structured category, channel, outcome, and optional occurrence time only;
- `contains_free_text: false`.

The service does not accept narratives, attachments, recordings, contact names, identity claims, requester IP addresses, raw lookup histories, or arbitrary categories.

## Intake controls

The caller supplies an opaque proof token from the eventual authenticated boundary. The service immediately converts it into a keyed digest and never stores the raw token. A report ID, deduplication fingerprint, and correction receipt are also keyed deterministic values. The production boundary must supply the secret from an approved secret store and must not use IP addresses as durable identity.

Before storage, the service checks:

1. E.164 structure and the existing normalized phone-number object;
2. allowed structured categories, channel, outcome, region, and timestamp;
3. exact duplicate fingerprint;
4. per-proof-token rate limit within the configured window; and
5. distinct-proof-token threshold for the same displayed number within that window.

An exact repeat returns the original receipt and creates no second report. Excess activity returns a typed `actor_rate_limit` or `brigading_threshold` rejection and stores no extra report. These controls reduce abuse; they do not prove that accepted submissions are true or independent people.

## Moderation lifecycle

| Workflow state | Meaning |
| --- | --- |
| `pending` | Newly submitted or reporter-corrected structured observation awaiting review. |
| `accepted_observation` | Format and policy review passed; the report remains unverified. |
| `rejected` | Moderation rejected the observation with machine-readable reason codes. |
| `withdrawn` | The reporter requested removal; content is deleted and only a minimized deletion receipt remains. |

Moderation decisions require non-empty machine-readable reason codes. Acceptance never changes `unverified_observation` into verified evidence. Reputation aggregation may consume only privacy-thresholded, independently corroborated aggregates produced under its separate task and policy.

## Correction, deletion, and retention

The original opaque actor proof plus receipt ID authorizes correction or deletion. A correction can change only structured categories, returns the report to `pending`, and adds `reporter_correction`. A deletion removes report content and deduplication state, then returns a minimal receipt containing a pseudonymous report handle, deletion time, and reason.

Each report has an explicit retention deadline. Scheduled purge removes expired content, and every read or mutation checks expiry again so a missed schedule cannot expose an overdue report. Expired content fails as not found and produces a `retention_expired` receipt.

## Production activation gate

Public intake remains disabled until all of the following have executable proof:

- approved processing purpose, legal basis review, notice, consent where applicable, and data map;
- production storage with atomic correction, deletion, retention, and audit receipts;
- authenticated proof-token issuance, secret rotation, anti-enumeration, and transport rate limits;
- moderation staffing, appeal, objection, source takedown, abuse, and incident runbooks;
- privacy-thresholded aggregation that cannot use one report or lookup popularity as a verdict;
- provider contracts, access controls, encryption boundaries, backup deletion, and failure behavior;
- security, privacy, integration, and operational tests plus release approval.

No third-party caller-report database enters this service unless the source registry separately proves explicit reuse rights and privacy eligibility.

## Verification

```console
uv run pytest tests/integration/test_reports.py -q
make check
```
