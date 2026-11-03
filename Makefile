# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# Dev tasks. `make check` is the single gate: it runs everything CI runs.
# Needs uv (mise use uv) and Node for markdownlint-cli2; `make demo` needs vhs.

SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

PY_FILES := $(wildcard tools/*.py scripts/*.py tests/*.py)
MARKDOWNLINT ?= npx --yes markdownlint-cli2@0.24.0
UV ?= uv run --locked --quiet

.PHONY: help check lint readme-check complexity deps-audit test build demo audit baseline

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

check: lint complexity deps-audit test build ## The gate: lint, complexity, advisories, tests and a package build

lint: readme-check ## ruff check, ruff format --check, markdownlint and the README template check
	$(UV) ruff check .
	$(UV) ruff format --check .
	shellcheck scripts/*.sh
	$(MARKDOWNLINT)

readme-check: ## README follows ~/Code/README-TEMPLATE.md (checked by the audit itself)
	$(UV) python scripts/readme_check.py

complexity: ## Per-function ceilings against complexity-baseline.json
	$(UV) python scripts/complexity_gate.py $(PY_FILES)

deps-audit: ## pip-audit the locked dependencies against known advisories
	uv export --locked --quiet --no-hashes --no-emit-project --format requirements-txt | uvx --quiet pip-audit@2.10.1 --strict -r /dev/stdin

test: ## pytest
	$(UV) pytest -q

build: ## Build the sdist and wheel into dist/
	uv build --quiet

demo: ## Re-render .github/demo.gif from .github/demo.tape (needs vhs)
	vhs .github/demo.tape

audit: ## Audit the workspace and regenerate reports/ (never edit them by hand)
	python3 tools/audit_compliance.py

baseline: ## Rewrite complexity-baseline.json after an offender shrinks
	$(UV) python scripts/complexity_gate.py --write $(PY_FILES)
