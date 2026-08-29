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

const RISK_GLYPHS = {
  official_warning: "!",
  elevated_signals: "△",
  no_risk_evidence: "○",
  insufficient_evidence: "?",
};

export function buildLookupURL(number, originRegion) {
  const query = new URLSearchParams({ number });
  if (originRegion) {
    query.set("origin_region", originRegion);
  }
  return `/v1/lookup?${query.toString()}`;
}

export function buildCampaignURL(campaignId) {
  return campaignId
    ? `/v1/campaigns/${encodeURIComponent(campaignId)}`
    : "/v1/campaigns";
}

export function buildTransparencyURL() {
  return "/v1/coverage";
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
      title: presentation.international ?? canonical.e164 ?? "Interpreted number",
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
    coverage: {
      checked: result.sources_checked.length,
      current: result.sources_checked.filter(
        (source) => !["error", "unavailable"].includes(source.status),
      ).length,
      riskCapable: result.sources_checked.filter((source) => source.risk_capable).length,
      asOf: result.generated_at,
    },
  };
}

export function toCampaignViewModel(record) {
  const campaign = record.campaign;
  const riskState = Object.hasOwn(RISK_LABELS, campaign.risk_state)
    ? campaign.risk_state
    : "insufficient_evidence";
  return {
    id: campaign.campaign_id,
    title: campaign.title,
    status: humanize(campaign.status),
    riskState,
    stateLabel: RISK_LABELS[riskState],
    categories: campaign.categories.map(humanize),
    jurisdictions: campaign.jurisdictions,
    members: campaign.membership,
    timeline: campaign.timeline,
    freshness: campaign.freshness,
    evidence: campaign.evidence,
    confidence: campaign.confidence,
    actions: campaign.recommended_actions.map(humanize),
    correction: campaign.correction,
    limitations: campaign.limitations,
    organization: record.verified_organization
      ? {
          name: record.verified_organization.display_name,
          status: humanize(record.verified_organization.verification_status),
          scope: humanize(record.verified_organization.declaration_scope),
          contactUrl: record.verified_organization.official_contact_url ?? null,
        }
      : null,
    sourceCoverage: record.source_coverage,
  };
}

