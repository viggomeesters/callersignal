# Source rights and intake

CallerSignal grows from sources whose authority, reuse basis, field boundary, freshness, failure behavior, privacy posture, and provenance are known before ingestion. The normative decision record is [`sources/registry.json`](../sources/registry.json); [`source-registry.schema.json`](../schemas/source-registry.schema.json) makes unsafe state transitions fail validation.

This is an engineering control, not legal advice. Legal or privacy uncertainty keeps a source disabled.

## Current decision

The bounded ACM, Ofcom, and NANPA numbering fixtures are enabled for their declared factual fields. They are not risk-capable and cannot establish caller identity, subscriber identity, live location, or call safety.

`wieheeftmijgebeld_nl` is recorded as `permission_required`. It has no adapter, no evidence classes, no permitted ingestion fields, and no copied records. Its public pages contain phone-number records, ratings, activity counts, and user-authored narratives. Its copyright notice requires explicit written permission for reproduction or publication. CallerSignal therefore does not crawl, copy, transform, aggregate, cache, embed, or republish that content.

The review used the following primary sources on 2026-08-28:

- the publisher's [copyright notice](https://wieheeftmijgebeld.nl/copyright/), [contribution terms](https://wieheeftmijgebeld.nl/voorwaarden/), and [robots file](https://wieheeftmijgebeld.nl/robots.txt);
- the European Union's explanation of [copyright and sui generis database protection](https://europa.eu/youreurope/business/growing/protecting-intellectual-property/database-protection/index_en.htm);
- the European Commission's [GDPR principles](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en).

The site can be reconsidered only after written permission or a suitable license explicitly covers CallerSignal's intended extraction, storage, transformation, display, territories, commercial context, attribution, update cadence, and termination behavior.

## Seven independent gates

Every registry source has seven gate decisions. Passing one never implies another.

| Gate | Question answered | It does not prove |
| --- | --- | --- |
| `robots_access` | Does the publisher's current crawl-control file permit the intended automated path? | Copyright, database rights, contract permission, or privacy lawfulness |
| `reuse_permission` | Is there documented permission or a license for the exact intended reuse? | That every field is lawful or necessary to process |
| `copyright` | May protected selection, structure, text, and presentation be reproduced or transformed? | Database-right or privacy clearance |
| `database_rights` | May the intended quantity and cadence be extracted and reused? | Copyright, contract, or privacy clearance |
| `privacy` | Are purpose, lawful basis, minimization, retention, access, and data-subject operations approved? | That source content is accurate or non-defamatory |
| `takedown` | Can affected parties request correction, objection, deletion, appeal, and source removal? | Source authority or provenance |
| `provenance` | Can each admitted observation retain source, retrieval time, record identity, transformation, and digest? | Permission to obtain or publish it |

`robots_access: passed` is intentionally compatible with every other gate remaining `required`. Robots is a technical crawl signal, not a reuse license.

## Enablement rules

A source may become `enabled` only when:

1. the rights owner and stable source URL are identified;
2. the exact evidence classes and permitted fields are bounded;
3. permission, copyright, database-rights, and privacy decisions are documented;
4. personal data and free text are explicitly allowed or forbidden;
5. freshness and fail-closed outage behavior are declared;
6. correction, deletion, takedown, and provenance owners are operational;
7. its adapter and fixture pass the shared conformance suite; and
8. `uv run pytest tests/contracts/test_source_registry.py -q` and `make check` pass.

The JSON Schema additionally prevents a `permission_required` candidate from being enabled while its adapter is absent, fields are empty, or legal, privacy, takedown, and provenance gates remain open.

## Safe growth routes

Preferred database growth is, in order:

1. official regulatory warnings and public numbering facts under documented reuse terms;
2. licensed reputation feeds whose fields and downstream display rights are explicit; and
3. first-party structured reports only after moderation, privacy, retention, correction, deletion, appeal, anti-brigading, and abuse controls are approved and tested.

Search-engine snippets, manual copy-paste, rotating crawlers, or storing only derived ratings do not bypass source rights or privacy review. A derived value still needs authorized, traceable input.

## Change procedure

Add or change the registry entry before writing an adapter. Record review evidence rather than asserting that public visibility equals permission. Keep the entry disabled while any required gate is unresolved. A rights or policy change triggers a new review date, fixture provenance review, affected-data removal assessment, and full conformance run.

Report permission revocation, exposed personal data, or a takedown request through the private process in [`SECURITY.md`](../SECURITY.md), never with a real phone number in a public issue.
