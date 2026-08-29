# Verified Organisation Portfolios

CallerSignal lets an organisation declare a bounded set of official contact numbers after proving control of its domain contact route. The result helps people independently find a declared route. It does **not** prove that a call displaying one of those numbers originated from the organisation: caller ID can be spoofed.

The public projection validates against [`schemas/organization-portfolio.schema.json`](../schemas/organization-portfolio.schema.json). Challenge, conflict, appeal, correction, and deletion behavior lives in [`src/callersignal/organizations`](../src/callersignal/organizations).

## Claim semantics

`organization_declared_official_contact_routes` means exactly:

1. an administrator used an email address on the declared domain;
2. the short-lived challenge sent to that domain route was completed;
3. the organisation declared the listed numbers as official contact routes; and
4. the declaration is within its verification period and has no unresolved conflict or impersonation review.

It does not establish current number ownership, subscriber identity, employee identity, call origin, authenticity of caller ID, or safety. Public UI and MCP responses must pair the declaration with the origin/spoofing limitations from the schema.

## Challenge workflow

An eligible request atomically creates a private organisation record, a short-lived keyed challenge, and an idempotent outbox message. The administrator address must use the declared domain. The stored record contains only a keyed administrator reference; the public projection excludes it.

Before challenge success, `public_portfolio()` returns no record. Wrong codes increment a bounded attempt counter, attempt exhaustion locks the challenge, expiry deletes it, and a consumed challenge cannot be replayed. A correct code records verification and its explicit expiry, then removes the challenge.

The deterministic email-code flow is local proof. A production workflow may add DNS or stronger business verification, but must preserve the same narrow claim scope and pass the provider, privacy, authentication, abuse, and operations gates before mutation is exposed.

## Bounded portfolio and conflicts

The initial contract allows one to twenty unique E.164 numbers per organisation. Repository tests use only NANPA-reserved fictional values. Every entry carries a neutral label, active/retired status, and declaration time.

Before initial publication or any change, the service checks other verified portfolios. A number declared by two organisations fails closed to `conflict_review`; neither the new declaration nor its challenge becomes a public verified claim. The control challenge is still consumed, the conflict is audited, and correction state opens for review. Once the conflicting declaration changes or is removed, a documented appeal decision may reinstate the bounded portfolio without claiming that either organisation originated calls.

Changes require the already verified administrator boundary, replace the complete bounded set, and create a versioned `portfolio_updated` audit receipt. Public transports must supply that administrator reference from an authenticated organisation session or OAuth claim; an email string alone is not production authentication.

## Impersonation, correction, appeal, and deletion

- A credible impersonation report immediately suspends public projection and opens `under_review` correction state.
- Moderation can resolve an appeal by reinstating a still-current verification or revoking the declaration; the decision and reason are audited.
- Verification expiry removes the portfolio from public results until another challenge succeeds.
- A verified administrator can delete a verified, suspended, expired, or revoked portfolio; content is removed and a minimized audit receipt remains.
- Missing records, wrong administrator context, stale challenges, and invalid appeal transitions return the same verification failure boundary.

Impersonation reports are moderation signals, not proof of organisation wrongdoing. They cannot alter phone-number risk directly. Any campaign impact must come from separately eligible evidence through the shared assessment policy.

## Public rendering

Renderers may show the organisation name, domain, jurisdiction, verification dates, bounded number declarations, correction state, and limitations. They must not show administrator references, challenge state, attempt counts, outbox messages, private reports, or hidden lookup activity.

Use wording such as “Declared official contact route” and “Verify through this independently opened website.” Never use “verified caller,” “this call is genuine,” or a trust badge that visually guarantees call origin.

## Production gate

Organisation mutations remain absent from the public website, HTTP API, and hosted MCP until durable storage, qualified legal/privacy review, organisation authentication, domain-delivery controls, conflict moderation, appeals ownership, abuse limits, deletion, incident operations, and live deployment probes pass. Read-only public projection can ship only from schema-valid, non-expired, conflict-free records.

## Verification

```console
uv run pytest tests/integration/test_organizations.py -q
make check
```
