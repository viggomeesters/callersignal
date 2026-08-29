# Data Architecture

CallerSignal separates deterministic domain logic from persistence through the [`DataStore`](../src/callersignal/storage/ports.py) protocol. The committed [`LocalStore`](../src/callersignal/storage/local.py) is a process-local proof adapter for tests and development. It is not durable, shared, or approved for public mutation traffic.

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
make check
```
