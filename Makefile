HOST ?= 127.0.0.1
PORT ?= 6280

.PHONY: help install backend-install frontend-install frontend-build start status scheduler worker dev check \
	agim-check zett-weixin-check ruff-check typecheck pre-commit-install docs-build docs-serve site package

help:
	@echo "Available targets:"
	@echo "  make install   Build the frontend and install the zett command"
	@echo "  make start     Start the installed application"
	@echo "  make status    Show whether the application is running"
	@echo "  make scheduler Start the scheduling control process"
	@echo "  make worker    Start an execution worker"
	@echo "  make dev       Build and start the application from source"
	@echo "  make check     Run backend lint, tests, and frontend checks"
	@echo "  make package   Build the frontend and the distributable wheel and sdist"
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

status:
	zett status

scheduler: backend-install
	uv run --directory backend zett scheduler

worker: backend-install
	uv run --directory backend zett worker

dev: backend-install frontend-build
	uv run --directory backend zett start --foreground --host $(HOST) --port $(PORT) --reload

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

# The local build serves the site from the repository root, so every in-site
# URL is root-absolute; the Docs workflow passes --base /zettelekasten/ because
# GitHub Pages serves this repository as a project site.
docs-build:
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
	@echo "Preview with: python3 -m http.server -d site 8000"

# The wheel embeds the compiled interface under zett/static, so the frontend
# build has to run first; backend/hatch_build.py adds the README as the long
# description that the PyPI page renders.
package: frontend-build
	uv build --directory backend --out-dir ../dist

agim-check:
	uv run --directory backend/agim ruff format --check src tests
	uv run --directory backend/agim ruff check src tests
	uv run --directory backend/agim pytest

zett-weixin-check:
	uv run --directory backend/zett-weixin ruff format --check src tests
	uv run --directory backend/zett-weixin ruff check src tests
	uv run --directory backend/zett-weixin pytest
