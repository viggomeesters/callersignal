# Data Safety and Public Boundaries

## Scope

Phone numbers and call reports can be personal data, and displayed caller ID can be spoofed. This repository is public. Its default posture is data minimization, provenance, calibrated uncertainty, and zero private fixtures. This document is an engineering boundary, not legal advice; a qualified privacy and legal review is required before public report ingestion or production processing.

## Claims CallerSignal may and may not make

CallerSignal may describe validated number structure, country or numbering-plan context, official source observations, range-allocation evidence, source freshness, and explicit community observations under their correct evidence class.

CallerSignal must not present a displayed number as proof of caller identity; present a range holder or original carrier as the current provider, subscriber, or caller; infer live location from numbering geography; label a number safe because no reports exist; or infer fraud from lookup popularity, virality, or one unverified report.

## Repository data classes

| Class | Public repository policy |
| --- | --- |
| Product schemas and synthetic fixtures | Allowed when they contain no real personal data and preserve safety semantics |
| Official-source metadata and small permitted fixtures | Allowed only with authority, reuse basis, provenance, retrieval time, permitted fields, and license recorded |
| Real personal phone numbers or call histories | Forbidden |
| Contact-book identities, private reports, requester data, IP addresses, recordings, screenshots, or exports | Forbidden |
| Credentials, access tokens, cookies, private keys, or local configuration | Forbidden |
| Aggregated demand metrics | Documentation is allowed; production values require anti-enumeration and privacy thresholds |

Use an officially reserved fictional value when a complete example is essential. Otherwise use structural redaction such as `+<country-code><national-number>`. Never replace only a few digits of a real number and assume it is safe.

## Evidence separation

The implementation must model these independently:

1. Number interpretation and syntax facts.
2. Official or licensed source observations.
3. Claims about provider, subscriber, or identity.
4. Reports about calls displaying a number.
5. Aggregate lookup demand.
6. Derived assessments.

A lookup is not a report. High lookup demand is not evidence of harm. A report is an unverified observation until moderation and corroboration justify a stronger state. Derived assessments reference evidence but never overwrite it.

## Minimum production controls

Before processing real lookups, document purpose, lawful basis where applicable, retention, deletion, access, sharing, logging, security, incident response, and data-subject operations. Prefer ephemeral processing and coarse service metrics. Avoid raw phone-number cardinality, requester identity, raw IP retention, persistent lookup trails, and analytics payloads containing numbers.

Before accepting reports, implement and test notice, consent or other applicable basis, minimization, retention limits, correction, objection, deletion, moderation, appeals, rate limiting, deduplication, anti-brigading, source takedown, abuse response, and auditable policy changes. Public aggregates require a minimum cohort threshold and anti-enumeration review.

## Source intake checklist

A country adapter cannot ship until it has an `enabled` entry in the machine-validated [`source registry`](../sources/registry.json). That record must identify the authority and stable source location; document reuse terms and permitted fields; capture retrieval time and content identity; define freshness and outage behavior; state personal-data and free-text policy; include takedown ownership; and keep robots access, reuse permission, copyright, database rights, privacy, takedown, and provenance as separate gates. The adapter must also state portability and allocation limitations, include a public-safe deterministic fixture, and pass the shared fail-closed conformance suite.

Scraping or republishing third-party caller databases without explicit permission is outside scope. A permissive `robots.txt` only describes crawl access; it is not a license or privacy approval. Search snippets, ratings, report counts, phone-number lists, user narratives, and derived aggregates remain prohibited when reuse rights or personal-data status are unclear. Such a source must be `permission_required`, with no adapter, no evidence classes, zero permitted fields, and no copied records. See [`docs/source-rights.md`](source-rights.md) for the enablement procedure and current decisions.

Official and licensed feeds are not blanket-approved either. Only the fields and evidence classes named in the registry may enter fixtures or public results. Expanding a source's fields, quantity, cadence, use case, or jurisdiction requires a new review before ingestion.

## Logging and diagnostics

Default logs should contain request identifiers, duration, adapter health, typed result status, and coarse country coverage only. They should not contain raw or normalized phone numbers, request bodies, requester identities, contact names, report narratives, tokens, cookies, or full external payloads. Debugging with sensitive values must use an approved temporary environment, restricted access, explicit expiry, and documented deletion; it must never enter this repository or `.go` evidence.

## Security and privacy response

Report suspected vulnerabilities or exposed personal data through the private route in [`SECURITY.md`](../SECURITY.md). Do not open a public issue with a real number, report narrative, request trace, credential, or reproduction containing private data. Maintainers should contain access, preserve only necessary restricted evidence, rotate affected secrets, remove public exposure, assess notification duties, and publish a sanitized retrospective when appropriate.

## Review gate

Every change involving a new source, data field, report flow, retention rule, log, metric, screenshot, fixture, or public claim must be checked against [`docs/vision.json`](vision.json), the [source registry](../sources/registry.json), the repository safety test, and this document. A legal or privacy uncertainty is a stop condition, not an invitation for an agent to guess.
