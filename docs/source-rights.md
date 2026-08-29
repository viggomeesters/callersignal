# Source rights and intake

CallerSignal grows from sources whose authority, reuse basis, field boundary, freshness, failure behavior, privacy posture, and provenance are known before ingestion. The normative decision record is [`sources/registry.json`](../sources/registry.json); [`source-registry.schema.json`](../schemas/source-registry.schema.json) makes unsafe state transitions fail validation.

This is an engineering control, not legal advice. Legal or privacy uncertainty keeps a source disabled.

## Current decision

The bounded ACM, Ofcom, and NANPA numbering sources are enabled for their declared factual fields. They are not risk-capable and cannot establish caller identity, subscriber identity, live location, or call safety.

The FCC Consumer Complaints Data — Unwanted Calls source contract is authorized for a different and deliberately narrow purpose, but its runtime adapter remains disabled until the importer and read model pass their own tasks. Its official metadata declares the dataset `Public Domain U.S. Government` and exposes it through an anonymous Socrata API. CallerSignal may process only caller ID, issue date, and call/message type into a keyed aggregate. The FCC states that the data is selected by consumers and that it does not verify the alleged facts. An aggregate from this source is therefore an unverified consumer-complaint observation, not an FCC warning, verified caller identity, proof of harm, or safety verdict. [`sources/fcc-complaints-manifest.json`](../sources/fcc-complaints-manifest.json) fixes this source, query, field, storage, freshness, and semantic boundary.

`wieheeftmijgebeld_nl` is recorded as `permission_required`. It has no adapter, no evidence classes, no permitted ingestion fields, and no copied records. Its public pages contain phone-number records, ratings, activity counts, and user-authored narratives. Its copyright notice requires explicit written permission for reproduction or publication. CallerSignal therefore does not crawl, copy, transform, aggregate, cache, embed, or republish that content.

No caller-reputation runtime is currently enabled. The source index contains sixteen services: the one public-domain FCC data API authorized for build, eleven permission or product-fit candidates, and four advertised commercial licensing routes. An advertised product is not a CallerSignal licence. With the checked-in registry and no approved partner credential, the commercial activation engine creates zero reputation adapters and performs zero report-page or partner-API requests. The FCC contract authorizes only its separate manifest-bounded aggregate importer; making that projection operational is a reviewed downstream task.

The review used the following primary sources on 2026-08-28:

- the publisher's [copyright notice](https://wieheeftmijgebeld.nl/copyright/), [contribution terms](https://wieheeftmijgebeld.nl/voorwaarden/), and [robots file](https://wieheeftmijgebeld.nl/robots.txt);
- the FCC's [Consumer Complaints Data — Unwanted Calls dataset](https://opendata.fcc.gov/Consumer/Consumer-Complaints-Data-Unwanted-Calls/vakf-fz8e) and its linked [United States government-work terms](https://www.usa.gov/government-works);
- the European Union's explanation of [copyright and sui generis database protection](https://europa.eu/youreurope/business/growing/protecting-intellectual-property/database-protection/index_en.htm);
- the European Commission's [GDPR principles](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en).

The site can be reconsidered only after written permission or a suitable license explicitly covers CallerSignal's intended extraction, storage, transformation, display, territories, commercial context, attribution, update cadence, and termination behavior.

## International caller-report discovery index

[`sources/caller-report-services.json`](../sources/caller-report-services.json) records the dated discovery surface separately from the enabled source registry. The 2026-08-29 review found sixteen Dutch, national, and international services through four documented search themes plus the official FCC public-data route. Each entry records service and robots URLs, report and status capabilities, a terms or no-terms finding, reuse posture, integration route, blocking gates, and the next activation action. The matching [JSON Schema](../schemas/caller-report-service-index.schema.json) prevents a disabled source from carrying permitted fields and prevents enablement without documented rights.

