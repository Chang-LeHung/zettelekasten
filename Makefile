HOST ?= 127.0.0.1
PORT ?= 6280

.PHONY: help install backend-install zett-agent-install frontend-install frontend-build start dev check \
	zett-agent-check ruff-check typecheck pre-commit-install

help:
	@echo "Available targets:"
	@echo "  make install   Build the frontend, install the zett command, and sync the zett-agent runtime"
	@echo "  make start     Start the installed application"
	@echo "  make dev       Build and start the application from source"
	@echo "  make check     Run backend lint and frontend type/build checks"
	@echo "  make zett-agent-check  Verify the standalone agent runtime"
	@echo "  make pre-commit-install  Install the Ruff and TypeScript Git hooks"

install: frontend-install frontend-build zett-agent-install
	uv tool install --force ./backend
	@echo "Installed. Run: zett start"

backend-install:
	uv sync --directory backend --locked

zett-agent-install:
	uv sync --directory backend/zett-agent
	@echo "zett-agent installed locally at backend/zett-agent/.venv"

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

typecheck:
	npm --prefix frontend run typecheck

pre-commit-install: backend-install frontend-install
	GIT_CONFIG_GLOBAL=/dev/null uv run --directory backend pre-commit install

check:
	$(MAKE) ruff-check
	uv run --directory backend pytest
	$(MAKE) zett-agent-check
	npm --prefix frontend run test
	$(MAKE) typecheck
	npm --prefix frontend run build

zett-agent-check:
	uv run --directory backend/zett-agent ruff format --check src tests examples
	uv run --directory backend/zett-agent ruff check src tests examples
	uv run --directory backend/zett-agent pytest --cov --cov-report=term-missing
