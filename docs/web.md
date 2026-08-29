# Public web lookup and campaign experience

The CallerSignal website is a read-only renderer over the canonical lookup and public-campaign HTTP results. It adds no browser-only source query, reputation calculation, identity inference, report store, watch store, or persistence path.

## Product and design read

The page is a public incident desk for people and agents responding to an unfamiliar displayed number. Its visual language is calm, source-led, and regulator-like; the primary job is to make one calibrated risk state, the displayed number, coverage recency, a concrete next action, and relevant campaign history understandable in one scan.

The interface uses one light theme, one rust-red accent, dark neutral ink, compact squared geometry, a readable Segoe UI/Verdana-family type stack, and a subtle ledger grid. Its signature is a large incident card that combines a text-and-icon state, plain-language headline, evidence basis, coverage strip, and recommended action. Four colour treatments reinforce but never replace semantic differences. A three-step safety checklist and clearly gated report/watch controls follow immediately. Campaign history stays distinct from number-plan facts, and technical source records remain collapsed until requested. Design variance is moderate, motion is limited to result-state continuity, and information density increases only after a lookup.

The example row uses only source-reviewed public-safe values. Its Netherlands choice is `0906-8844`, a number recorded as blocked in the pinned CC0 ACM register fixture; it is not an invented 06 number and does not represent an ordinary mobile subscriber. Selecting it sets `origin_region=NL` and submits through the same canonical lookup endpoint as manual input. The US choice is from NANPA's fictional-use range and the GB choice is from Ofcom's protected drama range. A blocked or protected numbering status supplies context only and is not evidence that a displayed call is safe or harmful.

The public campaign index is intentionally allowed to be empty. `GET /v1/campaigns` returns only campaigns that pass the canonical aggregate-evidence threshold and have complete source-coverage records. `GET /v1/campaigns/{campaign_id}` adds exact source coverage, displayed-value membership, correction state, optional verified-organisation declaration context, recommended actions, and limitations. Projection drops undeclared fields, private reports, reporter data, and lookup activity. Monitoring campaigns or records with incomplete source coverage fail closed and are not published.

## Run and verify

From the repository root, start the same-origin browser-proof server:

```bash
PYTHONPATH=src uv run python tests/e2e/site_server.py
```

Open `http://127.0.0.1:8765/`. The local server serves only committed web assets and delegates `/v1/lookup` and `/v1/campaigns` to `callersignal.http_api.application`. It serves campaign page routes through the same static renderer.

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

Every risk result showed exactly one matching icon plus a text label, the reserved number as its title, source counts and recency, and the canonical action. The result heading received focus; the campaign-detail heading received focus on direct routes. The empty-state captures and machine facts show all three source-reviewed NL, US, and GB example choices, including the exact NL number and region binding. The coverage view showed the exact public snapshot of three enabled numbering jurisdictions, zero risk-capable sources, zero eligible campaigns, and zero verified portfolios. Machine facts in [`web/proof/browser-proof.json`](../web/proof/browser-proof.json) record zero horizontal overflow, clipped visible controls/text, temporary copy, and console warnings/errors for all twelve captures. Visual inspection confirmed readable state contrast, no overlap, stable squared geometry, compact mobile wrapping, and no raw report or lookup-popularity display.

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

`vercel.json` defines the static site, campaign page routes, same-origin `/v1/lookup`, `/v1/campaigns`, and `/healthz` rewrites, response-security headers, and Python function bundle. `api/index.py`, `api/campaigns.py`, and `api/healthz.py` export the WSGI apps expected by Vercel and map platform paths to the canonical HTTP application. The repository-root `pyproject.toml` and `uv.lock` provide the pinned production dependency.

Deploy from the repository root. The function configuration explicitly includes `src/callersignal`; the deployment therefore bundles shared domain code without maintaining a copy or a browser-only truth path. No production secret is required for the read-only pinned-source wedge.

```bash
npx vercel@latest deploy --prod --yes
```

Before treating a deployment as shipped, verify the production homepage, campaign index and missing-detail behaviour, `/v1/lookup` success and validation responses, CSP/security headers, the deployment alias, and the GitHub homepage readback. Do not enable request logging that records raw query strings or add telemetry that contains phone numbers, IP addresses, origin regions, results, or lookup histories.

## Deployment proof and ownership boundary

CallerSignal is persistently hosted at [`https://callersignal.vercel.app/`](https://callersignal.vercel.app/) in the authenticated `viggos-projects-eac4720a/callersignal` Vercel project. The last production readback before this campaign-experience task was deployment `dpl_C2AynN94S1GLXHVgny7DLdVkfVcG`, built from pushed commit `08376c5` and reported `Ready` on 28 August 2026. The release task must replace this paragraph with the new deployment identifier and live campaign-route checks; a local or pushed revision is not presented as deployed proof.

Deployment is currently manual: the Vercel project owns the stable production alias, but its GitHub repository integration is not connected. A pushed revision is not live until a maintainer runs the documented production deploy and repeats the alias checks. Local `.vercel` linkage remains ignored generated state.
