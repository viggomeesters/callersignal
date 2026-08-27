#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

required_files=(
  README.md
  docs/architecture.md
  docs/onboarding.md
  docs/data-safety.md
  docs/implementation-plan.md
  docs/agent-contract.md
  docs/vision.json
)

for file in "${required_files[@]}"; do
  test -s "$file" || { printf 'missing required documentation: %s\n' "$file" >&2; exit 1; }
done

for heading in \
  'Current maturity' \
  'Repository map' \
  'Installation' \
  'Development: continue the backlog' \
  'Public-safety boundary' \
  'License'; do
  rg -q "$heading" README.md || { printf 'README section missing: %s\n' "$heading" >&2; exit 1; }
done

if rg -n -i '\b(TODO|TBD|FIXME|lorem ipsum|coming soon)\b' README.md docs --glob '*.md'; then
  printf 'unfinished marker found in public documentation\n' >&2
  exit 1
fi

uv run python - <<'PY'
from pathlib import Path
import re

root = Path.cwd()
files = [root / "README.md", *sorted((root / "docs").glob("*.md"))]
pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
errors = []
planned_public_hygiene = {
    (root / name).resolve()
    for name in (
        "AGENTS.md",
        "CHANGELOG.md",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "SECURITY.md",
        "SUPPORT.md",
        "scripts/check.sh",
    )
}
hygiene_is_open = (root / ".go/tasks/open/foundation-public-hygiene.json").exists()
for source in files:
    for target in pattern.findall(source.read_text(encoding="utf-8")):
        target = target.strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        destination = (source.parent / path_part).resolve()
        if hygiene_is_open and destination in planned_public_hygiene:
            continue
        if not destination.exists():
            errors.append(f"{source.relative_to(root)} -> {target}")
if errors:
    raise SystemExit("broken local documentation links:\n" + "\n".join(errors))
PY

printf 'documentation checks passed\n'
