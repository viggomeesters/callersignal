# Public web lookup and campaign experience

The CallerSignal website is a read-only renderer over the canonical lookup and public-campaign HTTP results. It adds no browser-only source query, reputation calculation, identity inference, report store, watch store, or persistence path.

## Product and design read

The page is a public incident desk for people and agents responding to an unfamiliar displayed number. Its visual language is calm, source-led, and regulator-like; the primary job is to make one calibrated risk state, the displayed number, coverage recency, a concrete next action, and relevant campaign history understandable in one scan.

The interface uses one light theme, one rust-red accent, dark neutral ink, compact squared geometry, a readable Segoe UI/Verdana-family type stack, and a subtle ledger grid. Its lookup signature is a large incident card that combines a text-and-icon state, plain-language headline, evidence basis, coverage strip, and recommended action. The coverage signature is a three-part evidence ledger: green plus “Available · official context” for the full ACM catalogue, ochre plus “Live · unverified complaints” for the FCC aggregate, and rust plus “Unavailable · commercial sources” for permission- or agreement-gated feeds. Text labels, counts, grouped reasons, and individual source decisions carry meaning without relying on colour. Four risk-state colour treatments likewise reinforce but never replace semantic differences. A three-step safety checklist and clearly gated report/watch controls follow immediately. Campaign history stays distinct from number-plan facts, and technical source records remain collapsed until requested. Design variance is moderate, motion is limited to result-state continuity, and information density increases only after a lookup.

The example row uses only source-reviewed public-safe values. Its Netherlands choice is `0906-8844`, a number recorded as blocked in the pinned CC0 ACM register fixture; it is not an invented 06 number and does not represent an ordinary mobile subscriber. Selecting it sets `origin_region=NL` and submits through the same canonical lookup endpoint as manual input. The US choice is from NANPA's fictional-use range and the GB choice is from Ofcom's protected drama range. A blocked or protected numbering status supplies context only and is not evidence that a displayed call is safe or harmful.

The public campaign index is intentionally allowed to be empty. `GET /v1/campaigns` returns only campaigns that pass the canonical aggregate-evidence threshold and have complete source-coverage records. `GET /v1/campaigns/{campaign_id}` adds exact source coverage, displayed-value membership, correction state, optional verified-organisation declaration context, recommended actions, and limitations. Projection drops undeclared fields, private reports, reporter data, and lookup activity. Monitoring campaigns or records with incomplete source coverage fail closed and are not published.

## Run and verify

From the repository root, start the same-origin browser-proof server:

```bash
PYTHONPATH=src uv run python tests/e2e/site_server.py
```

Open `http://127.0.0.1:8765/`. The local server serves only committed web assets and delegates `/v1/lookup`, `/v1/campaigns`, and `/v1/coverage` to `callersignal.http_api.application`. It serves campaign page routes through the same static renderer.

Run the web gates:

```bash
uv run pytest tests/e2e -q
npm --prefix web test
make check
```

The Node suite checks lookup and campaign URL construction, view-model parity, aggregate campaign projection, and distinct text/icon/tone mappings for all four canonical risk states. The Python end-to-end suite checks document semantics, metadata, result actions, progressive disclosure, focus and responsive CSS, safe DOM constraints, public-campaign non-disclosure, and the Vercel WSGI entrypoints.

## Browser proof

The real same-origin page and API were exercised in headless Chrome on 29 August 2026 using only the NANPA-reserved fictional number and explicitly synthetic browser-proof sources. No screenshot is evidence about a real caller or live campaign.

| Viewport | States inspected | Horizontal overflow | Clipped controls/text | Console warnings/errors |
| --- | --- | ---: | ---: | ---: |
| 375 × 812 | empty, coverage, unknown, elevated, official warning, campaign detail | 0 px | 0 | 0 |
| 1440 × 1000 | empty, coverage, unknown, elevated, official warning, campaign detail | 0 px | 0 | 0 |

Every risk result showed exactly one matching icon plus a text label, the reserved number as its title, source counts and recency, and the canonical action. The result heading received focus; the campaign-detail heading received focus on direct routes. The empty-state captures and machine facts show all three source-reviewed NL, US, and GB example choices, including the exact NL number and region binding. The coverage view showed 74,984 ACM ranges, 238,327 FCC keyed displayed numbers, 260,504 indexed FCC observations, one enabled reputation source, and all sixteen source decisions. It visibly separated official numbering context, live unverified complaints, and unavailable commercial sources. Machine facts in [`web/proof/browser-proof.json`](../web/proof/browser-proof.json) record zero horizontal overflow, clipped visible controls/text, internal content overflow, temporary copy, and console warnings/errors for all twelve captures. The three status-label contrast ratios were 8.68:1, 7.44:1, and 7.26:1. Visual inspection confirmed readable contrast and hierarchy, no overlap, stable squared geometry, compact mobile wrapping, and no raw inventory, complaint row, report, or lookup-popularity display.

