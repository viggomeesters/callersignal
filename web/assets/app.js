const COUNTRY_NAMES = {
  NL: "Netherlands",
  GB: "United Kingdom",
  US: "United States",
};

const RISK_LABELS = {
  official_warning: "Official warning",
  elevated_signals: "Elevated signals",
  no_risk_evidence: "No risk evidence",
  insufficient_evidence: "Insufficient evidence",
};

export function buildLookupURL(number, originRegion) {
  const query = new URLSearchParams({ number });
  if (originRegion) {
    query.set("origin_region", originRegion);
  }
  return `/v1/lookup?${query.toString()}`;
}

export function toViewModel(result) {
  const canonical = result.phone_number.canonical;
  const presentation = result.phone_number.presentation;
  const assessment = result.assessment;
  const risk = assessment.risk;
  const riskState = Object.hasOwn(RISK_LABELS, risk.state)
    ? risk.state
    : "insufficient_evidence";
  return {
    number: {
      country: canonical.region ?? "Unsupported jurisdiction",
      e164: canonical.e164 ?? "Unavailable",
      local: presentation.national ?? "Unavailable",
      international: presentation.international ?? "Unavailable",
      type: humanize(canonical.number_type),
    },
    assessment: {
      state: humanize(assessment.state),
      confidence: humanize(assessment.confidence.level),
      residualRisk: assessment.residual_risk,
    },
    risk: {
      state: riskState,
      stateLabel: RISK_LABELS[riskState],
      headline: risk.headline,
      summary: risk.summary,
      reasonCodes: risk.reason_codes,
      actionCode: risk.recommended_action.code,
      actionMessage: risk.recommended_action.message,
    },
    evidence: result.evidence,
    gaps: result.gaps,
    sources: result.sources_checked,
    generatedAt: result.generated_at,
    lookupId: result.lookup_id,
  };
}

function humanize(value) {
  return String(value ?? "unknown").replaceAll("_", " ");
}

function textElement(tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) {
    element.className = className;
  }
  return element;
}

function formatValue(value) {
  return Array.isArray(value) ? value.map(humanize).join(", ") : humanize(value);
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return "time unavailable";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
}

