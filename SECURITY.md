# Security Policy

## Supported versions

CallerSignal v0.1.x covers repository contracts, documentation, and workflow tooling. It does not yet provide a deployed lookup service. Security fixes apply to the latest release on the default branch; older foundation snapshots are not maintained.

## Report privately

Do not disclose a vulnerability, credential, real phone number, call report, request trace, or other personal data in a public issue or discussion.

Use [GitHub private vulnerability reporting](https://github.com/viggomeesters/callersignal/security/advisories/new). Include the affected revision, impact, minimal reproduction, and suggested mitigation. Replace personal values with reserved fictional data or structural redaction.

If private reporting is unavailable, open a public issue that contains no vulnerability detail or private data and ask a maintainer to establish a private channel.

## Response expectations

Maintainers aim to acknowledge a complete report within five business days, assess severity and exposure, coordinate a fix and disclosure window, and publish a sanitized advisory when users need to act. Timelines depend on impact and reproducibility; the reporter will receive updates through the private advisory.

## Scope

In scope are repository tooling, schemas, product code, dependency or supply-chain risks, source-ingestion boundaries, authorization and rate-limit bypasses, privacy leaks, unsafe logging, and evidence or assessment integrity failures.

Claims about a third-party phone number or caller are not security reports. Never submit real personal data as proof. Use [`SUPPORT.md`](SUPPORT.md) for ordinary project questions and [`docs/data-safety.md`](docs/data-safety.md) for the product's privacy boundary.

## Safe-harbor intent

Good-faith research that avoids privacy harm, service disruption, persistence, social engineering, and unauthorized data access will be handled constructively. This statement does not authorize testing of third-party systems or datasets.
