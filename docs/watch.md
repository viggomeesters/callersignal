# Private Number Watches

CallerSignal watches make the product useful after a one-off search: a person can privately monitor material changes to the campaign or risk context for a displayed number. A watch is never public, never increases a reputation score, and never proves that a number is safe or that a particular person called.

The private contract is [`schemas/watch-subscription.schema.json`](../schemas/watch-subscription.schema.json). The transport-independent domain workflow is [`src/callersignal/watch`](../src/callersignal/watch).

## Privacy model

The service accepts a normalized E.164 value and an email contact at its input boundary, then immediately derives separate keyed references:

- `num_<digest>` for the watched displayed number;
- `contact_<digest>` for the normalized contact;
- opaque watch, consent, challenge, message, and audit identifiers.

The store and notification payloads contain no raw phone number, email address, requester IP address, or lookup history. Digest and challenge keys belong in the deployment secret store and must be independently rotatable. A keyed reference is pseudonymous, not anonymous, so it remains private data and is never published.

## Verification and anti-enumeration

Starting a watch always returns the same sentence: “If the request is eligible, verification instructions will be sent.” Invalid input, an existing watch, and a rate-limited request use that same response. Public transport must keep status, shape, and timing close enough to avoid revealing whether a contact or watch exists.

An eligible request atomically creates:

1. a `pending_verification` watch with an explicit consent receipt and expiry;
2. a short-lived keyed challenge with attempt limit; and
3. one idempotent `watch.verify` outbox message addressed through a private contact reference.

Only the code delivered through that contact route can activate the watch. Wrong codes increment attempts; exhaustion locks the challenge; expiry deletes it; replay after success fails. A provider failure leaves the watch pending and records an outbox attempt—it never silently activates monitoring.

The local code factory and outbox are deterministic proof mechanisms. Public deployment additionally requires authenticated contact claims, an approved delivery provider, secret handling, retry/backoff, bounce processing, communications-law review, and the provider gate in [`privacy.md`](privacy.md).

## Lifecycle

| State | Meaning |
| --- | --- |
| `pending_verification` | Consent was recorded, but contact ownership is not proven. It is not returned by private listing. |
| `active` | Contact verification passed and the consent period has not expired. |
| `revoked` | The verified subscriber unsubscribed. No change notification can be created. |
| `expired` | Consent reached its explicit expiry. Re-verification is required for another active watch. |

A verified contact can privately list active watches, correct the watched scope, revoke, and delete. Scope correction stores only a new keyed number reference, clears the prior material fingerprint, records correction reasons, and keeps the verified contact and consent boundary. Revocation atomically disables the watch and queues one idempotent confirmation. Deletion removes the record and leaves only the minimized storage audit receipt.

Production transports must derive the contact reference from a verified session or OAuth claim. Supplying an email string alone is not authentication and must never be exposed as the public authorization mechanism.

## Material-change notifications

The event processor computes a fingerprint only from public-safe material state:

- campaign identifier and lifecycle status;
- calibrated risk state;
- correction status; and
- recommended action.

Freshness polling, lookup demand, source ordering, repeated identical events, and private report activity do not trigger a message. If the fingerprint changes, watch update and outbox message commit in one transaction. Replaying the same event is a no-op.

Notification content uses calibrated state and action codes, contains no accusation or hidden lookup trail, and always says that caller ID can be spoofed and no state proves safety. Revoked, expired, pending, missing, or unverified watches fail closed without an outbox event.

## Rate, outage, and deletion behavior

- Challenge requests are counted by keyed contact reference inside a fixed window.
- Existing-watch and rate-limit responses remain generic.
- Challenge attempts are bounded and use constant-time digest comparison.
- Delivery failure remains retryable in the transactional outbox and cannot change watch status.
- Consent expiry is checked deterministically and disables notifications.
- Unsubscribe is idempotent and immediately makes private listing empty.
- Deletion requires the verified contact boundary, removes watch content, and returns a minimized receipt.

The public website and hosted MCP expose no mutation route until the privacy, provider, authentication, abuse, communications, operations, and live-deployment gates pass.

## Verification

```console
uv run pytest tests/integration/test_watch.py -q
make check
```