Four operators currently advertise a plausible licensed route that warrants commercial evaluation: [tellows API partnerships](https://www.tellows.com/s/about-en/tellows-api-partnership-program), [Nomorobo business APIs](https://www.nomorobo.com/business/terms/), [Whoscall enterprise services](https://web.whoscall.com/en), and [Hiya partner APIs](https://developer.hiya.com/docs/getting-started/introduction). “Licensed access available” means only that an operator advertises a route. CallerSignal has no agreement, credentials, approved fields, or publication rights for these services, so every integration remains disabled.

The remaining discovered services require explicit permission or product-fit confirmation. Public report pages and permissive crawl paths are useful discovery signals, but they do not settle copyright, database rights, privacy, caching, derived classifications, or republication. The index intentionally contains no phone-number inventory, report text, user names, ratings, or lookup counts. Its scope is reproducible but not globally exhaustive: new services and changed terms require a dated review and schema-valid update.

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

The JSON Schema additionally prevents a `permission_required` source from being enabled while its adapter is absent, fields are empty, or legal, privacy, takedown, and provenance gates remain open.

## Authorized feed contract

[`src/callersignal/reputation`](../src/callersignal/reputation) implements the dormant production boundary for an authorized licensed feed. Activation is the intersection of two independent records: the discovery index must say that rights, integration, and activation are enabled, and the source registry must contain the same identifier as an enabled, risk-capable `licensed_reputation` source. All seven registry gates must pass, the runtime credential must exist, and the feed must use the bounded HTTPS JSON contract. A permissive robots file, a public page, a commercial product page, or a credential without republication rights cannot activate it.

The admitted response is fixed to an opaque source record identifier, a reviewed source-native category, observation time, and confidence. The normalizer maps only reviewed categories to `spam`, `phishing`, `scam`, `telemarketing`, `robocall`, `nuisance`, or explicit `no_current_risk_match`. Names, narratives, popularity, requester metadata, unexpected fields, unknown categories, and native `safe` claims are discarded or rejected. The evidence digest covers only the admitted aggregate projection; the raw response is not persisted.

The HTTP client requires HTTPS, blocks downgrade redirects, sends lookups in a JSON body, applies a short timeout and response-size limit, and never owns logging. The adapter has a fail-fast per-source rate limiter. The scheduler retains only the last attempt time per source; it does not retain numbers or requester history. Transport failure becomes `source_unavailable`, contract drift becomes `source_error`, and expired observations remain explicitly stale. None of those states becomes a safety claim.

Activating a real provider requires a schema-valid registry and service-index change containing the executed agreement reference, exact fields, jurisdictions, native-category map, rate and schedule terms, credential environment key, privacy decision, takedown owner, and provenance policy. Add provider conformance tests with synthetic protected numbers; never commit the credential or a copied production payload.

## FCC public complaint aggregate contract

The FCC source does not use the licensed-feed point-lookup path. Its [manifest](../sources/fcc-complaints-manifest.json) permits a five-year rolling, server-side grouped query over three source fields. Only the reviewed `Prerecorded Voice` and `Autodialed Live Voice Call` values map to `robocall`; `Live Voice`, `Abandoned Calls`, and `Text Message` map to the neutral `nuisance` category. Empty, unknown, email, and drifted values are excluded rather than guessed.

The importer may hold a caller-ID value only long enough to validate US structure and derive an HMAC-SHA256 lookup key from a deployment secret. Plaintext number inventories, raw rows, ticket IDs, advertiser numbers, reporter location, ZIP codes, free text, and source responses are forbidden from persistence and Git. The projection retains only keyed category counts, bounded first/last dates, dataset provenance, content digest, build time, rolling window, and coverage totals. A missing key, stale metadata, schema drift, incomplete pagination, or failed replacement becomes a typed gap and leaves the prior valid catalogue untouched.

## Safe growth routes

Preferred database growth is, in order:

1. official regulatory warnings and public numbering facts under documented reuse terms;
2. licensed reputation feeds whose fields and downstream display rights are explicit; and
3. first-party structured reports only after moderation, privacy, retention, correction, deletion, appeal, anti-brigading, and abuse controls are approved and tested.

Search-engine snippets, manual copy-paste, rotating crawlers, or storing only derived ratings do not bypass source rights or privacy review. A derived value still needs authorized, traceable input.

## Change procedure

Add or change the registry entry before writing an adapter. Record review evidence rather than asserting that public visibility equals permission. Keep the entry disabled while any required gate is unresolved. A rights or policy change triggers a new review date, fixture provenance review, affected-data removal assessment, and full conformance run.

Report permission revocation, exposed personal data, or a takedown request through the private process in [`SECURITY.md`](../SECURITY.md), never with a real phone number in a public issue.
