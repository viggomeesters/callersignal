"""Validate repository structure and public-safety invariants without network access."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {"", ".json", ".jsonl", ".md", ".py", ".sh", ".toml", ".yaml", ".yml"}
EXCLUDED_PARTS = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}
ALLOWED_FICTIONAL_NUMBERS = {"202-555-0147"}


def fail(message: str) -> None:
    raise SystemExit(message)


def repository_text_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Makefile", "LICENSE", "go"}:
            files.append(path)
    return files


def check_sensitive_content() -> None:
    secret_patterns = {
        "GitHub token": re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{20,}\b"),
        "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "assigned secret": re.compile(
            r"(?i)\b(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
        ),
    }
    full_phone = re.compile(r"(?<![\w.])\+\d(?:[\s().-]*\d){7,14}(?!\w)")
    phone_like = re.compile(r"(?<![A-Fa-f0-9])(?:\d[ -]?){9,14}\d(?![A-Fa-f0-9])")
    date_like = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    problems = []
    for path in repository_text_files():
        relative = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8", errors="strict")
        for label, pattern in secret_patterns.items():
            if pattern.search(text):
                problems.append(f"{relative}: possible {label}")
        for match in full_phone.finditer(text):
            problems.append(f"{relative}: international phone-like value {match.group(0)!r}")
        for match in phone_like.finditer(text):
            value = match.group(0)
            if value in ALLOWED_FICTIONAL_NUMBERS or date_like.fullmatch(value):
                continue
            digits = re.sub(r"\D", "", value)
            if len(set(digits)) <= 2:
                continue
            problems.append(f"{relative}: phone-like numeric value {value!r}")
    if problems:
        fail("public-safety scan failed:\n" + "\n".join(sorted(set(problems))))


def load_tasks() -> dict[str, dict]:
    tasks = {}
    for state in ("open", "active", "blocked", "done"):
        for path in sorted((ROOT / ".go/tasks" / state).glob("*.json")):
            task = json.loads(path.read_text(encoding="utf-8"))
            if task["id"] in tasks:
                fail(f"duplicate task id: {task['id']}")
            tasks[task["id"]] = task
    return tasks


def check_task_graph() -> None:
    tasks = load_tasks()
    if len(tasks) != 21:
        fail(f"expected 21 repository tasks, found {len(tasks)}")
    product = {task_id for task_id in tasks if task_id.startswith("product-")}
    foundation = {task_id for task_id in tasks if task_id.startswith("foundation-")}
    if len(product) != 16 or len(foundation) != 5:
        fail(f"unexpected task split: {len(foundation)} foundation, {len(product)} product")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            fail(f"cyclic task dependency at {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in tasks[task_id].get("depends_on", []):
            if dependency not in tasks:
                fail(f"{task_id} depends on missing task {dependency}")
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)

    plan = (ROOT / "docs/implementation-plan.md").read_text(encoding="utf-8")
    missing = sorted(task_id for task_id in product if f"`{task_id}`" not in plan)
    if missing:
        fail("implementation plan omits product tasks: " + ", ".join(missing))


def check_ignore_policy() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    required = {
        ".env",
        ".env.*",
        ".secrets/",
        "*.pem",
        "*.key",
        "private/",
        "data/private/",
        "exports/",
        "recordings/",
        ".venv/",
        "__pycache__/",
        ".go/locks/",
        ".go/runs/latest.json",
        ".go/runs/resume.sh",
        ".go/runs/*/",
    }
    missing = sorted(required - set(ignore.splitlines()))
    if missing:
        fail(".gitignore lacks required public-safety rules: " + ", ".join(missing))

    generated = [ROOT / ".venv", ROOT / "tests/__pycache__", ROOT / ".pytest_cache"]
    existing = [str(path.relative_to(ROOT)) for path in generated if path.exists()]
    for relative in existing:
        process = subprocess.run(
            ["git", "check-ignore", "--quiet", relative],
            cwd=ROOT,
            check=False,
        )
        if process.returncode != 0:
            fail(f"generated local state is not ignored: {relative}")


def main() -> None:
    check_sensitive_content()
    check_task_graph()
    check_ignore_policy()
    print("repository public-safety checks passed")


if __name__ == "__main__":
    main()
