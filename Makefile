SHELL := /bin/sh

COMPOSE_FILE := docker/compose.yaml
ENV_FILE := docker/.env

.PHONY: help run frontend test lint format

help:
	@echo "Available commands:"
	@echo "  make run     Build and run the full application with Docker Compose"
	@echo "  make frontend Run the Vite frontend development server"
	@echo "  make test    Run all configured project tests"
	@echo "  make lint    Check backend code with Ruff"
	@echo "  make format  Fix and format backend code with Ruff"

run:
	@test -f "$(COMPOSE_FILE)" || { \
		echo "Error: $(COMPOSE_FILE) is not configured yet." >&2; \
		exit 1; \
	}
	@if [ -f "$(ENV_FILE)" ]; then \
		docker compose --env-file "$(ENV_FILE)" -f "$(COMPOSE_FILE)" up --build; \
	else \
		docker compose -f "$(COMPOSE_FILE)" up --build; \
	fi

frontend:
	@npm --prefix frontend run dev

test:
	@npm --prefix frontend test
	@uv run --project backend --locked pytest

lint:
	@uv run --project backend --locked ruff check backend
	@uv run --project backend --locked ruff format --check backend

format:
	@uv run --project backend --locked ruff check --fix backend
	@uv run --project backend --locked ruff format backend