export function toTransparencyViewModel(snapshot) {
  const corpus = snapshot.corpus;
  const coverage = snapshot.coverage;
  const catalog = coverage.number_catalog;
  const reputation = coverage.reputation_sources;
  const reputationCatalog = coverage.reputation_catalog;
  const correctionCount =
    corpus.corrections.campaigns + corpus.corrections.organization_portfolios;
  return {
    generatedAt: snapshot.generated_at,
    registryReviewedAt: snapshot.registry_reviewed_at,
    methodologyVersion: snapshot.methodology_version,
    noMatchMeaning: snapshot.interpretation.no_matching_evidence,
    metrics: {
      importedRanges: catalog.imported_range_count,
      matchableRanges: catalog.matchable_range_count,
      fccUniqueNumbers: reputationCatalog.unique_number_count,
      fccIndexedObservations: reputationCatalog.indexed_observation_count,
      enabledReputationSources: reputation.enabled_source_count,
    },
    corpusMetrics: {
      jurisdictions: coverage.jurisdictions.filter(
        (item) => item.enabled_sources.length > 0,
      ).length,
      riskSources: coverage.risk_capable_source_count,
      campaigns: corpus.eligible_campaigns,
      portfolios: corpus.verified_organization_portfolios,
    },
    catalog: {
      status: humanize(catalog.status),
      importedRanges: catalog.imported_range_count,
      matchableRanges: catalog.matchable_range_count,
      destinationCategories: catalog.destination_category_count,
      freshness: humanize(catalog.freshness),
      retrievedAt: catalog.retrieved_at,
      newestChange: catalog.source_newest_mutation_at,
      digest: catalog.source_sha256,
      statuses: catalog.register_statuses.map((item) => ({
        label: humanize(item.status),
        nativeLabel: item.source_status,
        count: item.range_count,
      })),
      limitations: catalog.limitations,
    },
    reputation: {
      indexed: reputation.indexed_service_count,
      licensable: reputation.licensable_service_count,
      enabled: reputation.enabled_source_count,
      unavailable: reputation.unavailable_service_count,
      reasons: reputation.unavailable_reasons.map((item) => ({
        label: humanize(item.reason),
        count: item.service_count,
      })),
      services: reputation.services.map((service) => ({
        id: service.service_id,
        name: service.name,
        jurisdictions: service.jurisdictions,
        channel: humanize(service.integration_channel),
        status: humanize(service.status),
        reason: humanize(service.reason),
        blockingGates: service.blocking_gates.map(humanize),
      })),
      notice: reputation.notice,
    },
    reputationCatalog: {
      status: humanize(reputationCatalog.status),
      verificationStatus: humanize(reputationCatalog.verification_status),
      generatedAt: reputationCatalog.generated_at,
      sourceUpdatedAt: reputationCatalog.source_updated_at,
      windowStart: reputationCatalog.window_start,
      windowEnd: reputationCatalog.window_end,
      uniqueNumbers: reputationCatalog.unique_number_count,
      sourceObservations: reputationCatalog.source_observation_count,
      indexedObservations: reputationCatalog.indexed_observation_count,
      rejectedObservations: reputationCatalog.rejected_observation_count,
      freshness: humanize(reputationCatalog.freshness),
      categories: reputationCatalog.category_counts.map((item) => ({
        label: humanize(item.category),
        count: item.observation_count,
      })),
      limitations: reputationCatalog.limitations,
    },
    sources: coverage.sources.map((source) => ({
      id: source.source_id,
      name: source.name,
      jurisdictions: source.jurisdictions,
      scope: source.risk_capable ? "Risk-capable evidence" : "Numbering context only",
      lastIngest: source.last_successful_ingest,
      freshness: humanize(source.freshness),
      gaps: source.gaps.map(humanize),
    })),
    unavailableSources: coverage.unavailable_sources.map((source) => ({
      id: source.source_id,
      jurisdictions: source.jurisdictions,
      gap: humanize(source.gap),
    })),
    moderationThreshold:
      snapshot.moderation.status === "approved" &&
      Number.isInteger(snapshot.moderation.public_aggregate_minimum)
        ? `At least ${formatCount(snapshot.moderation.public_aggregate_minimum)} independently controlled observations`
        : "Not approved; public report aggregation is disabled",
    correctionCount,
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
  if (!value) {
    return "time unavailable";
  }
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

function formatDateOnly(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return "date unavailable";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(date);
}

function formatCount(value) {
  return new Intl.NumberFormat().format(value);
}

function riskStateMark(state, label) {
  const wrapper = document.createElement("span");
  wrapper.className = "campaign-state";
  wrapper.dataset.riskState = state;
  const glyph = textElement("span", RISK_GLYPHS[state] ?? "?", "campaign-state-glyph");
  glyph.setAttribute("aria-hidden", "true");
  wrapper.append(glyph, textElement("span", label));
  return wrapper;
}

function campaignSummaryView(summary) {
  const riskState = Object.hasOwn(RISK_LABELS, summary.risk_state)
    ? summary.risk_state
    : "insufficient_evidence";
  return {
    id: summary.campaign_id,
    title: summary.title,
    status: humanize(summary.status),
    riskState,
    stateLabel: RISK_LABELS[riskState],
    categories: summary.categories.map(humanize),
    jurisdictions: summary.jurisdictions,
    members: summary.membership,
    timeline: summary.timeline,
    freshness: summary.freshness,
    correction: summary.correction,
    sourceDiversity: summary.source_diversity,
    organization: summary.verified_organization,
  };
}

function campaignCard(summary) {
  const view = campaignSummaryView(summary);
  const article = document.createElement("article");
  article.className = "campaign-card";
  article.dataset.riskState = view.riskState;

  const header = document.createElement("header");
  header.append(riskStateMark(view.riskState, view.stateLabel));
  const title = textElement("h3", view.title);
  const link = document.createElement("a");
  link.href = `/campaigns/${encodeURIComponent(view.id)}`;
  link.textContent = "Open campaign record";
  title.append(" ", link);
  header.append(title);

  const dates = textElement(
    "p",
    `${view.status} · first seen ${formatDateOnly(view.timeline.first_seen)} · last seen ${formatDateOnly(view.timeline.last_seen)}`,
    "campaign-card-dates",
  );
  const basis = textElement(
    "p",
    `${formatCount(view.sourceDiversity)} independent ${view.sourceDiversity === 1 ? "source" : "sources"} · ${view.categories.join(", ")} · freshness ${humanize(view.freshness.status)}`,
    "campaign-card-basis",
  );
  article.append(header, dates, basis);
  if (view.organization?.verification_status === "verified") {
    article.append(
      textElement(
        "p",
        `Verified declaration context: ${view.organization.display_name}. This does not prove call origin.`,
        "organization-note",
      ),
    );
  }
  return article;
}

function renderCampaignCatalogue(campaigns, elements) {
  elements.campaignList.replaceChildren(...campaigns.map(campaignCard));
  if (campaigns.length === 0) {
    elements.campaignList.replaceChildren(
      textElement(
        "p",
        "No campaign currently meets the public evidence and rights threshold. This does not mean unknown calls are safe.",
        "campaign-empty",
      ),
    );
    elements.campaignCatalogueStatus.textContent = "No publishable campaigns in the current public corpus.";
    return;
  }
  elements.campaignCatalogueStatus.textContent = `${formatCount(campaigns.length)} public ${campaigns.length === 1 ? "campaign meets" : "campaigns meet"} the publication threshold.`;
}

function renderCampaignHistory(e164, campaigns, elements) {
  const matches = campaigns.filter((summary) =>
    summary.membership.some(
      (member) => member.kind === "displayed_number" && member.value === e164,
    ),
  );
  elements.campaignHistoryCount.textContent = `${formatCount(matches.length)} ${matches.length === 1 ? "campaign" : "campaigns"}`;
  if (matches.length === 0) {
    elements.campaignHistoryList.replaceChildren(
      textElement(
        "p",
        "No eligible public campaign currently matches this displayed value. That is a coverage result, not a safety verdict.",
        "campaign-empty",
      ),
    );
    return;
  }
  elements.campaignHistoryList.replaceChildren(...matches.map(campaignCard));
}

function detailSection(title, values, className = "campaign-detail-section") {
  const section = document.createElement("section");
  section.className = className;
  section.append(textElement("h4", title));
  const list = document.createElement("ul");
  list.replaceChildren(...values.map((value) => textElement("li", value)));
  section.append(list);
  return section;
}

function renderCampaignDetail(record, elements) {
  const view = toCampaignViewModel(record);
  elements.campaignDetail.dataset.riskState = view.riskState;
  elements.campaignDetailState.textContent = view.stateLabel;
  elements.campaignDetailTitle.textContent = view.title;
  elements.campaignDetailSummary.textContent = `${view.status}. First observed ${formatDateOnly(view.timeline.first_seen)}, last observed ${formatDateOnly(view.timeline.last_seen)}. This describes displayed values, not a caller identity.`;

  const facts = document.createElement("dl");
  facts.className = "campaign-facts";
  const factValues = [
    ["Freshness", `${humanize(view.freshness.status)}, as of ${formatDate(view.freshness.as_of)} UTC`],
    ["Evidence", `${formatCount(view.evidence.source_diversity)} independent sources, confidence ${humanize(view.confidence.level)}`],
    ["Correction", `${humanize(view.correction.status)}${view.correction.updated_at ? `, updated ${formatDate(view.correction.updated_at)} UTC` : ""}`],
    ["Jurisdiction", view.jurisdictions.join(", ")],
  ];
  for (const [term, value] of factValues) {
    const row = document.createElement("div");
    row.append(textElement("dt", term), textElement("dd", value));
    facts.append(row);
  }

  const coverage = detailSection(
    "Exact source coverage",
    view.sourceCoverage.map(
      (source) => `${source.source_id}: ${humanize(source.status)}, checked ${formatDate(source.checked_at)} UTC`,
    ),
  );
  const members = detailSection(
    "Displayed-value membership",
    view.members.map((member) =>
      member.kind === "bounded_pattern"
        ? `${member.value} followed by exactly ${formatCount(member.following_digits)} digits`
        : `${member.value}, exact displayed value`,
    ),
  );
  const actions = detailSection(
    "Recommended actions",
    view.actions.map((action) => `${action}.`),
  );
  const limitations = detailSection("Limits", view.limitations);
  const sections = [facts];
  if (view.organization) {
    const organizationCopy = [
      `${view.organization.name}: ${view.organization.status} declaration, scope ${view.organization.scope}.`,
      "A verified declaration is not proof that an individual call originated from this organisation.",
    ];
    sections.push(detailSection("Verified organisation context", organizationCopy));
  }
  sections.push(coverage, members, actions, limitations);
  elements.campaignDetailBody.replaceChildren(...sections);
  elements.campaignList.hidden = true;
  elements.campaignCatalogueStatus.hidden = true;
  elements.campaignDetail.hidden = false;
  elements.campaigns.scrollIntoView({ block: "start" });
  elements.campaignDetailTitle.focus({ preventScroll: true });
}

function campaignIdFromLocation() {
  if (typeof window === "undefined") {
    return null;
  }
  const match = window.location.pathname.match(/^\/campaigns\/([^/]+)$/);
  if (!match) {
    return null;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

async function loadCampaignCatalogue(elements) {
  try {
    const response = await fetch(buildCampaignURL(), {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message ?? "The campaign index is unavailable.");
    }
    const campaigns = Array.isArray(payload.campaigns) ? payload.campaigns : [];
    renderCampaignCatalogue(campaigns, elements);
    const campaignId = campaignIdFromLocation();
    if (campaignId) {
      const detailResponse = await fetch(buildCampaignURL(campaignId), {
        headers: { Accept: "application/json" },
      });
      const detail = await detailResponse.json();
      if (!detailResponse.ok) {
        throw new Error(detail.error?.message ?? "The campaign record is unavailable.");
      }
      renderCampaignDetail(detail, elements);
    }
    return campaigns;
  } catch (error) {
    elements.campaignCatalogueStatus.dataset.state = "error";
    elements.campaignCatalogueStatus.textContent =
      error instanceof Error
        ? `${error.message} Try again later.`
        : "The campaign index is unavailable. Try again later.";
    return [];
  }
}

function renderTransparency(snapshot, elements) {
  const view = toTransparencyViewModel(snapshot);
  elements.metricAcmRanges.textContent = formatCount(view.metrics.importedRanges);
  elements.metricFccNumbers.textContent = formatCount(view.metrics.fccUniqueNumbers);
  elements.metricFccObservations.textContent = formatCount(
    view.metrics.fccIndexedObservations,
  );
  elements.metricEnabledReputation.textContent = formatCount(
    view.metrics.enabledReputationSources,
  );
  elements.metricJurisdictions.textContent = formatCount(
    view.corpusMetrics.jurisdictions,
  );
  elements.metricRiskSources.textContent = formatCount(view.corpusMetrics.riskSources);
  elements.metricCampaigns.textContent = formatCount(view.corpusMetrics.campaigns);
  elements.metricPortfolios.textContent = formatCount(view.corpusMetrics.portfolios);
  elements.coverageNoMatch.textContent = view.noMatchMeaning;
  elements.catalogLead.textContent = `${formatCount(view.catalog.importedRanges)} imported ranges, ${formatCount(view.catalog.matchableRanges)} available for canonical lookups.`;
  elements.catalogFreshness.textContent = `${view.catalog.freshness}, retrieved ${formatDate(view.catalog.retrievedAt)} UTC`;
  elements.catalogDestinations.textContent = formatCount(
    view.catalog.destinationCategories,
  );
  elements.catalogNewestChange.textContent = `${formatDate(view.catalog.newestChange)} UTC`;
  elements.catalogDigest.textContent = view.catalog.digest;
  elements.catalogStatusList.replaceChildren(
    ...view.catalog.statuses.map((status) => {
      const item = document.createElement("li");
      item.append(
        textElement("strong", formatCount(status.count)),
        textElement("span", `${status.label} · ACM: ${status.nativeLabel}`),
      );
      return item;
    }),
  );
  elements.fccCatalogLead.textContent = `${formatCount(view.reputationCatalog.indexedObservations)} observations across ${formatCount(view.reputationCatalog.uniqueNumbers)} keyed displayed numbers; ${formatCount(view.reputationCatalog.rejectedObservations)} source observations were excluded by the number boundary.`;
  elements.fccCatalogWindow.textContent = `${view.reputationCatalog.windowStart} through ${view.reputationCatalog.windowEnd}`;
  elements.fccCatalogGenerated.textContent = `${formatDate(view.reputationCatalog.generatedAt)} UTC`;
  elements.fccCatalogSourceUpdated.textContent = `${formatDate(view.reputationCatalog.sourceUpdatedAt)} UTC`;
  elements.fccCatalogFreshness.textContent = view.reputationCatalog.freshness;
  elements.fccCategoryList.replaceChildren(
    ...view.reputationCatalog.categories.map((category) => {
      const item = document.createElement("li");
      item.append(
        textElement("strong", formatCount(category.count)),
        textElement("span", category.label),
      );
      return item;
    }),
  );
  elements.fccCatalogBoundary.textContent = view.reputationCatalog.limitations.join(" ");
  elements.reputationLead.textContent = `${formatCount(view.reputation.indexed)} services indexed, ${formatCount(view.reputation.licensable)} advertise a licensing route, ${formatCount(view.reputation.enabled)} are enabled.`;
  elements.reputationReasonList.replaceChildren(
    ...view.reputation.reasons.map((reason) => {
      const item = document.createElement("li");
      item.append(
        textElement("strong", formatCount(reason.count)),
        textElement("span", reason.label),
      );
      return item;
    }),
  );
  elements.reputationSourceSummary.textContent = `Inspect ${formatCount(view.reputation.services.length)} source decisions`;
  elements.reputationServiceList.replaceChildren(
    ...view.reputation.services.map((service) => {
      const item = document.createElement("li");
      const jurisdictions =
        service.jurisdictions.length > 0 ? service.jurisdictions.join(", ") : "International";
      const blockers =
        service.blockingGates.length > 0
          ? ` Blocked by ${service.blockingGates.join(", ")}.`
          : "";
      item.append(
        textElement("strong", service.name),
        textElement(
          "span",
          `${jurisdictions} · ${service.channel} · ${service.reason}.${blockers}`,
        ),
      );
      return item;
    }),
  );
  elements.reputationNotice.textContent = view.reputation.notice;
  elements.sourceCoverageCount.textContent = `${formatCount(view.sources.length)} enabled ${view.sources.length === 1 ? "source" : "sources"}`;

  const sourceRows = view.sources.map((source) => {
    const article = document.createElement("article");
    article.className = "source-coverage-row";
    const header = document.createElement("header");
    header.append(
      textElement("strong", source.name),
      textElement("span", source.scope, "source-scope"),
    );
    const facts = textElement(
      "p",
      `${source.jurisdictions.join(", ")} · last successful ingest ${formatDate(source.lastIngest)} UTC · freshness ${source.freshness}`,
      "source-coverage-facts",
    );
    article.append(header, facts);
    if (source.gaps.length > 0) {
      article.append(textElement("p", `Gaps: ${source.gaps.join(", ")}.`, "source-gap"));
    }
    return article;
  });
  elements.sourceCoverageList.replaceChildren(...sourceRows);
  elements.moderationThreshold.textContent = view.moderationThreshold;
  elements.correctionCount.textContent = formatCount(view.correctionCount);
  elements.methodologyVersion.textContent = `v${view.methodologyVersion}`;
  elements.transparencyStatus.textContent = `Coverage generated ${formatDate(view.generatedAt)} UTC · source registry reviewed ${formatDateOnly(view.registryReviewedAt)}.`;
}

async function loadTransparency(elements) {
  try {
    const response = await fetch(buildTransparencyURL(), {
      headers: { Accept: "application/json" },
    });
    const snapshot = await response.json();
    if (!response.ok) {
      throw new Error("Public corpus coverage is unavailable.");
    }
    renderTransparency(snapshot, elements);
  } catch (error) {
    elements.transparencyStatus.dataset.state = "error";
    elements.transparencyStatus.textContent =
      error instanceof Error
        ? `${error.message} Read the repository transparency document for the last committed snapshot.`
        : "Public corpus coverage is unavailable. Read the repository transparency document.";
  }
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
  elements.resultTitle.textContent = view.number.title;
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
  elements.coverageChecked.textContent = formatCount(view.coverage.checked);
  elements.coverageCurrent.textContent = formatCount(view.coverage.current);
  elements.coverageRiskCapable.textContent = formatCount(view.coverage.riskCapable);
  elements.coverageAsOf.textContent = `${formatDate(view.coverage.asOf)} UTC`;
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
    coverageChecked: document.querySelector("#coverage-checked"),
    coverageCurrent: document.querySelector("#coverage-current"),
    coverageRiskCapable: document.querySelector("#coverage-risk-capable"),
    coverageAsOf: document.querySelector("#coverage-as-of"),
    campaignHistoryCount: document.querySelector("#campaign-history-count"),
    campaignHistoryList: document.querySelector("#campaign-history-list"),
    campaigns: document.querySelector("#campaigns"),
    campaignCatalogueStatus: document.querySelector("#campaign-catalogue-status"),
    campaignList: document.querySelector("#campaign-list"),
    campaignDetail: document.querySelector("#campaign-detail"),
    campaignDetailState: document.querySelector("#campaign-detail-state"),
    campaignDetailTitle: document.querySelector("#campaign-detail-title"),
    campaignDetailSummary: document.querySelector("#campaign-detail-summary"),
    campaignDetailBody: document.querySelector("#campaign-detail-body"),
    transparencyStatus: document.querySelector("#transparency-status"),
    coverageNoMatch: document.querySelector("#coverage-no-match"),
    metricAcmRanges: document.querySelector("#metric-acm-ranges"),
    metricFccNumbers: document.querySelector("#metric-fcc-numbers"),
    metricFccObservations: document.querySelector("#metric-fcc-observations"),
    metricEnabledReputation: document.querySelector("#metric-enabled-reputation"),
    metricJurisdictions: document.querySelector("#metric-jurisdictions"),
    metricRiskSources: document.querySelector("#metric-risk-sources"),
    metricCampaigns: document.querySelector("#metric-campaigns"),
    metricPortfolios: document.querySelector("#metric-portfolios"),
    catalogLead: document.querySelector("#catalog-lead"),
    catalogFreshness: document.querySelector("#catalog-freshness"),
    catalogDestinations: document.querySelector("#catalog-destinations"),
    catalogNewestChange: document.querySelector("#catalog-newest-change"),
    catalogDigest: document.querySelector("#catalog-digest"),
    catalogStatusList: document.querySelector("#catalog-status-list"),
    fccCatalogLead: document.querySelector("#fcc-catalog-lead"),
    fccCatalogWindow: document.querySelector("#fcc-catalog-window"),
    fccCatalogGenerated: document.querySelector("#fcc-catalog-generated"),
    fccCatalogSourceUpdated: document.querySelector("#fcc-catalog-source-updated"),
    fccCatalogFreshness: document.querySelector("#fcc-catalog-freshness"),
    fccCategoryList: document.querySelector("#fcc-category-list"),
    fccCatalogBoundary: document.querySelector("#fcc-catalog-boundary"),
    reputationLead: document.querySelector("#reputation-lead"),
    reputationReasonList: document.querySelector("#reputation-reason-list"),
    reputationSourceSummary: document.querySelector("#reputation-source-summary"),
    reputationServiceList: document.querySelector("#reputation-service-list"),
    reputationNotice: document.querySelector("#reputation-notice"),
    sourceCoverageCount: document.querySelector("#source-coverage-count"),
    sourceCoverageList: document.querySelector("#source-coverage-list"),
    moderationThreshold: document.querySelector("#moderation-threshold"),
    correctionCount: document.querySelector("#correction-count"),
    methodologyVersion: document.querySelector("#methodology-version"),
  };

  const campaignsPromise = loadCampaignCatalogue(elements);
  loadTransparency(elements);

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
      const campaigns = await campaignsPromise;
      renderCampaignHistory(payload.phone_number.canonical.e164, campaigns, elements);
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
