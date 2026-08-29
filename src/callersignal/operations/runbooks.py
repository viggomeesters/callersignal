"""Ordered operational playbooks that store sanitized evidence handles only."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

RUNBOOKS: dict[str, tuple[str, ...]] = {
    "incident": (
        "contain_access",
        "scope_minimized_data",
        "rotate_affected_secrets",
        "assess_notifications",
        "publish_sanitized_review",
    ),
    "deletion": (
        "authenticate_request",
        "locate_scoped_records",
        "delete_primary_and_outbox",
        "schedule_backup_expiry",
        "issue_minimized_receipt",
    ),
    "correction": (
        "authenticate_request",
        "freeze_affected_publication",
        "correct_source_record",
        "rebuild_derived_state",
        "record_and_notify_correction",
    ),
    "source_takedown": (
        "disable_source",
        "stop_ingestion",
        "identify_affected_evidence_handles",
        "remove_or_recompute_derivatives",
        "confirm_rights_owner_response",
    ),
    "abuse_response": (
        "activate_rate_controls",
        "preserve_minimized_evidence",
        "isolate_affected_workflow",
        "apply_moderation_decision",
        "open_appeal_and_review",
    ),
}

_CASE_ID = re.compile(r"^case_[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_EVIDENCE_REF = re.compile(
    r"^(?:audit|change|receipt|run|ticket)_[a-z0-9]+(?:[_-][a-z0-9]+)*$"
)


class RunbookBoundaryError(ValueError):
    """A case or evidence reference crossed the privacy boundary."""


class RunbookOrderError(RuntimeError):
    """A runbook step was skipped, repeated, or executed out of order."""


@dataclass(frozen=True)
class RunbookCase:
    case_id: str
    kind: str
    status: str
    completed_steps: tuple[str, ...]
    evidence_refs: tuple[str, ...]


class RunbookEngine:
    def start(self, *, kind: str, case_id: str) -> RunbookCase:
        if kind not in RUNBOOKS:
            raise RunbookBoundaryError("unknown runbook kind")
        if _CASE_ID.fullmatch(case_id) is None:
            raise RunbookBoundaryError("case_id must be a sanitized opaque token")
        return RunbookCase(
            case_id=case_id,
            kind=kind,
            status="active",
            completed_steps=(),
            evidence_refs=(),
        )

    def complete_step(
        self,
        *,
        case: RunbookCase,
        step_id: str,
        evidence_ref: str,
    ) -> RunbookCase:
        if case.status != "active":
            raise RunbookOrderError("completed runbook cannot accept another step")
        expected = RUNBOOKS[case.kind][len(case.completed_steps)]
        if step_id != expected:
            raise RunbookOrderError(f"expected {expected}, received {step_id}")
        if _EVIDENCE_REF.fullmatch(evidence_ref) is None:
            raise RunbookBoundaryError("evidence_ref must be a sanitized opaque handle")
        completed = (*case.completed_steps, step_id)
        return replace(
            case,
            status="completed" if len(completed) == len(RUNBOOKS[case.kind]) else "active",
            completed_steps=completed,
            evidence_refs=(*case.evidence_refs, evidence_ref),
        )
