import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def test_repo_vision_schema_is_valid() -> None:
    schema = load_json("schemas/repo-vision-contract.schema.json")
    Draft202012Validator.check_schema(schema)


def test_repo_vision_contract_matches_schema() -> None:
    schema = load_json("schemas/repo-vision-contract.schema.json")
    vision = load_json("docs/vision.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    errors = sorted(validator.iter_errors(vision), key=lambda error: list(error.path))
    assert not errors, "\n".join(
        f"{'.'.join(map(str, error.absolute_path))}: {error.message}" for error in errors
    )


def test_required_operating_principles_are_explicit() -> None:
    vision = load_json("docs/vision.json")
    principle_ids = {principle["id"] for principle in vision["principles"]}

    assert {
        "agent-first",
        "displayed-number-not-caller",
        "separate-signals",
        "evidence-before-verdict",
        "country-aware-normalization",
        "reliable-fail-closed",
        "public-safe-by-default",
        "source-rights-and-freshness",
    } <= principle_ids


def test_public_safety_boundary_covers_core_failure_modes() -> None:
    vision = load_json("docs/vision.json")
    boundary_text = " ".join(vision["public_safety"]["required_boundaries"]).lower()
    forbidden_text = " ".join(vision["public_safety"]["forbidden"]).lower()

    assert "spoof" in boundary_text
    assert "allocation holder" in boundary_text
    assert "lookup activity" in boundary_text
    assert "real personal phone numbers" in forbidden_text
    assert "raw requester ip" in forbidden_text


def test_scorecard_is_actionable_and_unique() -> None:
    scorecard = load_json("docs/vision.json")["acceptance_scorecard"]
    score_ids = [entry["id"] for entry in scorecard]

    assert len(score_ids) == len(set(score_ids))
    assert "fresh-clone-ready" in score_ids
    assert "spoofing-safe" in score_ids
    assert all(len(entry["pass_condition"]) >= 20 for entry in scorecard)


def test_go_vision_carries_product_assumptions_and_success_metrics() -> None:
    vision = load_json(".go/vision.json")

    assert vision["project"] == "callersignal"
    assert len(vision["assumptions"]) >= 5
    assert len(vision["success_metrics"]) >= 4
    assert any("spoof" in assumption.lower() for assumption in vision["assumptions"])
    assert any("fresh clone" in metric.lower() for metric in vision["success_metrics"])
