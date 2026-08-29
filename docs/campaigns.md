# Caller Campaigns

CallerSignal models recurring harmful-call context as a caller campaign, not as an accusation against a phone-number owner. The versioned contract is [`schemas/caller-campaign.schema.json`](../schemas/caller-campaign.schema.json); the deterministic derivation policy is [`src/callersignal/campaigns`](../src/callersignal/campaigns).

## Canonical language

### Caller campaign

A caller campaign is a derived, freshness-bounded pattern supported by eligible observations about calls displaying one or more exact numbers or bounded number patterns over time. It has its own lifecycle, evidence handles, confidence, actions, and correction state.

Avoid: “the owner of this number is running a scam.”

Example: two independent eligible sources observe the same impersonation pattern among calls displaying a reserved test number. CallerSignal can publish an `elevated_signals` campaign while still saying that caller ID can be spoofed.

### Campaign member

A campaign member is an exact displayed number or an explicitly bounded prefix plus a fixed number of following digits. Membership says only that matching values were displayed during observations; it does not identify a caller, subscriber, provider, or organisation.

Avoid: “campaign number” when that wording could imply ownership or origin.

Example: a prefix with `following_digits: 2` covers exactly one hundred displayed values; an unconstrained wildcard is invalid.

### Eligible evidence

Eligible campaign evidence is current, public, rights-approved regulatory, licensed reputation, or privacy-thresholded moderated aggregate evidence with an accepted verification status. Raw reports, restricted records, lookup activity, stale observations, and unsupported evidence classes remain outside campaign derivation.

### Verified organisation declaration

A verified declaration means an organisation completed the required challenge before declaring an official contact route. It does not prove that a matching call came from that organisation; spoofing remains possible.

## Lifecycle and fail-closed policy

| Status | Meaning |
| --- | --- |
| `active` | A current official warning applies or at least two independent eligible sources corroborate the same pattern. |
| `monitoring` | Evidence exists but is stale, ineligible, insufficient, uncorroborated, or contradictory. This is not a public risk verdict. |
| `resolved` | Eligible evidence supports that the observed pattern has ended; historical context and dates remain inspectable. |
| `retracted` | Correction review found that the campaign should no longer be published as supported. |

A current regulator warning can produce `official_warning` from one authoritative source. `elevated_signals` requires a shared pattern across at least two independent eligible source identifiers. Contradiction always fails closed to `monitoring` and opens correction review. Stale or ineligible evidence remains excluded and visible only through reason codes. No campaign state uses lookup volume.

The timeline requires timezone-aware values in this order: `first_seen <= last_seen <= assessed_at`. Invalid order is rejected before a public artifact is produced. Inputs and evidence are sorted into canonical order so identical evidence produces identical output regardless of arrival order.

## Public interpretation

Public renderers must show:

- the displayed-number or bounded-pattern semantics;
- status and calibrated risk state;
- first and last seen dates plus freshness;
- eligible evidence handles, source diversity, and reasons;
- a concrete recommended action;
- correction state and residual spoofing uncertainty.

They must not show private reports, reporter details, watch subscribers, raw lookup histories, or a claim that the subscriber or caller is known. Campaign pages consume this contract; they do not compute a separate verdict.

## Verification

```console
uv run pytest tests/contracts/test_caller_campaign.py -q
make check
```
