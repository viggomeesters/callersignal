# Operations and Privacy Runbooks

CallerSignal operates on two principles: observe service behavior without observing people, and execute sensitive response work in a fixed order with sanitized evidence handles. The implementation is in [`src/callersignal/operations`](../src/callersignal/operations); deterministic proof is in [`tests/operations`](../tests/operations).

## Health and coverage metrics

`HealthMetrics` exposes only bounded declared dimensions:

- route (`lookup`, `campaigns`, `mcp`, or another explicitly registered route);
- typed outcome and a small HTTP status set;
- fixed latency bucket;
- ISO jurisdiction or `global`;
- registered source identifier and typed coverage-gap code.

Its API has no field for a phone number, request ID, account, IP address, contact, report, prompt, query string, or arbitrary label map. Non-empty metadata is rejected. Dynamic routes and unregistered sources are rejected. The snapshot contains aggregate request totals, latency buckets, source/jurisdiction gap counts, service status, and its privacy posture.

Do not derive “unique numbers,” distinct users, per-number demand, rare-query cohorts, or personal trails from logs outside this API. Lookup popularity remains outside reputation and campaigns. A coverage-gap count means a source or jurisdiction needs operational attention; it says nothing about a number's safety.

## Logging

Allowed structured log fields are deployment revision, coarse route, typed outcome, HTTP status, duration bucket, registered source health, coarse jurisdiction, runtime name, and sanitized runbook evidence handle. Error messages sent to clients remain generic and `no-store`.

Forbidden fields include raw or normalized phone numbers, query strings, request/response bodies, requester identifiers, IP addresses, contact routes, challenge codes, OAuth tokens, reports, narratives, lookup histories, source payloads, prompts, cookies, and credentials. Debug logging does not override this boundary. A sensitive incident uses restricted systems and explicit expiry, never repository commits or public issues.

## Executable runbook contract

`RunbookEngine` starts one of five fixed workflows and accepts exactly the next declared step. Skipping, replaying after completion, using a free-form case identifier, or attaching an email/number/text narrative fails. Each step records only a sanitized handle such as `audit_deletion_primary_removed`; the restricted evidence remains in its approved incident or privacy system.

Run the executable conformance proof with:

```console
uv run pytest tests/operations/test_runbooks.py -q
```

### Incident

1. `contain_access` — disable affected credentials, mutation route, provider integration, or source.
2. `scope_minimized_data` — determine affected data classes, time window, processors, and jurisdictions without exporting full records.
3. `rotate_affected_secrets` — rotate scoped keys and verify old access fails.
4. `assess_notifications` — privacy/security owners record regulator, user, provider, and public-communication decisions.
5. `publish_sanitized_review` — record root cause, prevention, and verified recovery with no private evidence.

The incident commander owns sequencing; security owns containment and rotation; privacy owns notification assessment; the service owner verifies recovery. Public traffic remains read-only or disabled until recovery evidence passes.

### Deletion

1. `authenticate_request` — resolve the request through verified contact, organisation, or receipt proof using an anti-enumerable response.
2. `locate_scoped_records` — resolve pseudonymous aggregate handles and processors; never search a broad exported dataset.
3. `delete_primary_and_outbox` — atomically remove active content, queued delivery, cache/read model, and provider references.
4. `schedule_backup_expiry` — record the provider's bounded backup deletion/expiry evidence.
5. `issue_minimized_receipt` — return action, pseudonymous handle, time, scope, and completion/remaining-backup boundary only.

If authentication fails, stop at step one. If a processor is unavailable, keep the case active, disable affected mutations, and retry; do not issue a completed receipt.

### Correction

1. `authenticate_request`.
2. `freeze_affected_publication` — move the campaign or portfolio to monitoring/suspended before investigation.
3. `correct_source_record` — version the structured source, report, watch, or declaration with a reason.
4. `rebuild_derived_state` — recompute campaigns, risk, catalogue, transparency, and pending notifications from eligible evidence.
5. `record_and_notify_correction` — publish correction state and send only material, consented notifications.

The corrected record never overwrites immutable source evidence. Contradiction fails closed while the case is active.

### Source takedown

1. `disable_source` — set the source registry/runtime control to non-ingestible.
2. `stop_ingestion` — verify fetchers, queues, imports, and retries cannot add records.
3. `identify_affected_evidence_handles` — use provenance handles, not copied payloads.
4. `remove_or_recompute_derivatives` — withdraw ineligible evidence and rebuild risk/campaign outputs.
5. `confirm_rights_owner_response` — record correction/deletion scope, completion, and continuing obligations.

Robots access, source availability, or a prior licence does not delay an emergency disable. Re-enablement requires the full source-rights gate and a new reviewed revision.

### Abuse response

1. `activate_rate_controls` — tighten the affected report, watch, verification, organisation, or MCP boundary.
2. `preserve_minimized_evidence` — retain only bounded abuse reason codes and sanitized provider/audit handles.
3. `isolate_affected_workflow` — stop publication or notification for the targeted aggregate class.
4. `apply_moderation_decision` — reject, suspend, correct, revoke, or restore through the tested domain transition.
5. `open_appeal_and_review` — provide a non-public appeal route and review false-positive impact before closing.

High traffic, repeated reports, or many lookups never become proof of fraud. Abuse controls protect the workflow; they do not create reputation evidence.

## Operational gates and recovery

- Read-only lookup can remain available during mutation-provider failure when evidence freshness is still honest.
- Reports, watches, organisation changes, OAuth mutation tools, and outbound delivery default to disabled until their production provider and owner gates pass.
- Source outage becomes an explicit coverage gap; stale data does not silently become no risk evidence.
- Outbox failure leaves messages pending and aggregates committed only when their own transaction succeeded.
- Deployment rollback must preserve schema compatibility and must not resurrect deleted or expired data.
- Health recovery requires source checks, queue/outbox state, deletion backlog, correction backlog, and public alias probes at the deployed revision.

## Licensed reputation refresh

`activate_reputation_feeds` reads the service index and source registry together at process start. The checked-in state deliberately activates zero reputation feeds. A future production scheduler may pass transient, already-normalized lookup subjects to `ReputationRefreshScheduler`; the scheduler stores only a source-to-last-attempt timestamp and respects the source's reviewed refresh interval. Each adapter separately applies the contractual request window, so a large input batch cannot bypass provider limits.

Before a scheduled run, verify that the provider agreement still covers extraction, caching or transient processing, transformation, and public display; that its credential is present in the deployment secret store; and that privacy, takedown, and provenance owners are available. Never put credentials, raw provider responses, number lists, or scheduler inputs in Git, `.go`, logs, build artifacts, or issue trackers.

An absent credential, disabled index entry, missing registry entry, incomplete gate, invalid configuration, or transport-construction error yields no adapter and therefore no network request. At runtime, rate exhaustion and provider outage yield typed unavailable gaps. Unknown fields are ignored, while an unknown category, native `safe` value, invalid source record, malformed time, oversized body, non-JSON response, or implausible future timestamp fails closed. Re-enable after source takedown only through a newly reviewed registry revision.

## Validation

```console
uv run pytest tests/operations tests/integration/test_reputation_ingest.py -q
make check
```

The tests prove metric cardinality/privacy boundaries and complete every runbook in order. Production case evidence belongs in restricted operational systems and enters repository evidence only as a sanitized non-personal handle.
