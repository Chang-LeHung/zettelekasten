HOST ?= 127.0.0.1
PORT ?= 6280

.PHONY: help install backend-install frontend-install frontend-build start dev check

help:
	@echo "Available targets:"
	@echo "  make install   Build the frontend and install the kcs command"
	@echo "  make start     Start the installed application"
	@echo "  make dev       Build and start the application from source"
	@echo "  make check     Run backend lint and frontend type/build checks"

install: frontend-install frontend-build
	uv tool install --force ./backend
	@echo "Installed. Run: kcs start"

backend-install:
	uv sync --directory backend --locked

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
	npm --prefix frontend run test
	npm --prefix frontend run typecheck
	npm --prefix frontend run build
