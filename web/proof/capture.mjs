import { writeFileSync } from "node:fs";
import { chromium } from "playwright";

const baseUrl = process.env.CALLERSIGNAL_PROOF_URL ?? "http://127.0.0.1:8765";
const output = new URL("./", import.meta.url);
const reservedNumber = "+1" + " 202-555-0147";
const e164 = "+1" + "202" + "555" + "0147";
const now = "2026-08-29T06:20:00Z";

function source(sourceId, riskCapable = true) {
  return {
    source_id: sourceId,
    status: "matched",
    risk_capable: riskCapable,
    checked_at: now,
  };
}

function lookupFixture(state) {
  const elevated = state === "elevated_signals";
  const official = state === "official_warning";
  const sources = official
    ? [source("reserved_fixture_regulator")]
    : elevated
      ? [source("reserved_fixture_alpha"), source("reserved_fixture_beta")]
      : [source("nanpa_public_numbering", false)];
  const messages = {
    insufficient_evidence: {
      headline: "Not enough risk evidence",
      summary: "Numbering context does not show whether calls displaying this number are harmful.",
      action: "Treat this result as unknown and verify unexpected requests through a trusted channel.",
      reasons: ["no_risk_capable_source_checked"],
    },
    elevated_signals: {
      headline: "Multiple test sources share a warning pattern",
      summary: "Two independent, reserved browser-test sources describe the same impersonation pattern.",
      action: "Avoid sensitive actions and verify the request through a contact route you already trust.",
      reasons: ["shared_impersonation_pattern"],
    },
    official_warning: {
      headline: "Official warning in a reserved test fixture",
      summary: "A synthetic regulator fixture marks this protected example for browser verification only.",
      action: "Do not engage through the call. Verify independently and follow regulator guidance.",
      reasons: ["official_scam_warning"],
    },
  };
  const message = messages[state];
  return {
    schema_version: "1.0.0",
    kind: "lookup_result",
    lookup_id: `lkp_browser_${state}`,
    generated_at: now,
    phone_number: {
      origin_region: "US",
      canonical: { e164, region: "US", number_type: "fixed_or_mobile" },
      presentation: { national: "(202) 555-0147", international: reservedNumber },
    },
    sources_checked: sources,
    evidence: sources.map((item, index) => ({
      evidence_id: `ev_browser_${state}_${index}`,
      source: { name: item.source_id, url: "https://example.com/fixture" },
      observation: {
        claim_type: official || elevated ? "reported_pattern" : "reserved_status",
        value: official || elevated ? message.reasons : "fictional_use",
        confidence: official ? 0.95 : elevated ? 0.82 : 0.99,
      },
      freshness: { status: "current", retrieved_at: now },
    })),
    gaps: [],
    assessment: {
      state: official || elevated ? "risk_evidence_available" : "numbering_context_only",
      confidence: { level: official ? "high" : elevated ? "medium" : "high", score: 0.8 },
      conclusions: [],
      residual_risk: "Caller ID can be spoofed; displayed-number evidence does not prove caller identity.",
      risk: {
        state,
        headline: message.headline,
        summary: message.summary,
        reason_codes: message.reasons,
        evidence_ids: [],
        source_ids: sources.map((item) => item.source_id),
        recommended_action: { code: "verify_independently", message: message.action },
      },
    },
  };
}