function safeSourceLink(source) {
  const locator = source.locator ?? source.url;
  if (!locator) {
    return null;
  }
  try {
    const url = new URL(locator);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function renderEvidence(records, container) {
  if (records.length === 0) {
    container.replaceChildren(
      textElement(
        "p",
        "No public source observation matched this number. Unknown stays unknown.",
        "empty-record",
      ),
    );
    return;
  }
  const items = records.map((record) => {
    const article = document.createElement("article");
    article.className = "evidence-record";
    const header = document.createElement("header");
    header.append(textElement("h4", record.source.name));
    const href = safeSourceLink(record.source);
    if (href) {
      const sourceLink = textElement("a", "Open source");
      sourceLink.href = href;
      sourceLink.target = "_blank";
      sourceLink.rel = "noopener noreferrer";
      header.append(sourceLink);
    }
    const value = textElement(
      "p",
      `${humanize(record.observation.claim_type)}: ${formatValue(record.observation.value)}`,
      "record-value",
    );
    const meta = textElement(
      "p",
      `${humanize(record.freshness.status)} · retrieved ${formatDate(record.freshness.retrieved_at)} · confidence ${Math.round(record.observation.confidence * 100)}%`,
      "record-meta",
    );
    article.append(header, value, meta);
    return article;
  });
  container.replaceChildren(...items);
}

function renderGaps(gaps, container) {
  if (gaps.length === 0) {
    container.replaceChildren(
      textElement(
        "p",
        "No source-specific gaps were returned. This is not a safety verdict.",
        "empty-record",
      ),
    );
    return;
  }
  const items = gaps.map((gap) => {
    const article = document.createElement("article");
    article.className = "gap-record";
    article.append(
      textElement("span", humanize(gap.code), "gap-code"),
      textElement("p", gap.message),
    );
    return article;
  });
  container.replaceChildren(...items);
}

function renderSources(sources, container) {
  const items = sources.map((source) => {
    const item = document.createElement("li");
    const sourceCopy = document.createElement("span");
    sourceCopy.append(
      textElement("strong", source.source_id),
      textElement(
        "small",
        source.risk_capable ? "Eligible risk source" : "Numbering context only",
      ),
    );
    item.append(sourceCopy);
    const status = textElement("span", humanize(source.status), "source-status");
    status.dataset.status = source.status;
    item.append(status);
    return item;
  });
  if (items.length === 0) {
    items.push(textElement("li", "No country source is available for this input."));
  }
  container.replaceChildren(...items);
}

function renderResult(result, elements) {
  const view = toViewModel(result);
  const countryName = COUNTRY_NAMES[view.number.country] ?? view.number.country;
  elements.resultCountry.textContent = `${countryName} (${view.number.country})`;
  elements.resultLocal.textContent = view.number.local;
  elements.resultInternational.textContent = view.number.international;
  elements.resultType.textContent = view.number.type;
  elements.resultReference.textContent = `${view.lookupId} · schema ${result.schema_version}`;
  elements.riskBanner.dataset.riskState = view.risk.state;
  elements.riskState.textContent = view.risk.stateLabel;
  elements.riskHeadline.textContent = view.risk.headline;
  elements.riskSummary.textContent = view.risk.summary;
  elements.riskBasis.textContent = view.risk.reasonCodes.map(humanize).join(", ");
  elements.riskAction.textContent = view.risk.actionMessage;
  elements.assessmentState.textContent = `Evidence coverage: ${view.assessment.state}`;
  elements.confidenceValue.textContent = view.assessment.confidence;
  elements.residualRisk.textContent = view.assessment.residualRisk;
  elements.evidenceCount.textContent = `${view.evidence.length} ${view.evidence.length === 1 ? "record" : "records"}`;
  elements.gapCount.textContent = `${view.gaps.length} ${view.gaps.length === 1 ? "gap" : "gaps"}`;
  renderEvidence(view.evidence, elements.evidenceList);
  renderGaps(view.gaps, elements.gapList);
  renderSources(view.sources, elements.sourcesList);
  elements.generatedAt.textContent = `Generated ${formatDate(view.generatedAt)} UTC. Lookups are not stored by default.`;
  elements.result.hidden = false;
  elements.resultTitle.focus({ preventScroll: true });
  elements.result.scrollIntoView({ behavior: "smooth", block: "start" });
}

function init() {
  const elements = {
    form: document.querySelector("#lookup-form"),
    number: document.querySelector("#number"),
    origin: document.querySelector("#origin-region"),
    submit: document.querySelector("#lookup-submit"),
    status: document.querySelector("#lookup-status"),
    result: document.querySelector("#result"),
    resultTitle: document.querySelector("#result-title"),
    resultCountry: document.querySelector("#result-country"),
    resultLocal: document.querySelector("#result-local"),
    resultInternational: document.querySelector("#result-international"),
    resultType: document.querySelector("#result-type"),
    resultReference: document.querySelector("#result-reference"),
    riskBanner: document.querySelector("#risk-banner"),
    riskState: document.querySelector("#risk-state"),
    riskHeadline: document.querySelector("#risk-headline"),
    riskSummary: document.querySelector("#risk-summary"),
    riskBasis: document.querySelector("#risk-basis"),
    riskAction: document.querySelector("#risk-action"),
    assessmentState: document.querySelector("#assessment-state"),
    confidenceValue: document.querySelector("#confidence-value"),
    residualRisk: document.querySelector("#residual-risk"),
    evidenceCount: document.querySelector("#evidence-count"),
    evidenceList: document.querySelector("#evidence-list"),
    gapCount: document.querySelector("#gap-count"),
    gapList: document.querySelector("#gap-list"),
    sourcesList: document.querySelector("#sources-list"),
    generatedAt: document.querySelector("#generated-at"),
  };

  for (const button of document.querySelectorAll(".example-button")) {
    button.addEventListener("click", () => {
      elements.number.value = button.dataset.number;
      elements.origin.value = button.dataset.region;
      elements.number.focus();
    });
  }

  elements.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const number = elements.number.value.trim();
    const origin = elements.origin.value;
    elements.status.dataset.state = "";
    if (!number) {
      elements.status.dataset.state = "error";
      elements.status.textContent = "Enter the displayed phone number to continue.";
      elements.number.focus();
      return;
    }
    if (!number.startsWith("+") && !origin) {
      elements.status.dataset.state = "error";
      elements.status.textContent = "Choose an origin country for a national-format number.";
      elements.origin.focus();
      return;
    }

    elements.submit.disabled = true;
    elements.submit.textContent = "Checking…";
    elements.status.textContent = `Checking public evidence for ${origin || "the international number"}…`;
    try {
      const response = await fetch(buildLookupURL(number, origin), {
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error?.message ?? "The lookup request failed.");
      }
      renderResult(payload, elements);
      elements.status.textContent = "Lookup complete. Evidence and unknowns are shown below.";
    } catch (error) {
      elements.status.dataset.state = "error";
      elements.status.textContent =
        error instanceof Error
          ? `${error.message} Check the number and try again.`
          : "The lookup is unavailable. Try again later.";
    } finally {
      elements.submit.disabled = false;
      elements.submit.textContent = "Check public evidence";
    }
  });
}

if (typeof document !== "undefined") {
  init();
}
