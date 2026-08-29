# Privacy and Data Map

This document records CallerSignal's engineering posture, not legal advice or a final lawful-basis determination. The European Commission describes purpose limitation, data minimisation, storage limitation, accuracy, security, and accountability as core processing principles; the European Data Protection Board requires data protection by design and by default. CallerSignal treats those principles as build gates, while a qualified reviewer must approve each real processing purpose before activation. See the [European Commission principles](https://commission.europa.eu/law/law-topic/data-protection/reform/rules-business-and-organisations/principles-gdpr/overview-principles/what-data-can-we-process-and-under-which-conditions_en) and [EDPB Guidelines 4/2019](https://www.edpb.europa.eu/documents/guideline/guidelines-42019-on-article-25-data-protection-by-design-and-by-default_en).

## Activation status

Public lookup is read-only and ephemeral. Public report submission, durable watch subscriptions, organisation challenges, and outbound notifications are disabled. Their processing purposes and engineering controls are documented below, but their lawful-basis status is **not approved**. Code proof does not authorize real personal-data processing.

The enabled FCC public-domain importer is a separate source-specific path, not approval for first-party reporting. It minimizes the official complaint export during the build: only caller ID, issue date, and call/message type enter the process; valid displayed numbers are immediately replaced with secret-keyed HMAC values; and no plaintext number inventory, raw complaint row, narrative, ticket, advertiser field, reporter attribute, or requester history is retained. Public output is limited to neutral aggregate counts, dates, provenance, freshness, and explicit unverified/spoofing caveats.

## Data map

| Data class | Purpose and fields | Lawful-basis review | Retention | Access and publication |
| --- | --- | --- | --- | --- |
| Lookup request | Normalize one supplied number and region; no requester identity, IP persistence, or raw lookup history | Existing read-only service still requires operator privacy review for each deployment jurisdiction | Request-memory lifetime only; metadata health counters contain no number | Requester receives result; no stored personal trail |
| Structured call report | Displayed normalized number, structured category/channel/outcome, occurrence time, moderation state, policy/retention time, pseudonymous receipt | Not approved; public intake disabled pending purpose, notice, controller/processor, necessity, balancing/consent, and rights review | Maximum 90 days proposed for report content, immediate deletion on valid request, shorter rejection schedule to be approved before activation | Restricted moderators and privacy operators; only thresholded aggregates may become public |
| Caller campaign | Bounded displayed values, categories, jurisdictions, dates, eligible evidence handles, confidence, freshness, actions, correction state | Not approved for production derivation from personal reports; official public-warning use requires source-specific review | Active lifecycle; proposed 24 months after resolution for public correction context, subject to review | Public only when evidence is eligible and privacy-thresholded; never reporter data or identity claims |
| Watch subscription | Number digest/reference, verified contact reference, consent receipt, state, last material version, expiry | Not approved; explicit opt-in and communications rules review required | Until revocation, deletion, consent expiry, or proposed 12 months inactivity | Subscriber and restricted operations only; never public or enumerable |
| Verification challenge | Purpose, subject reference, keyed challenge digest, attempt count, created/expiry/consumed times | Not approved; required to fulfill user-requested verification, subject to necessity and notice review | Proposed 15 minutes, then automatic deletion; consumed challenge deleted promptly | Verification service only |
| Organisation portfolio | Organisation reference, challenge evidence, bounded declared numbers, status, expiry, audit/correction state | Not approved; organisation authority, representative data, notice, conflicts, and appeal review required | Declaration lifetime plus proposed 24-month minimized audit receipts | Public declaration only after verification; never proof of call origin |
| Notification outbox | Idempotency key, aggregate reference/version, template code, delivery state, attempt count | Inherits approved watch purpose; provider role and communications rules require review | Pending until delivered/expired; proposed delivery metadata maximum 30 days | Delivery worker and restricted operations; no public access |
| Audit/deletion receipt | Pseudonymous record handle, kind, action, version, time, reason | Accountability/defence basis requires qualified review and documented necessity | Proposed 24 months, reviewed per action type | Restricted privacy/security operators; no aggregate content |
| Service health | Duration, typed status, source health, coarse country coverage | Legitimate operational purpose review required | Proposed 30 days aggregated; no raw number cardinality | Restricted operations; public only as coarse transparency metrics |

“Proposed” means a concrete engineering maximum that remains disabled until a qualified reviewer confirms necessity and jurisdictional fit. Approval must replace the status with owner, date, scope, and review expiry; it must not silently lengthen retention.

## Keys, encryption, and access boundaries

- Raw actor or contact proof enters only the verification boundary and is converted to a keyed digest or provider reference before persistence.
- Digest keys, database credentials, OAuth secrets, and delivery-provider credentials are separate secret-store values with distinct rotation and access policies.
- The repository and Vercel configuration contain secret names only. Secret values never enter Git, `.go` evidence, logs, screenshots, or public error output.
- A production database must encrypt transport and storage, support least-privilege roles for app, moderation, delivery, and privacy operations, and provide verified key rotation.
- Backups must inherit retention and deletion obligations. A provider cannot pass the gate until backup expiry and restoration access are tested.
- Public campaign and transparency read models are separate from private reports, watches, challenges, outbox data, and audit receipts.

## Rights and operational handling

Correction and deletion use an authenticated receipt or verified account context. Public endpoints must be anti-enumerable: the same response shape and timing must not reveal whether a report, watch, contact, or organisation record exists. Objection, appeal, source takedown, access, correction, deletion, provider outage, and breach handling require executable runbooks before activation.

Incident handling begins with containment and access revocation, then scope assessment, evidence preservation limited to necessity, secret rotation, affected-provider coordination, deletion/notification assessment, and a sanitized retrospective. Real numbers, report content, contacts, or tokens must not enter public issues.

## Explicit Vercel provider gate

The current Vercel deployment may run public read-only lookup, campaign catalogue, transparency, and remote MCP reads only from committed public-safe data. It may not accept reports, watches, organisation changes, or notification requests until all of these are proven:

1. qualified lawful-basis and privacy review is approved for the exact purpose, fields, jurisdictions, retention, and processors;
2. an approved durable provider implements `DataStore` and passes atomicity, isolation, retention, correction, deletion, backup, and outbox integration tests;
3. deployment secrets, key rotation, least privilege, encryption, regional/data-transfer terms, subprocessor inventory, and breach routes are configured;
4. authentication, consent, anti-enumeration, transport rate limits, moderation, appeal, and abuse controls pass;
5. deletion works across primary storage, outbox, delivery provider, analytics, logs, and backups within documented windows;
6. operational owner, privacy owner, security owner, rollback, kill switch, and incident exercise are recorded; and
7. repository gates, production probes, and a public privacy notice pass at the exact deployed revision.

Until then, `StorageProviderConfig.local_proof()` fails the public mutation gate by design.
