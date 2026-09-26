HOST ?= 127.0.0.1
PORT ?= 6280

.PHONY: help install backend-install frontend-install frontend-build start scheduler worker dev check \
	agim-check zett-weixin-check ruff-check typecheck pre-commit-install docs-build docs-serve site

help:
	@echo "Available targets:"
	@echo "  make install   Build the frontend and install the zett command"
	@echo "  make start     Start the installed application"
	@echo "  make scheduler Start the scheduling control process"
	@echo "  make worker    Start an execution worker"
	@echo "  make dev       Build and start the application from source"
	@echo "  make check     Run backend lint, tests, and frontend checks"
	@echo "  make docs-serve Build and serve the whole site at http://127.0.0.1:8000"
	@echo "  make site      Build the landing page and the docs into site/ for preview"
	@echo "  make pre-commit-install  Install the Ruff and TypeScript Git hooks"

install: frontend-install frontend-build
	uv tool install --force --refresh-package zett ./backend
	@echo "Installed. Run: zett start"

backend-install:
	uv sync --directory backend --locked

frontend-install:
	npm --prefix frontend install

frontend-build:
	npm --prefix frontend run typecheck
	npm --prefix frontend run build

start:
	zett start --host $(HOST) --port $(PORT)

scheduler: backend-install
	uv run --directory backend zett scheduler

worker: backend-install
	uv run --directory backend zett worker

dev: backend-install frontend-build
	uv run --directory backend zett start --host $(HOST) --port $(PORT) --reload

ruff-check:
	uv run --directory backend ruff format --check zett
	uv run --directory backend ruff check zett
	uv run --directory backend/agim ruff format --check src tests
	uv run --directory backend/agim ruff check src tests
	uv run --directory backend/zett-weixin ruff format --check src tests
	uv run --directory backend/zett-weixin ruff check src tests

typecheck:
	npm --prefix frontend run typecheck

pre-commit-install: backend-install frontend-install
	GIT_CONFIG_GLOBAL=/dev/null uv run --directory backend pre-commit install

check:
	$(MAKE) ruff-check
	uv run --directory backend pytest
	$(MAKE) agim-check
	$(MAKE) zett-weixin-check
	npm --prefix frontend run test
	$(MAKE) typecheck
	npm --prefix frontend run build

docs-build:
	# --project selects the backend environment without changing the working
	# directory, so the script path stays relative to the repository root.
	uv run --project backend python web/tools/build_docs.py

docs-serve: site
	python3 -m http.server -d site 8000

# What the Docs workflow publishes: the landing page at the root, the
# documentation under /docs/. The build starts from an empty site/ so a stale
# stylesheet or page can never survive a rebuild, and web/tools stays out of the
# published site.
site:
	rm -rf site
	$(MAKE) docs-build
	cp -R web/styles/. site/styles/
	cp -R web/scripts/. site/scripts/
	cp -R web/assets/. site/assets/
	cp web/index.html site/index.html
	@echo "Preview with: python3 -m http.server -d site 8000"

agim-check:
	uv run --directory backend/agim ruff format --check src tests
	uv run --directory backend/agim ruff check src tests
	uv run --directory backend/agim pytest

zett-weixin-check:
	uv run --directory backend/zett-weixin ruff format --check src tests
	uv run --directory backend/zett-weixin ruff check src tests
	uv run --directory backend/zett-weixin pytest
