# Data Architecture

CallerSignal separates deterministic domain logic from persistence through the [`DataStore`](../src/callersignal/storage/ports.py) protocol. The committed [`LocalStore`](../src/callersignal/storage/local.py) is a process-local proof adapter for tests and development. It is not durable, shared, or approved for public mutation traffic.

## Official ACM read catalogue

The complete Dutch ACM telephone-number register is a separate read-only projection, not a user-data store. [`sources/acm-bulk-manifest.json`](../sources/acm-bulk-manifest.json) pins the official ACM download URL, government catalogue, CC0 declaration, retrieval time, archive and CSV sizes, SHA-256 digest, member name, encoding, delimiter, and exact sixteen-column source contract. Build it with:

```console
make build-acm-catalog
```

The command downloads the declared ZIP over HTTPS, verifies its checksum and structure, validates every source row, and builds `downloads/acm-number-register.sqlite3`. A temporary database is atomically renamed only after the full import commits. Checksum drift, a malformed or unexpected archive, CSV schema drift, duplicate record identifiers, malformed or reversed ranges, invalid mutation timestamps, and an empty dataset leave any previous catalogue untouched.

Every source row becomes one `number_ranges` record so coverage and source status remain auditable. The projection retains only the source record identifier, normalized national interval, optional NL E.164 interval, destination, neutral number type, register status, mutation time, and a deterministic source-row digest. It deliberately omits range-holder names, relation identifiers, KVK values, establishment identifiers, application metadata, decision dates, network-area fields, and places. A row digest supports provenance without reproducing omitted values.

`catalog_metadata` records source and dataset URLs, license, retrieval time, source digest, total and matchable row counts, status counts, destination counts, and newest mutation. Generated downloads, SQLite files, sidecars, and local generated-data directories are ignored by Git. The catalogue contains official numbering context only: it is not a subscriber, caller-identity, live-provider, reputation, or safety database.

The Netherlands adapter activates this full catalogue only through an explicit `catalog_path` or `CALLERSIGNAL_ACM_CATALOG_PATH`. It opens SQLite in immutable read-only mode, validates the catalogue identity, schema, source digest, coverage counts, matching record, status, type, timestamp, and row digest, then selects the narrowest matching canonical E.164 interval deterministically. A catalogue result emits only `number_type` and normalized `regulatory_status`; it does not expose destination text, range bounds, holder data, KVK data, provider claims, or identities.

Missing or invalid catalogues never turn the one-record fixture into global coverage. The fixture may answer only its exact documented public-safe record; every other request returns a retryable `source_unavailable` gap. A valid full catalogue can return an authoritative `no_authoritative_data` no-match. Stale matching rows remain visible as stale numbering context with a `source_stale` gap. This distinction prevents an unavailable bulk dataset from being mistaken for absence of evidence.

The current pinned release imports 74,984 rows, of which 73,409 have a lookup-compatible NL interval. It contains 73,221 `Toegekend`, 1,740 `Afkoelen`, and 23 `Geblokkeerd` records across 44 destination labels; the newest source mutation is 2026-08-28. These values are both build readback and pinned release expectations: deployment fails closed if the generated catalogue differs. Refreshing the pin requires a new checksum, reviewed expectations, full rebuild, coverage comparison, source-rights review, and repository gate run.

[`web/assets/transparency.json`](../web/assets/transparency.json) is the committed public-safe coverage projection. It exposes only aggregate catalogue counts, normalized status coverage, destination-category count, source digest, retrieval time, newest source mutation, and freshness. HTTP, CLI, stdio MCP, hosted MCP, and the website all consume that object. It contains no ranges, destination counts, holders, organisations, subscriber or provider fields, reports, requester activity, lookup demand, or credentials.

Caller-report services are indexed separately in [`sources/caller-report-services.json`](../sources/caller-report-services.json). Discovery does not activate ingestion. A reputation source becomes usable only when the index and canonical source registry both prove compatible rights, permitted fields, credentials where required, privacy, correction, takedown, provenance, rate, size, schedule, and drift gates. The public-domain FCC aggregate is the one enabled reputation source; permission-required sites still receive no automated report-page requests.

