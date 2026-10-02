HOST ?= 127.0.0.1
PORT ?= 6280
# GitHub Pages serves this repository as a project site, so its workflow builds
# with SITE_BASE=/zettelekasten/; a local `make site` serves the tree at /.
SITE_BASE ?= /

.PHONY: help install backend-install frontend-install frontend-build start status scheduler worker dev check \
	agim-check zett-weixin-check ruff-check typecheck pre-commit-install docs-install docs-build docs-serve site package

help:
	@echo "Available targets:"
	@echo "  make install   Build the frontend and install the zett command"
	@echo "  make docs-install  Install the documentation site's Node dependencies"
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
	npm --prefix zett3rd/chrome-extension run test
	npm --prefix zett3rd/chrome-extension run typecheck
	npm --prefix zett3rd/chrome-extension run build
	npm --prefix zett3rd/zettelekasten-chatgpt run typecheck
	npm --prefix zett3rd/zettelekasten-chatgpt run test
	$(MAKE) docs-build

# The documentation is a VitePress site: the default theme with Zett's green
# palette, rendered from docs/*.md into site/docs/. `docs/node_modules` is a
# prerequisite for both targets, installed once with `make docs-install`.
docs-install:
	npm --prefix docs ci

docs-build:
	DOCS_BASE=$(SITE_BASE)docs/ npm --prefix docs run build

docs-serve: site
	python3 -m http.server -d site 8000

# What the Docs workflow publishes: the landing page at the root, the
# documentation under /docs/. The build starts from an empty site/ so a stale
# stylesheet or page can never survive a rebuild.
site:
	rm -rf site
	$(MAKE) docs-build
	node web/tools/compose_site.mjs --base $(SITE_BASE)
	@echo "Preview with: python3 -m http.server -d site 8000"

# The wheel embeds the compiled interface under zett/static, so the frontend
# build has to run first; backend/hatch_build.py adds the README as the long
# description that the PyPI page renders.
# Every distribution the release publishes, in dependency order: the release
# workflow publishes these same three, and PyPI refuses an install whose pinned
# requirements are missing. `--out-dir` is relative to each project, so the
# absolute paths keep all three artifacts in the repository's `dist/`.
package: frontend-build
	uv build --directory backend/agim --out-dir $(CURDIR)/dist/agim
	uv build --directory backend/zett-weixin --out-dir $(CURDIR)/dist/zett-weixin
	uv build --directory backend --out-dir $(CURDIR)/dist/zettelekasten
	uv run --no-project --with twine twine check dist/*/*

agim-check:
	uv run --directory backend/agim ruff format --check src tests
	uv run --directory backend/agim ruff check src tests
	uv run --directory backend/agim pytest

zett-weixin-check:
	uv run --directory backend/zett-weixin ruff format --check src tests
	uv run --directory backend/zett-weixin ruff check src tests
	uv run --directory backend/zett-weixin pytest
