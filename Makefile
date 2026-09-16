HOST ?= 127.0.0.1
PORT ?= 6280
DOCS_HOST ?= 127.0.0.1
DOCS_PORT ?= 8000

.PHONY: help install backend-install zett-agent-install zettcode-install frontend-install frontend-build start dev check \
	zett-agent-check zettcode-check ruff-check typecheck pre-commit-install docs docs-serve docs-check docs-examples docs-ui-check

help:
	@echo "Available targets:"
	@echo "  make install   Build the frontend, install the zett command, and sync the zett-agent runtime"
	@echo "  make start     Start the installed application"
	@echo "  make dev       Build and start the application from source"
	@echo "  make check     Run backend lint and frontend type/build checks"
	@echo "  make zett-agent-check  Verify the standalone agent runtime"
	@echo "  make zettcode-check  Verify the standalone ZettCode terminal agent"
	@echo "  make pre-commit-install  Install the Ruff and TypeScript Git hooks"
	@echo "  make docs      Build the Zett Agent API documentation"
	@echo "  make docs-serve  Build and preview docs at http://$(DOCS_HOST):$(DOCS_PORT)"
	@echo "  make docs-check  Validate public API coverage, examples, and local links"
	@echo "  make docs-examples  Run all offline documentation examples"
	@echo "  make docs-ui-check  Verify desktop/mobile navigation and search in Chromium"

install: frontend-install frontend-build zett-agent-install
	uv tool install --force --refresh-package zett --refresh-package zett-agent ./backend
	@echo "Installed. Run: zett start"

backend-install:
	uv sync --directory backend --locked

zett-agent-install:
	uv sync --directory backend/zett-agent
	@echo "zett-agent installed locally at backend/zett-agent/.venv"

zettcode-install:
	uv sync --directory backend/zettcode
	@echo "zettcode installed locally at backend/zettcode/.venv"

frontend-install:
	npm --prefix frontend install

frontend-build:
	npm --prefix frontend run typecheck
	npm --prefix frontend run build

start:
	zett start --host $(HOST) --port $(PORT)

dev: backend-install frontend-build
	uv run --directory backend zett start --host $(HOST) --port $(PORT) --reload

ruff-check:
	uv run --directory backend ruff format --check zett tests
	uv run --directory backend ruff check zett tests
	env -u VIRTUAL_ENV uv run --directory backend/zett-agent ruff format --check src tests examples
	env -u VIRTUAL_ENV uv run --directory backend/zett-agent ruff check src tests examples
	env -u VIRTUAL_ENV uv run --directory backend/zettcode ruff format --check src tests
	env -u VIRTUAL_ENV uv run --directory backend/zettcode ruff check src tests

typecheck:
	npm --prefix frontend run typecheck

pre-commit-install: backend-install frontend-install
	GIT_CONFIG_GLOBAL=/dev/null uv run --directory backend pre-commit install

check:
	$(MAKE) ruff-check
	uv run --directory backend pytest
	$(MAKE) zett-agent-check
	$(MAKE) zettcode-check
	$(MAKE) docs-check
	npm --prefix frontend run test
	$(MAKE) typecheck
	npm --prefix frontend run build

zett-agent-check:
	uv run --directory backend/zett-agent ruff format --check src tests examples
	uv run --directory backend/zett-agent ruff check src tests examples
	uv run --directory backend/zett-agent pytest --cov --cov-report=term-missing

zettcode-check:
	env -u VIRTUAL_ENV uv run --directory backend/zettcode ruff format --check src tests
	env -u VIRTUAL_ENV uv run --directory backend/zettcode ruff check src tests
	env -u VIRTUAL_ENV uv run --directory backend/zettcode pytest

docs:
	env -u VIRTUAL_ENV uv run --directory backend/zett-agent --group docs sphinx-build -E -a -W --keep-going -b html docs docs/_build/html

docs-serve: docs
	@echo "Zett Agent docs: http://$(DOCS_HOST):$(DOCS_PORT) (Ctrl+C to stop)"
	env -u VIRTUAL_ENV uv run --directory backend/zett-agent --group docs python -m http.server $(DOCS_PORT) --bind $(DOCS_HOST) --directory docs/_build/html

docs-examples:
	env -u VIRTUAL_ENV uv run --directory backend/zett-agent --group docs pytest tests/test_documentation_examples.py -q

docs-ui-check:
	env -u VIRTUAL_ENV uv run --directory backend/zett-agent --group docs-test playwright install chromium
	env -u VIRTUAL_ENV uv run --directory backend/zett-agent --group docs --group docs-test pytest tests/test_documentation.py -q

docs-check:
	env -u VIRTUAL_ENV uv run --directory backend/zett-agent --group docs ruff check docs
	env -u VIRTUAL_ENV uv run --directory backend/zett-agent --group docs pytest tests/test_documentation.py tests/test_documentation_examples.py -q
