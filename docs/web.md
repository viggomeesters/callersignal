# Public web lookup

The CallerSignal website is a read-only renderer over the canonical HTTP result. It adds no browser-only source query, reputation calculation, identity inference, or persistence path.

## Product and design read

The page is a public incident desk for people and agents responding to an unfamiliar displayed number. Its visual language is calm, source-led, and regulator-like; the primary job is to make the calibrated risk state, next action, country interpretation, evidence, unknowns, and spoofing risk understandable in one scan.

The interface uses one light theme, one rust-red accent, dark neutral ink, compact squared geometry, a readable Segoe UI/Verdana-family type stack, and a subtle ledger grid. Its signature is a large state panel that combines an icon, explicit state label, headline, evidence basis, and recommended action. Four colour treatments reinforce but never replace those semantic differences. The number transcript then keeps country context, national display, international display, and number type visibly linked. Design variance is moderate, motion is limited to result-state continuity, and information density increases only after a lookup.

## Run and verify

From the repository root, start the same-origin browser-proof server:

```bash
PYTHONPATH=src uv run python tests/e2e/site_server.py
```

Open `http://127.0.0.1:8765/`. The local server serves only the committed web assets and delegates `/v1/lookup` to `callersignal.http_api.application`.

Run the web gates:

```bash
uv run pytest tests/e2e -q
npm --prefix web test
make check
```

The Node suite checks URL construction, view-model parity, and distinct text/icon/tone mappings for all four canonical risk states. The Python end-to-end suite checks document semantics, metadata, risk landmarks, form labels, focus and responsive CSS, reduced-motion handling, safe DOM constraints, and the Vercel WSGI entrypoint against the canonical lookup schema.

## Browser proof

The real same-origin page and API were exercised in a browser on 28 August 2026 using only reserved, fictional, or protected fixtures.

| Viewport | Result | Horizontal overflow | Console warnings/errors |
| --- | --- | ---: | ---: |
| 375 × 812 | Risk result rendered and visually inspected | 0 px | 0 |
| 390 × 844 | Risk result responsive probe | 0 px | 0 |
| 768 × 900 | Risk result responsive probe | 0 px | 0 |
| 1024 × 900 | Risk result responsive probe | 0 px | 0 |
| 1440 × 1000 | Risk result rendered and visually inspected | 0 px | 0 |

The reserved US fixture correctly rendered `insufficient_evidence` because its numbering source is not risk-capable. The panel showed exactly one question icon, the canonical headline and action, no overlap, no placeholder text, and 8.68:1 or better foreground/background contrast across all four state palettes. The result heading received focus, the primary button remained 51 px high, and the shared spoofing warning remained visible. Source confidence appeared only as a small text row with the explicit note that it rates observations rather than safety; no percentage bar remained.

Visual evidence:

- [desktop hero](../web/proof/desktop-hero-1440.jpg)
- [desktop risk result](../web/proof/desktop-risk-result-1440.jpg)
- [mobile hero](../web/proof/mobile-hero-375.jpg)
- [mobile risk result](../web/proof/mobile-risk-result-375.jpg)

## Accessibility and state behavior

- The page uses landmarks, a skip link, ordered headings, native labels and controls, a polite live region, and a programmatically focused result heading.
- Every interactive target has a visible focus treatment; the primary mobile target exceeds 44 px.
- Loading copy and the action label stay synchronized. Input, transport, rate-limit, and network errors give a next step.
- Evidence-free and gap-free states use explicit text rather than color or an implied safety verdict.
- Motion is restricted to result transform and opacity, and is effectively disabled under `prefers-reduced-motion`.
- Dynamic source content is inserted with DOM nodes and `textContent`; untrusted values are never assigned through `innerHTML`.
- The page uses no analytics, cookies, local storage, third-party fonts, or lookup-history persistence.

## Vercel shape

`vercel.json` defines the static site, same-origin `/v1/lookup` and `/healthz` rewrites, response-security headers, and Python function bundle. `api/index.py` and `api/healthz.py` export the WSGI apps expected by Vercel and map platform paths to the canonical HTTP application. The repository-root `pyproject.toml` and `uv.lock` provide the pinned production dependency.

Deploy from the repository root. The function configuration explicitly includes `src/callersignal`; the deployment therefore bundles shared domain code without maintaining a copy or a browser-only truth path. No production secret is required for the read-only pinned-source wedge.

```bash
npx vercel@latest deploy --prod --yes
```

Before treating a deployment as shipped, verify the production homepage, `/v1/lookup` success and validation responses, CSP/security headers, the deployment alias, and the GitHub homepage readback. Do not enable request logging that records raw query strings or add telemetry that contains phone numbers, IP addresses, origin regions, results, or lookup histories.

## Deployment proof and ownership boundary

CallerSignal is persistently hosted at [`https://callersignal.vercel.app/`](https://callersignal.vercel.app/) in the authenticated `viggos-projects-eac4720a/callersignal` Vercel project. Production deployment `dpl_C2AynN94S1GLXHVgny7DLdVkfVcG`, built from pushed commit `08376c5`, was read back as `Ready` on 28 August 2026 with separate Python functions for lookup and health.

The stable homepage and reserved US lookup both returned `200`; the lookup returned schema `1.0.0`, two public evidence records, `assessment.risk.state=insufficient_evidence`, action `treat_as_unknown`, the shared spoofing warning, and `Cache-Control: no-store`. The homepage exposed CSP, HSTS, referrer, permissions, MIME-sniffing, and frame-denial headers. A real-browser production lookup rendered the canonical headline and action, exactly one state icon, no confidence bar, focused `result-title`, had zero horizontal overflow, and produced no console warnings or errors.

Deployment is currently manual: the Vercel project owns the stable production alias, but its GitHub repository integration is not connected. A pushed revision is not live until a maintainer runs the documented production deploy and repeats the alias checks. Local `.vercel` linkage remains ignored generated state.