The authorized FCC public-data route uses a separate bulk boundary. `scripts/build_fcc_catalog.py` validates official dataset metadata, public-domain terms, the exact twelve-column source schema, a five-year rolling grouped query, supported categories, and complete pagination. It transiently normalizes only the permitted caller-ID, issue-date, and call-type fields, immediately replaces each valid US number with HMAC-SHA256 under `CALLERSIGNAL_REPUTATION_INDEX_KEY`, and writes a new immutable SQLite catalogue only after the whole build validates. The importer reads source metadata again before replacement and rejects the build if the FCC update identity changed during pagination. The database retains keyed nuisance/robocall counts, first/last issue dates, public-safe coverage metadata, and an HMAC-derived projection digest. It never retains plaintext number inventory, raw complaint rows, ticket or advertiser identifiers, reporter attributes, narratives, or source responses. A prior valid catalogue survives every failed build.

The US adapter opens that SQLite file in immutable read-only mode and performs one indexed HMAC lookup. Before returning evidence it verifies the exact table and metadata schemas, source identity and URLs, licence, count and date invariants, the deployment-key verifier, and an HMAC authenticator covering all catalogue metadata. A missing file or key returns `source_unavailable`; a mismatched key or invalid catalogue returns `source_error`; an expired catalogue returns explicitly stale evidence. A current match yields only low-confidence unverified complaint aggregates, while a current absence yields `no_authoritative_data` and never a safe verdict.

## Aggregate boundary

The port recognizes four aggregate kinds:

| Kind | Purpose | Typical expiry |
| --- | --- | --- |
| `report` | Structured first-party observation about a call displaying a number | Explicit report retention deadline |
| `campaign` | Public-safe derived risk pattern with evidence and correction state | Policy-defined lifecycle plus resolved-history period |
| `watch` | Private, verified monitoring subscription | Consent expiry, revocation, or inactivity deadline |
| `verification_challenge` | Short-lived contact or organisation control proof | Minutes, never indefinite |

Notification messages use a separate transactional outbox. Audit receipts record mutation metadata without copying aggregate content. Raw lookup requests and histories have no persistence aggregate.

## Atomic transaction contract

All record mutations run through one transaction object. A transaction can create or deduplicate a record, apply an optimistic versioned correction, delete a record, and enqueue an idempotent outbox message. The adapter publishes none of those staged changes until the context exits successfully. A privacy validation error or any other exception leaves both aggregate and outbox unchanged.

This makes the critical workflow atomic:

```text
material state change
  -> update aggregate version
  -> enqueue one idempotent notification
  -> commit both, or commit neither
```

Outbox delivery records attempts separately. A failed attempt stays pending; a successful attempt records delivery time; another success call returns the completed message unchanged. Delivery providers do not mutate campaign or watch truth.

## Deterministic local adapter

`LocalStore` provides executable proof for:

- explicit deduplication keys scoped by aggregate kind;
- all four aggregate types;
- transaction rollback on nested privacy violations;
- optimistic version checks for corrections;
- content deletion plus minimized audit receipts;
- scheduled and read-time retention expiry;
- idempotent transactional outbox creation and retry state;
- stable ordering for records, receipts, and pending messages.

The adapter stores data only in process memory. Restarting deletes it. That property is useful for tests but disqualifies it from public report, watch, or verification traffic.

## Privacy guardrail

Every nested payload is inspected before staging. Keys for requester IP addresses, requester identity, raw actor tokens, and raw lookup history are forbidden. This guard supplements, but does not replace, provider schema constraints, transport minimization, access control, encryption, logging policy, and review.

Audit receipts contain only action, aggregate kind, pseudonymous record handle, version, time, and reason. They do not copy report narratives, displayed numbers, contact details, or notification bodies.

## Replaceable production provider gate

`StorageProviderConfig` carries a provider identifier and the name of an environment secret, never a connection string or credential value. `local_memory` always fails `require_public_mutation_ready()`. A durable provider may pass only when `approved_for_public_mutation` is explicitly true after the privacy, legal, security, deletion, backup, incident, and operations reviews in [`privacy.md`](privacy.md).

No production adapter is selected in this repository revision. Vercel continues to serve read-only lookup traffic. Adding a provider requires a separately reviewed adapter that conforms to `DataStore`, executes the same tests against isolated infrastructure, proves transaction and retention behavior, and reads credentials from the deployment secret store.

## Verification

```console
uv run pytest tests/storage -q
uv run pytest tests/unit/test_acm_catalog.py -q
uv run pytest tests/unit/test_fcc_catalog.py -q
make check
```
