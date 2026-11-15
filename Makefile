SHELL := /bin/sh

COMPOSE_FILE := docker/compose.yaml
ENV_FILE := docker/.env

.PHONY: help run migrate create-admin frontend test lint format

help:
	@echo "Available commands:"
	@echo "  make run     Build and run the full application with Docker Compose"
	@echo "  make migrate Apply database migrations with Docker Compose"
	@echo "  make create-admin LOGIN=<login> Create an administrator account"
	@echo "  make knowledge-check DIR=<path> Check a knowledge package"
	@echo "  make knowledge-load DIR=<path> [FORMAT=json] Check and load a knowledge package into PostgreSQL"
	@echo "  make knowledge-export DIR=<path> [FORMAT=json] [TYPE=<type>] Export knowledge into a package"
	@echo "  make knowledge-delete REFS=\"<type>/<id> ...\" [APPLY=1] [FORMAT=json] Delete knowledge entities"
	@echo "  make knowledge-restore REF=<type>/<id> [REVISION=N] [APPLY=1] [FORMAT=json] Restore a knowledge entity"
	@echo "  make frontend Run the Vite frontend development server"
	@echo "  make test    Run all configured project tests"
	@echo "  make test-integration [PYTEST_ARGS=...] Run backend tests against disposable PostgreSQL and Redis"
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

migrate:
	@if [ -f "$(ENV_FILE)" ]; then \
		docker compose --env-file "$(ENV_FILE)" -f "$(COMPOSE_FILE)" run --rm --build migrate; \
	else \
		docker compose -f "$(COMPOSE_FILE)" run --rm --build migrate; \
	fi

create-admin:
	@test -n "$(LOGIN)" || { \
		echo "Usage: make create-admin LOGIN=<login>" >&2; \
		exit 2; \
	}
	@$(MAKE) --no-print-directory migrate
	@if [ -f "$(ENV_FILE)" ]; then \
		docker compose --env-file "$(ENV_FILE)" -f "$(COMPOSE_FILE)" run --rm migrate \
			python -m smeshariki_ai.create_admin --login "$(LOGIN)"; \
	else \
		docker compose -f "$(COMPOSE_FILE)" run --rm migrate \
			python -m smeshariki_ai.create_admin --login "$(LOGIN)"; \
	fi

.PHONY: knowledge-check

knowledge-check:
	@test -n "$(DIR)" || { \
		echo "Usage: make knowledge-check DIR=<path>" >&2; \
		exit 2; \
	}
	@uv run --project backend --locked python -m smeshariki_ai.rag check "$(DIR)"

.PHONY: knowledge-load

knowledge-load:
	@test -n "$(DIR)" || { \
		echo "Usage: make knowledge-load DIR=<path> [FORMAT=json]" >&2; \
		exit 2; \
	}
	@test -d "$(DIR)" || { \
		echo "Error: knowledge package $(DIR) is not a directory." >&2; \
		exit 2; \
	}
	@$(MAKE) --no-print-directory migrate >&2
	@if [ -f "$(ENV_FILE)" ]; then \
		docker compose --env-file "$(ENV_FILE)" -f "$(COMPOSE_FILE)" run --rm \
			-v "$(abspath $(DIR)):/knowledge:ro" migrate \
			python -m smeshariki_ai.rag load /knowledge --format "$(or $(FORMAT),text)"; \
	else \
		docker compose -f "$(COMPOSE_FILE)" run --rm \
			-v "$(abspath $(DIR)):/knowledge:ro" migrate \
			python -m smeshariki_ai.rag load /knowledge --format "$(or $(FORMAT),text)"; \
	fi

.PHONY: knowledge-export

knowledge-export:
	@test -n "$(DIR)" || { \
		echo "Usage: make knowledge-export DIR=<path> [FORMAT=json] [TYPE=<type>]" >&2; \
		exit 2; \
	}
	@test -d "$(DIR)" || { \
		echo "Error: knowledge export directory $(DIR) does not exist." >&2; \
		exit 2; \
	}
	@test -z "$$(find "$(DIR)" -mindepth 1 -print -quit)" || { \
		echo "Error: knowledge export directory $(DIR) is not empty." >&2; \
		exit 2; \
	}
	@if [ -f "$(ENV_FILE)" ]; then \
		docker compose --env-file "$(ENV_FILE)" -f "$(COMPOSE_FILE)" run --rm \
			--user "$$(id -u):$$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
			-v "$(abspath $(DIR)):/knowledge" migrate \
			python -m smeshariki_ai.rag export /knowledge \
			$(if $(TYPE),--type $(TYPE),) --format "$(or $(FORMAT),text)"; \
	else \
		docker compose -f "$(COMPOSE_FILE)" run --rm \
			--user "$$(id -u):$$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
			-v "$(abspath $(DIR)):/knowledge" migrate \
			python -m smeshariki_ai.rag export /knowledge \
			$(if $(TYPE),--type $(TYPE),) --format "$(or $(FORMAT),text)"; \
	fi

.PHONY: knowledge-delete

knowledge-delete:
	@test -n "$(REFS)" || { \
		echo "Usage: make knowledge-delete REFS=\"<type>/<id> ...\" [APPLY=1] [FORMAT=json]" >&2; \
		exit 2; \
	}
	@if [ -f "$(ENV_FILE)" ]; then \
		docker compose --env-file "$(ENV_FILE)" -f "$(COMPOSE_FILE)" run --rm migrate \
			python -m smeshariki_ai.rag delete $(REFS) \
			$(if $(filter 1,$(APPLY)),--apply,) --format "$(or $(FORMAT),text)"; \
	else \
		docker compose -f "$(COMPOSE_FILE)" run --rm migrate \
			python -m smeshariki_ai.rag delete $(REFS) \
			$(if $(filter 1,$(APPLY)),--apply,) --format "$(or $(FORMAT),text)"; \
	fi

.PHONY: knowledge-restore

knowledge-restore:
	@test -n "$(REF)" || { \
		echo "Usage: make knowledge-restore REF=<type>/<id> [REVISION=N] [APPLY=1] [FORMAT=json]" >&2; \
		exit 2; \
	}
	@if [ -f "$(ENV_FILE)" ]; then \
		docker compose --env-file "$(ENV_FILE)" -f "$(COMPOSE_FILE)" run --rm migrate \
			python -m smeshariki_ai.rag restore $(REF) \
			$(if $(REVISION),--revision $(REVISION),) \
			$(if $(filter 1,$(APPLY)),--apply,) --format "$(or $(FORMAT),text)"; \
	else \
		docker compose -f "$(COMPOSE_FILE)" run --rm migrate \
			python -m smeshariki_ai.rag restore $(REF) \
			$(if $(REVISION),--revision $(REVISION),) \
			$(if $(filter 1,$(APPLY)),--apply,) --format "$(or $(FORMAT),text)"; \
	fi

frontend:
	@npm --prefix frontend run dev

test:
	@npm --prefix frontend test
	@uv run --project backend --locked pytest backend

.PHONY: test-integration

test-integration:
	@sh docker/test-integration.sh

lint:
	@uv run --project backend --locked ruff check backend
	@uv run --project backend --locked ruff format --check backend

format:
	@uv run --project backend --locked ruff check --fix backend
	@uv run --project backend --locked ruff format backend
