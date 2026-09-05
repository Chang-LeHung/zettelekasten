HOST ?= 127.0.0.1
PORT ?= 6280

.PHONY: help install backend-install kcs-agent-install frontend-install frontend-build start dev check kcs-agent-check

help:
	@echo "Available targets:"
	@echo "  make install   Build the frontend, install the kcs command, and sync the kcs-agent runtime"
	@echo "  make start     Start the installed application"
	@echo "  make dev       Build and start the application from source"
	@echo "  make check     Run backend lint and frontend type/build checks"
	@echo "  make kcs-agent-check  Verify the standalone agent runtime"

install: frontend-install frontend-build kcs-agent-install
	uv tool install --force ./backend
	@echo "Installed. Run: kcs start"

backend-install:
	uv sync --directory backend --locked

kcs-agent-install:
	uv sync --directory backend/kcs-agent
	@echo "kcs-agent installed locally at backend/kcs-agent/.venv"

frontend-install:
	npm --prefix frontend install

frontend-build:
	npm --prefix frontend run typecheck
	npm --prefix frontend run build

start:
	kcs start --host $(HOST) --port $(PORT)

dev: backend-install frontend-build
	uv run --directory backend kcs start --host $(HOST) --port $(PORT) --reload

check:
	uv run --directory backend ruff format --check kcs tests
	uv run --directory backend ruff check kcs tests
	uv run --directory backend pytest
	$(MAKE) kcs-agent-check
	npm --prefix frontend run test
	npm --prefix frontend run typecheck
	npm --prefix frontend run build

kcs-agent-check:
	uv run --directory backend/kcs-agent ruff format --check src tests examples
	uv run --directory backend/kcs-agent ruff check src tests examples
	uv run --directory backend/kcs-agent pytest --cov --cov-report=term-missing
