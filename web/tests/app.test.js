import assert from "node:assert/strict";
import test from "node:test";

import { buildLookupURL, toViewModel } from "../assets/app.js";

const RESULT = {
  schema_version: "1.0.0",
  kind: "lookup_result",
  lookup_id: "lkp_web-test",
  generated_at: "2026-08-27T09:00:00Z",
  phone_number: {
    origin_region: "US",
    canonical: {
      e164: "+12025550147",
      region: "US",
      number_type: "fixed_or_mobile",
    },
    presentation: {
      national: "(202) 555-0147",
      international: "+1 202-555-0147",
    },
  },
  sources_checked: [
    {
      source_id: "nanpa_public_numbering",
      status: "matched",
      risk_capable: false,
      checked_at: "2026-08-27T09:00:00Z",
    },
  ],
  evidence: [
    {
      evidence_id: "ev_web-example",
      source: {
        name: "North American Numbering Plan Administrator",
        url: "https://www.nationalnanpa.com/",
      },
      observation: {
        claim_type: "reserved_status",
        value: "fictional_use",
        confidence: 0.99,
      },
      freshness: { status: "current", retrieved_at: "2026-08-27T09:00:00Z" },
    },
  ],
  gaps: [],
  assessment: {
    state: "numbering_context_only",
    confidence: { level: "high", score: 0.99 },
    conclusions: [],
    residual_risk:
      "Caller ID spoofing remains possible; numbering evidence does not prove caller identity.",
    risk: {
      state: "insufficient_evidence",
      headline: "Not enough risk evidence",
      summary:
        "Numbering context does not show whether calls displaying this number are harmful.",
      reason_codes: ["no_risk_capable_source_checked"],
      evidence_ids: [],
      source_ids: [],
      recommended_action: {
        code: "treat_as_unknown",
        message:
          "Treat this result as unknown and verify unexpected requests through a trusted channel.",
      },
    },
  },
};

test("buildLookupURL preserves explicit national origin semantics", () => {
  assert.equal(
    buildLookupURL("202-555-0147", "US"),
    "/v1/lookup?number=202-555-0147&origin_region=US",
  );
  assert.equal(
    buildLookupURL("+1 202-555-0147", ""),
    "/v1/lookup?number=%2B1+202-555-0147",
  );
});

test("view model only organizes canonical HTTP result fields", () => {
  const view = toViewModel(RESULT);

  assert.deepEqual(view.number, {
    country: "US",
    e164: "+12025550147",
    local: "(202) 555-0147",
    international: "+1 202-555-0147",
    type: "fixed or mobile",
  });
  assert.deepEqual(view.assessment, {
    state: "numbering context only",
    confidence: "high",
    residualRisk: RESULT.assessment.residual_risk,
  });
  assert.deepEqual(view.risk, {
    state: "insufficient_evidence",
    stateLabel: "Insufficient evidence",
    headline: "Not enough risk evidence",
    summary: RESULT.assessment.risk.summary,
    reasonCodes: ["no_risk_capable_source_checked"],
    actionCode: "treat_as_unknown",
    actionMessage: RESULT.assessment.risk.recommended_action.message,
  });
  assert.equal(view.evidence, RESULT.evidence);
  assert.equal(view.gaps, RESULT.gaps);
  assert.equal(view.sources, RESULT.sources_checked);
  assert.equal(view.generatedAt, RESULT.generated_at);
  assert.equal(view.lookupId, RESULT.lookup_id);
});

test("view model preserves unknown and no-evidence states", () => {
  const unknown = structuredClone(RESULT);
  unknown.evidence = [];
  unknown.gaps = [
    {
      gap_id: "gap_web-example",
      source_id: "nanpa_public_numbering",
      code: "no_authoritative_data",
      message: "The public source returned no authoritative number-level evidence.",
      retryable: false,
    },
  ];
  unknown.assessment.state = "unknown";
  unknown.assessment.confidence = { level: "none", score: 0 };

  const view = toViewModel(unknown);

  assert.deepEqual(view.evidence, []);
  assert.equal(view.gaps[0].code, "no_authoritative_data");
  assert.equal(view.assessment.state, "unknown");
  assert.equal(view.assessment.confidence, "none");
});

test("all four canonical risk states preserve distinct state labels", () => {
  const states = {
    official_warning: "Official warning",
    elevated_signals: "Elevated signals",
    no_risk_evidence: "No risk evidence",
    insufficient_evidence: "Insufficient evidence",
  };

  for (const [state, label] of Object.entries(states)) {
    const fixture = structuredClone(RESULT);
    fixture.assessment.risk.state = state;
    const view = toViewModel(fixture);

    assert.equal(view.risk.stateLabel, label);
  }
});

test("an unexpected risk state fails closed to insufficient evidence styling", () => {
  const fixture = structuredClone(RESULT);
  fixture.assessment.risk.state = "unexpected_state";

  const view = toViewModel(fixture);

  assert.equal(view.risk.state, "insufficient_evidence");
  assert.equal(view.risk.stateLabel, "Insufficient evidence");
});
