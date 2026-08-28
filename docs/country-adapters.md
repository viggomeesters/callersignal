# Country adapter contract

Country adapters translate an official or otherwise explicitly declared source into CallerSignal source evidence. They do not identify a caller, decide whether a call is safe, or infer reputation from lookup demand.

## Canonical terms

### Source declaration

The stable statement of an adapter's country coverage, source authority, reuse basis, license, permitted claims, freshness limit, failure behavior, and portability limitations.

Avoid: treating an implementation name as sufficient provenance.

Example: an NL adapter may declare that it publishes range-allocation facts from a regulator, while warning that allocation does not establish the current provider or caller.

### Source observation

An immutable public fact attributed to the declared source and checked at a known time. An observation is evidence, not an assessment.

Avoid: verdict, identity result, or caller profile.

Example: a public register states which organization holds a number range; CallerSignal preserves that statement as `range_holder` evidence without naming the subscriber.

### Evidence gap

A typed explanation of evidence that could not be supplied. Gaps distinguish no authoritative record, unsupported jurisdiction, restricted reuse, staleness, source failure, and temporary unavailability.

Avoid: translating a gap into “safe”, “clean”, or “no complaints”.

Example: a regulator endpoint times out, so the adapter returns `source_unavailable` with `retryable: true` and the public state remains unknown.

### Range holder

The organization to which a source says a number range was allocated. It is not necessarily the original carrier, current provider, subscriber, displayed caller, or person who placed a call.

### Provider claim

A source-attributed statement about a communications provider. Number portability means an original allocation and a current-provider claim may differ; neither proves subscriber or caller identity.

## Implementation boundary

Before implementation begins, the source must pass the intake process in [`docs/source-rights.md`](source-rights.md) and have an `enabled` record in [`sources/registry.json`](../sources/registry.json). The registry is authoritative for enablement; an adapter declaration alone cannot authorize ingestion. Permission-required and disabled sources have no enabled adapter and return no evidence.

An enabled adapter implements the structural `CountryAdapter` protocol in `src/callersignal/adapters/base.py`. It accepts an already normalized phone-number record and a timezone-aware check time, then returns one `AdapterResult`:

- `matched` contains one or more explicitly public observations from the declared source;
- `no_match`, `unavailable`, `unsupported`, and `error` contain no observations and include the corresponding typed gap;
- `stale` may preserve observations only when every observation is marked stale, always includes a `source_stale` gap, and remains publicly unknown.

Subscriber identity claims and restricted observations are rejected at this boundary. Evidence must use a claim type listed by the source declaration and carry the same `source_id`. Returned evidence views are detached from stored adapter state.

## Conformance

Every country implementation must run the shared contract suite alongside its own source-specific tests. Conformance demonstrates complete source metadata, registry parity, public-only observations, explicit freshness, immutable results, and fail-closed gaps. It does not certify source availability or authorize data reuse; those remain properties of the registry decision and its documented rights basis.

The normative record shapes are [`source-registry.schema.json`](../schemas/source-registry.schema.json), [`source-evidence.schema.json`](../schemas/source-evidence.schema.json), and [`lookup-result.schema.json`](../schemas/lookup-result.schema.json). The protocol deliberately mirrors their status and gap vocabulary so CLI, MCP, HTTP, and web surfaces can consume one result model.
