.PHONY: check test lint validate-go check-docs check-assets check-safety

check:
	@bash scripts/check.sh

test:
	@uv run pytest -q

lint:
	@uv run ruff check tests scripts/validate_repository.py

validate-go:
	@bash scripts/validate-go.sh

check-docs:
	@bash scripts/check-docs.sh

check-assets:
	@bash scripts/check-assets.sh

check-safety:
	@bash scripts/check-public-safety.sh
