from __future__ import annotations

import pytest

from callersignal.operations import (
    RUNBOOKS,
    RunbookBoundaryError,
    RunbookEngine,
    RunbookOrderError,
)


@pytest.mark.parametrize("kind", sorted(RUNBOOKS))
def test_every_operational_runbook_executes_in_declared_order(kind: str) -> None:
    engine = RunbookEngine()
    case = engine.start(kind=kind, case_id=f"case_{kind}_example")

    for step in RUNBOOKS[kind]:
        case = engine.complete_step(
            case=case,
            step_id=step,
            evidence_ref=f"audit_{kind}_{step}",
        )

    assert case.status == "completed"
    assert case.completed_steps == RUNBOOKS[kind]


def test_runbook_rejects_skipped_steps_and_sensitive_evidence() -> None:
    engine = RunbookEngine()
    case = engine.start(kind="deletion", case_id="case_deletion_example")

    with pytest.raises(RunbookOrderError):
        engine.complete_step(
            case=case,
            step_id=RUNBOOKS["deletion"][1],
            evidence_ref="audit_skipped_step",
        )
    with pytest.raises(RunbookBoundaryError):
        engine.complete_step(
            case=case,
            step_id=RUNBOOKS["deletion"][0],
            evidence_ref="person@example.test",
        )
