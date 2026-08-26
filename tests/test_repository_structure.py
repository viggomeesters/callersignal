from __future__ import annotations

import json
import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def all_tasks() -> dict[str, dict]:
    tasks = {}
    for state in ("open", "active", "blocked", "done"):
        for path in (ROOT / ".go/tasks" / state).glob("*.json"):
            task = json.loads(path.read_text(encoding="utf-8"))
            tasks[task["id"]] = task
    return tasks


def test_public_repository_files_are_present() -> None:
    expected = {
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SUPPORT.md",
        "CHANGELOG.md",
        "AGENTS.md",
        "docs/architecture.md",
        "docs/onboarding.md",
        "docs/data-safety.md",
        "docs/agent-contract.md",
        "docs/implementation-plan.md",
    }
    missing = [name for name in expected if not (ROOT / name).is_file()]
    assert not missing
    assert all((ROOT / name).stat().st_size > 100 for name in expected)


def test_task_graph_is_complete_and_acyclic() -> None:
    tasks = all_tasks()
    assert len(tasks) == 21
    assert len([task for task in tasks if task.startswith("foundation-")]) == 5
    assert len([task for task in tasks if task.startswith("product-")]) == 16

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        assert task_id not in visiting
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in tasks[task_id].get("depends_on", []):
            assert dependency in tasks
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)


def test_plan_names_every_product_task() -> None:
    tasks = all_tasks()
    plan = (ROOT / "docs/implementation-plan.md").read_text(encoding="utf-8")
    product_ids = {task_id for task_id in tasks if task_id.startswith("product-")}
    documented_ids = set(re.findall(r"^### `(product-[a-z0-9-]+)`$", plan, re.MULTILINE))
    assert documented_ids == product_ids


def test_readme_is_content_first_and_maturity_honest() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# CallerSignal\n")
    assert "Current maturity" in readme[:1_000]
    assert "not implemented yet" in readme[:1_000]
    assert "Go" in readme
    assert "202-555-0147" in readme


def test_no_unfinished_markers_in_public_markdown() -> None:
    pattern = re.compile(r"\b(TODO|TBD|FIXME|lorem ipsum|coming soon)\b", re.IGNORECASE)
    files = [ROOT / "README.md", *ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md")]
    matches = [path.relative_to(ROOT) for path in files if pattern.search(path.read_text())]
    assert not matches


def test_repository_scripts_are_executable() -> None:
    scripts = [
        ROOT / "go",
        ROOT / "scripts/bootstrap-stack.sh",
        ROOT / "scripts/validate-go.sh",
        ROOT / "scripts/check.sh",
        ROOT / "scripts/check-docs.sh",
        ROOT / "scripts/check-assets.sh",
        ROOT / "scripts/check-public-safety.sh",
    ]
    assert all(path.stat().st_mode & stat.S_IXUSR for path in scripts)


def test_gitignore_protects_sensitive_and_runtime_state() -> None:
    entries = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())
    assert {
        ".env",
        ".env.*",
        ".secrets/",
        "*.pem",
        "*.key",
        "private/",
        "exports/",
        "recordings/",
        ".go/locks/",
        ".go/runs/latest.json",
        ".go/runs/resume.sh",
        ".go/runs/*/",
    } <= entries