function campaignRecord(riskState = "elevated_signals") {
  const sourceIds =
    riskState === "official_warning"
      ? ["reserved_fixture_regulator"]
      : ["reserved_fixture_alpha", "reserved_fixture_beta"];
  const campaign = {
    schema_version: "1.0.0",
    kind: "caller_campaign",
    campaign_id: "cmp_reserved_demo",
    title:
      riskState === "official_warning"
        ? "Reserved fixture with an official-warning state"
        : "Reserved fixture impersonation pattern",
    status: "active",
    risk_state: riskState,
    subject_semantics: "calls_displaying_numbers_or_patterns",
    categories: ["impersonation_attempt"],
    jurisdictions: ["US"],
    membership: [
      {
        kind: "displayed_number",
        value: e164,
        subject_semantics: "call_displayed_value",
        identity_scope: "no_caller_or_subscriber_identity_claim",
      },
    ],
    timeline: {
      first_seen: "2026-08-20T08:00:00Z",
      last_seen: "2026-08-28T08:00:00Z",
      published_at: "2026-08-28T09:00:00Z",
      updated_at: now,
    },
    evidence: {
      eligible_evidence_ids: sourceIds.map((_, index) => `ev_reserved_${index}`),
      source_ids: sourceIds,
      source_diversity: sourceIds.length,
      reason_codes: [
        riskState === "official_warning" ? "official_scam_warning" : "shared_impersonation_pattern",
      ],
      excluded_reason_codes: [],
    },
    confidence: { level: riskState === "official_warning" ? "high" : "medium", score: 0.86 },
    freshness: { as_of: now, status: "current" },
    recommended_actions: ["avoid_sensitive_actions", "verify_through_trusted_channel"],
    correction: { status: "none", updated_at: null, reason_codes: [] },
    limitations: [
      "Caller ID can be spoofed; this record describes displayed values, not caller identity.",
      "This synthetic campaign exists only to verify the public interface with a reserved number.",
    ],
  };
  return {
    schema_version: "1.0.0",
    kind: "public_campaign",
    campaign,
    verified_organization: {
      display_name: "Reserved Fixture Organisation",
      verification_status: "verified",
      declaration_scope: "official_contact_route_only",
    },
    source_coverage: sourceIds.map((sourceId) => ({
      source_id: sourceId,
      status: "matched",
      checked_at: now,
      jurisdiction: "US",
      scope: "reserved_browser_fixture",
    })),
  };
}

function campaignSummary(record) {
  const campaign = record.campaign;
  return {
    campaign_id: campaign.campaign_id,
    title: campaign.title,
    status: campaign.status,
    risk_state: campaign.risk_state,
    categories: campaign.categories,
    jurisdictions: campaign.jurisdictions,
    membership: campaign.membership,
    timeline: campaign.timeline,
    freshness: campaign.freshness,
    correction: campaign.correction,
    source_diversity: campaign.evidence.source_diversity,
    verified_organization: record.verified_organization,
  };
}

