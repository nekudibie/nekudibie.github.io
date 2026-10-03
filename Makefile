.PHONY: dev sync test lint typecheck ui check tokens

dev:            ## one-command local start
	./deploy/scripts/dev.sh

sync:           ## install every role for development
	uv sync --all-packages

test:           ## unit + fixture-backed integration tests
	uv run --no-sync pytest -q

lint:
	uv run --no-sync ruff check .

typecheck:
	uv run --no-sync mypy

ui:             ## build the desk UI the API serves
	cd apps/desk && npm ci --no-audit --no-fund && npm run build

check: lint test

tokens:
	uv run --no-sync companion-api make-token --count 2
