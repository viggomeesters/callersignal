# Public Readiness Privacy Review

## Current decision — 29 August 2026

CallerSignal's current tree and Git history are public-safe. Automated secret,
private-content, large-binary, and generated-state checks are clean. The only
automated filename signals are two historical locations of the same public
workflow contract:

- `.go/tasks/open/product-private-watch-subscriptions.json`
- `.go/tasks/done/product-private-watch-subscriptions.json`

These are reviewed false positive findings. The word `private` names a product
privacy boundary: a watch subscription belongs to one consenting user and must
never become public reputation evidence. The task files contain architecture,
acceptance criteria, source paths, and synthetic test requirements. They do not
contain phone numbers, subscriber data, reports, lookup history, credentials,
tokens, customer records, or private screenshots. Renaming or rewriting
git-history would make the product contract less precise without reducing risk.

## Review method

The review covered the working tree, tracked files, and git-history filename
signals. It also checked the original session numbers, high-confidence secret
patterns, private-key headers, environment files, generated runtime state,
caches, exports, recordings, and large binaries. Public examples use only a
NANPA-reserved fictional number.

The repository's forbidden public content remains: real personal phone
numbers, contact or subscriber identities, raw call reports, lookup histories,
recordings, private exports or screenshots, credentials, tokens, unlicensed
datasets, and generated local runtime state. A clean review does not loosen
those boundaries.

## Ongoing gate

`make check` and the strict public `repo-complete` profile remain release
requirements. Any new privacy or filename signal requires a new human review;
this decision applies only to the two exact workflow paths above.
