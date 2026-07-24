# Unwind — developer Makefile.
# Recipes use TABS (required by make). Run `make help` for a summary.

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Use uv when available (fast), fall back to plain python/pip otherwise.
UV := $(shell command -v uv 2> /dev/null)
PY ?= python

.PHONY: help install lint fmt typecheck test conformance bench cov demo demo-svg \
        results docs docs-build docker-build sandbox-up sandbox-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with dev, docs, and metrics extras (uv preferred)
ifdef UV
	uv pip install -e ".[dev,docs,metrics]"
else
	$(PY) -m pip install -e ".[dev,docs,metrics]"
endif

lint: ## Lint: ruff check + black --check (Black is the formatter of record)
	ruff check .
	black --check .

fmt: ## Auto-format: ruff lint-fix + black (Black is the formatter of record)
	ruff check --fix .
	black .

typecheck: ## Static typing: mypy --strict on the package
	mypy unwind

test: ## Run the fast unit tests (excludes integration & slow)
	pytest -m "not integration and not slow and not benchmark"

conformance: ## MANDATORY gate: protocol-conformance suite (a broken proxy is worthless)
	pytest -m protocol -ra

bench: ## Run performance benchmarks (pytest-benchmark)
	pytest -m benchmark --benchmark-only

cov: ## Run tests with a coverage report
	pytest -m "not integration and not slow and not benchmark" --cov=unwind --cov-report=term-missing --cov-report=xml

demo: ## Run the 20-second undo demo
	$(PY) scripts/demo.py

demo-svg: ## Render the demo to a self-contained SVG (docs/assets/demo.svg)
	$(PY) scripts/record_demo.py

results: ## Regenerate all paper results from pinned configs (writes into paper/, which is gitignored)
	$(PY) -m eval regenerate

docs: ## Serve the docs site locally (mkdocs)
	mkdocs serve

docs-build: ## Build the docs site (strict)
	mkdocs build --strict

docker-build: ## Build the Docker image locally
	docker build -t unwind:local .

sandbox-up: ## Bring up the Docker sandbox (filesystem, git, sqlite, mock comms/payments)
	docker compose up -d --wait

sandbox-down: ## Tear down the Docker sandbox and remove volumes
	docker compose down -v

clean: ## Remove build, test, and cache artifacts
	rm -rf build dist site .pytest_cache .mypy_cache .ruff_cache htmlcov \
		coverage.xml .coverage output.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
