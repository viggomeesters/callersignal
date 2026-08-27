#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

uv sync --locked --dev
uv run ruff check tests scripts/validate_repository.py
uv run pytest -q
npm test
bash scripts/validate-go.sh
bash scripts/check-docs.sh
bash scripts/check-assets.sh
bash scripts/check-public-safety.sh
git diff --check

printf 'all repository checks passed\n'
