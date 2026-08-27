# Public web lookup

The CallerSignal website is a read-only renderer over the canonical HTTP result. It adds no browser-only source query, reputation calculation, identity inference, or persistence path.

## Product and design read

The page is a public evidence desk for people and agents responding to an unfamiliar displayed number. Its visual language is calm, source-led, and regulator-like; the primary job is to make country interpretation, evidence, unknowns, confidence, and spoofing risk understandable in one scan.

The interface uses one light theme, one rust-red accent, dark neutral ink, compact squared geometry, a readable Segoe UI/Verdana-family type stack, and a subtle ledger grid. The signature element is the number transcript: country context, national display, international display, and number type remain visibly linked before any assessment appears. Design variance is moderate, motion is limited to result-state continuity, and information density increases only after a lookup.

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

The Node suite checks URL construction and view-model parity for evidence and unknown states. The Python end-to-end suite checks document semantics, metadata, form labels, focus and responsive CSS, reduced-motion handling, safe DOM constraints, and the Vercel WSGI entrypoint against the canonical lookup schema.

## Browser proof

The real same-origin page and API were exercised in a browser on 27 August 2026 using only reserved, fictional, or protected fixtures.

| Viewport | Result | Horizontal overflow | Console warnings/errors |
| --- | --- | ---: | ---: |
| 375 × 812 | Hero, validation, success, and result inspected | 0 px | 0 |
| 390 × 844 | Validation and no-evidence state inspected | 0 px | 0 |
| 768 × 900 | Success result inspected | 0 px | 0 |
| 1024 × 900 | Success result inspected | 0 px | 0 |
| 1440 × 1000 | Hero and success result inspected | 0 px | 0 |

At 1440 px the hero heading occupies two lines and the primary action is visible in the initial viewport. At 375 px the primary button is 51 px high and remains visible at the bottom of the initial viewport. Successful US fixture lookup rendered two source records, focused the result heading, and retained the HTTP residual-risk wording. National input without a region focused the origin selector with corrective guidance. The no-match NL fixture rendered `unknown`, zero evidence records, and one explicit evidence gap.

Visual evidence:

- [desktop hero](../web/proof/desktop-hero-1440.jpg)
- [desktop result](../web/proof/desktop-result-1440.jpg)
- [mobile hero](../web/proof/mobile-hero-375.jpg)
- [mobile result](../web/proof/mobile-result-375.jpg)

## Accessibility and state behavior

- The page uses landmarks, a skip link, ordered headings, native labels and controls, a polite live region, and a programmatically focused result heading.
- Every interactive target has a visible focus treatment; the primary mobile target exceeds 44 px.
- Loading copy and the action label stay synchronized. Input, transport, rate-limit, and network errors give a next step.
- Evidence-free and gap-free states use explicit text rather than color or an implied safety verdict.
- Motion is restricted to transform, opacity, and confidence-bar width, and is effectively disabled under `prefers-reduced-motion`.
- Dynamic source content is inserted with DOM nodes and `textContent`; untrusted values are never assigned through `innerHTML`.
- The page uses no analytics, cookies, local storage, third-party fonts, or lookup-history persistence.

## Vercel shape

`vercel.json` defines the static site, same-origin `/v1/lookup` rewrite, response-security headers, and Python function bundle. `api/index.py` exports the WSGI `app` expected by Vercel and only maps the platform path to the canonical HTTP application. The repository-root `pyproject.toml` and `uv.lock` provide the pinned production dependency.

Deploy from the repository root. The function configuration explicitly includes `src/callersignal`; the deployment therefore bundles shared domain code without maintaining a copy or a browser-only truth path. No production secret is required for the read-only pinned-source wedge.

```bash
npx vercel@latest deploy
```

Before treating a deployment as shipped, verify the production homepage, `/v1/lookup` success and validation responses, CSP/security headers, the deployment alias, and the GitHub homepage readback. Do not enable request logging that records raw query strings or add telemetry that contains phone numbers, IP addresses, origin regions, results, or lookup histories.

## Deployment proof and ownership boundary

An anonymous Vercel preview was built and exercised end to end on 27 August 2026. Bundle readback found 11 files from the canonical `src/callersignal` package. The public homepage and JavaScript asset returned `200`; the live lookup returned schema `1.0.0`, two public evidence records for the reserved US fixture, `numbering_context_only`, the shared spoofing warning, and `Cache-Control: no-store`. National-format input without an origin returned `400` with `origin_region_required`. A real-browser lookup on the preview rendered the same two records with zero console errors and zero horizontal overflow.

Anonymous previews expire and cannot be a canonical production URL. A maintainer must authenticate the Vercel CLI, deploy with `--prod`, and read back the owned project and stable alias before describing CallerSignal as persistently hosted. Ephemeral preview and claim URLs are deliberately not committed.