Visual evidence:

- [desktop empty](../web/proof/desktop-1440-hero.jpg)
- [desktop coverage](../web/proof/desktop-1440-coverage.jpg)
- [desktop unknown](../web/proof/desktop-1440-unknown.jpg)
- [desktop elevated](../web/proof/desktop-1440-elevated.jpg)
- [desktop official warning](../web/proof/desktop-1440-official-warning.jpg)
- [desktop campaign detail](../web/proof/desktop-1440-campaign-detail.jpg)
- [mobile empty](../web/proof/mobile-375-hero.jpg)
- [mobile coverage](../web/proof/mobile-375-coverage.jpg)
- [mobile unknown](../web/proof/mobile-375-unknown.jpg)
- [mobile elevated](../web/proof/mobile-375-elevated.jpg)
- [mobile official warning](../web/proof/mobile-375-official-warning.jpg)
- [mobile campaign detail](../web/proof/mobile-375-campaign-detail.jpg)

Reproduce the browser proof after starting the local server:

```bash
npm install --no-save --no-package-lock playwright
node web/proof/capture.mjs
```

## Accessibility and state behaviour

- The page uses landmarks, a skip link, ordered headings, native labels and controls, polite live regions, and programmatically focused result/detail headings.
- Every interactive target has a visible focus treatment; the primary mobile target exceeds 44 px.
- Loading copy and the action label stay synchronized. Input, transport, rate-limit, and network errors give a next step.
- Report and private-watch controls explain their unavailable state and privacy prerequisites without collecting data or pretending that a mutation succeeded.
- Evidence-free and campaign-free states use explicit text rather than colour or an implied safety verdict.
- Motion is restricted to result transform and opacity, and is effectively disabled under `prefers-reduced-motion`.
- Dynamic source content is inserted with DOM nodes and `textContent`; untrusted values are never assigned through `innerHTML`.
- The page uses no analytics, cookies, local storage, third-party fonts, or lookup-history persistence.

## Vercel shape

`vercel.json` defines the static site, campaign page routes, same-origin `/v1/lookup`, `/v1/campaigns`, `/v1/coverage`, and `/healthz` rewrites, response-security headers, and Python function bundle. Its build command runs the checksum-pinned ACM builder, the full FCC aggregate builder, and the authenticated transparency generator before packaging. A bounded staging script copies only `web/index.html` and `web/assets/` into the ignored `public/` output directory, so tests, proof artifacts, and repository files cannot become static deployment output. Both generated ignored SQLite files are explicitly included in every Python function and activated through their catalog-path environment settings. `api/index.py`, `api/campaigns.py`, `api/coverage.py`, and `api/healthz.py` export the WSGI apps expected by Vercel and map platform paths to the canonical HTTP application. The repository-root `pyproject.toml` and `uv.lock` provide the pinned production dependency.

Deploy from the repository root. The function configuration explicitly includes `src/callersignal` and both generated catalogues; the deployment therefore bundles shared domain code and privacy-minimized official read models without committing source downloads, generated databases, maintaining a code copy, or adding a browser-only truth path. `CALLERSIGNAL_REPUTATION_INDEX_KEY` is required in the Vercel secret store to HMAC-key and authenticate the FCC catalogue; it must never be committed, echoed, placed in a URL, or exposed to the browser.

```bash
npx vercel@latest deploy --prod --yes
```

Before treating a deployment as shipped, verify the production homepage, campaign index and missing-detail behaviour, `/v1/lookup` success and validation responses, CSP/security headers, the deployment alias, and the GitHub homepage readback. Do not enable request logging that records raw query strings or add telemetry that contains phone numbers, IP addresses, origin regions, results, or lookup histories.

## Deployment proof and ownership boundary

CallerSignal is persistently hosted at [`https://callersignal.vercel.app/`](https://callersignal.vercel.app/) in the authenticated `viggos-projects-eac4720a/callersignal` Vercel project. Production deployment `dpl_2Ap8eGWHvg5qVxV1moTxDRKcB46P`, built from pushed commit `53b39ed`, reported `Ready` and owned the stable alias on 29 August 2026. Alias readback proved the homepage, health route, NL public-safe example, US FCC lookup, exact source coverage, and hosted MCP boundaries. A local or merely pushed revision is not presented as deployed proof.

Deployment is currently manual: the Vercel project owns the stable production alias, but its GitHub repository integration is not connected. A pushed revision is not live until a maintainer runs the documented production deploy and repeats the alias checks. Local `.vercel` linkage remains ignored generated state.