async function capture(browser, viewport, scenario) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      consoleErrors.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));

  const record = campaignRecord(
    scenario.state === "official_warning" ? "official_warning" : "elevated_signals",
  );
  await page.route("**/v1/campaigns", async (route) => {
    const campaigns = scenario.withCampaign ? [campaignSummary(record)] : [];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schema_version: "1.0.0",
        kind: "public_campaign_catalogue",
        as_of: campaigns.length ? now : null,
        campaigns,
        notice: "Reserved browser-proof corpus.",
      }),
    });
  });
  await page.route("**/v1/campaigns/cmp_reserved_demo", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(record) });
  });
  if (scenario.state) {
    await page.route("**/v1/lookup?**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(lookupFixture(scenario.state)),
      });
    });
  }

  const path = scenario.detail ? "/campaigns/cmp_reserved_demo" : "/";
  await page.goto(`${baseUrl}${path}`, { waitUntil: "networkidle" });
  if (scenario.state && !scenario.detail) {
    await page.locator("#number").fill("202-555-0147");
    await page.locator("#origin-region").selectOption("US");
    await page.locator("#lookup-submit").click();
    await page.locator("#result").waitFor({ state: "visible" });
    await page.locator("#result").evaluate((element) => {
      element.scrollIntoView({ behavior: "instant", block: "start" });
    });
    await page.waitForTimeout(400);
  }
  if (scenario.detail) {
    await page.locator("#campaign-detail").waitFor({ state: "visible" });
    await page.waitForTimeout(400);
  }
  if (scenario.coverage) {
    await page.waitForFunction(
      () => document.querySelector("#metric-jurisdictions")?.textContent.trim() === "3",
    );
    await page.locator("#coverage").evaluate((element) => {
      element.scrollIntoView({ behavior: "instant", block: "start" });
    });
    await page.waitForTimeout(400);
  }
  if (!scenario.state && !scenario.detail && !scenario.coverage) {
    await page.locator(".demo-row").scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);
  }

  const facts = await page.evaluate(({ state, detail, coverage }) => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    };
    const clipped = [...document.querySelectorAll("button, a, summary, h1, h2, h3, p, dd")]
      .filter(visible)
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.left < -1 || rect.right > window.innerWidth + 1;
      })
      .map((element) => element.id || element.textContent.trim().slice(0, 60));
    return {
      viewport: { width: window.innerWidth, height: window.innerHeight },
      horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      clipped,
      riskState: state,
      riskHeadline: state ? document.querySelector("#risk-headline")?.textContent : null,
      visibleRiskIcons: state
        ? [...document.querySelectorAll(".risk-icon")].filter(visible).length
        : 0,
      resultTitleMatchesReservedFixture: state
        ? document.querySelector("#result-title")?.textContent === "+1" + " 202-555-0147"
        : null,
      focusedElement: document.activeElement?.id || document.activeElement?.tagName,
      detailTitle: detail ? document.querySelector("#campaign-detail-title")?.textContent : null,
      coverageMetrics: coverage
        ? [
            "#metric-jurisdictions",
            "#metric-risk-sources",
            "#metric-campaigns",
            "#metric-portfolios",
          ].map((selector) => document.querySelector(selector)?.textContent)
        : null,
      exampleButtons: [...document.querySelectorAll(".example-button")].map((button) => ({
        label: button.textContent.trim(),
        number: button.dataset.number,
        region: button.dataset.region,
      })),
      temporaryCopy: /\b(?:todo|lorem ipsum|placeholder)\b/i.test(document.body.textContent),
    };
  }, { state: scenario.state, detail: scenario.detail, coverage: scenario.coverage });
  facts.consoleErrors = consoleErrors;
  if (
    facts.horizontalOverflow !== 0 ||
    facts.clipped.length > 0 ||
    facts.consoleErrors.length > 0 ||
    facts.temporaryCopy ||
    (scenario.state && facts.visibleRiskIcons !== 1) ||
    (scenario.state && !facts.resultTitleMatchesReservedFixture) ||
    facts.exampleButtons.length !== 3 ||
    !facts.exampleButtons.some(
      (button) =>
        button.label === "NL ACM-blocked number" &&
        button.number === "0906-8844" &&
        button.region === "NL",
    ) ||
    (scenario.coverage && JSON.stringify(facts.coverageMetrics) !== JSON.stringify(["3", "0", "0", "0"]))
  ) {
    throw new Error(`${scenario.name} failed visual facts: ${JSON.stringify(facts)}`);
  }
  await page.screenshot({
    path: new URL(`./${scenario.filename}`, output).pathname,
    type: "jpeg",
    quality: 88,
    fullPage: false,
  });
  await context.close();
  return { scenario: scenario.name, ...facts };
}

const browser = await chromium.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
});
const scenarios = [
  { name: "empty", filename: "hero", state: null, withCampaign: false },
  { name: "coverage", filename: "coverage", state: null, withCampaign: false, coverage: true },
  { name: "unknown", filename: "unknown", state: "insufficient_evidence", withCampaign: false },
  { name: "elevated", filename: "elevated", state: "elevated_signals", withCampaign: true },
  { name: "official-warning", filename: "official-warning", state: "official_warning", withCampaign: true },
  { name: "campaign-detail", filename: "campaign-detail", state: null, withCampaign: true, detail: true },
];
const results = [];
for (const viewport of [
  { label: "desktop-1440", width: 1440, height: 1000 },
  { label: "mobile-375", width: 375, height: 812 },
]) {
  for (const scenario of scenarios) {
    results.push(
      await capture(browser, viewport, {
        ...scenario,
        filename: `${viewport.label}-${scenario.filename}.jpg`,
      }),
    );
  }
}
await browser.close();
writeFileSync(
  new URL("./browser-proof.json", output),
  `${JSON.stringify({ captured_at: new Date().toISOString(), fixture_as_of: now, fixture_policy: "reserved synthetic browser proof only", results }, null, 2)}\n`,
);
