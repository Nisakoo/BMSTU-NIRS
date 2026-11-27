SHELL := /bin/sh

COMPOSE_FILE := docker/compose.yaml
ENV_FILE := docker/.env
COMPOSE := docker compose $(if $(wildcard $(ENV_FILE)),--env-file "$(ENV_FILE)") -f "$(COMPOSE_FILE)"

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
	@echo "  make lore-check DIR=<path> Check a lore YAML package"
	@echo "  make lore-clean DIR=<path> [APPLY=1] Remove technical noise from a lore package"
	@echo "  make knowledge-benchmark DIR=<path> QUESTIONS=<yaml> Benchmark exact canon lookup"
	@echo "  make lore-load DIR=<path> [FORMAT=json] Replace the lore corpus and BM25 index"
	@echo "  make lore-search QUERY=\"...\" [TOPK=5] [FORMAT=json] Search the lore corpus"
	@echo "  make lore-benchmark DIR=<path> QUESTIONS=<yaml> [K=5] [ANSWERS=<json>] [CONTEXT=1] [EXPAND=1] [HYBRID=1] Run the lore benchmark"
	@echo "  make data-encrypt Encrypt data/ into encrypted/data.enc (asks for the passphrase)"
	@echo "  make data-decrypt [FORCE=1] Restore data/ from encrypted/data.enc (asks for the passphrase)"
	@echo "  make frontend Run the Vite frontend development server"
	@echo "  make test    Run all configured project tests"
	@echo "  make benchmark Run the committed 30-document BM25 benchmark (no DB, no LLM)"
	@echo "  make test-integration [PYTEST_ARGS=...] Run backend tests against disposable PostgreSQL and Redis"
	@echo "  make lint    Check backend code with Ruff"
	@echo "  make format  Fix and format backend code with Ruff"

run:
	@test -f "$(COMPOSE_FILE)" || { \
		echo "Error: $(COMPOSE_FILE) is not configured yet." >&2; \
		exit 1; \
	}
	@compose_environment=$$($(COMPOSE) config --environment) || exit $$?; \
	speech_enabled=$$(printf '%s\n' "$$compose_environment" | sed -n 's/^SPEECH_ENABLED=//p'); \
	. docker/backend-features.sh; \
	if feature_enabled "$$speech_enabled"; then \
		set -- -f "$(dir $(COMPOSE_FILE))compose.speech.yaml"; \
	fi; \
	exec $(COMPOSE) "$$@" up --build --remove-orphans

migrate:
	@$(COMPOSE) build backend
	@$(COMPOSE) run --rm migrate

create-admin:
	@test -n "$(LOGIN)" || { \
		echo "Usage: make create-admin LOGIN=<login>" >&2; \
		exit 2; \
	}
	@$(MAKE) --no-print-directory migrate
	@$(COMPOSE) run --rm migrate \
		python -m smeshariki_ai.create_admin --login "$(LOGIN)"

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
	@$(COMPOSE) run --rm \
		-v "$(abspath $(DIR)):/knowledge:ro" migrate \
		python -m smeshariki_ai.rag load /knowledge --format "$(or $(FORMAT),text)"

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
	@$(COMPOSE) build backend >&2
	@$(COMPOSE) run --rm \
		--user "$$(id -u):$$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
		-v "$(abspath $(DIR)):/knowledge" migrate \
		python -m smeshariki_ai.rag export /knowledge \
		$(if $(TYPE),--type $(TYPE),) --format "$(or $(FORMAT),text)"

.PHONY: knowledge-delete

knowledge-delete:
	@test -n "$(REFS)" || { \
		echo "Usage: make knowledge-delete REFS=\"<type>/<id> ...\" [APPLY=1] [FORMAT=json]" >&2; \
		exit 2; \
	}
	@$(COMPOSE) build backend >&2
	@$(COMPOSE) run --rm migrate \
		python -m smeshariki_ai.rag delete $(REFS) \
		$(if $(filter 1,$(APPLY)),--apply,) --format "$(or $(FORMAT),text)"

.PHONY: knowledge-restore

knowledge-restore:
	@test -n "$(REF)" || { \
		echo "Usage: make knowledge-restore REF=<type>/<id> [REVISION=N] [APPLY=1] [FORMAT=json]" >&2; \
		exit 2; \
	}
	@$(COMPOSE) build backend >&2
	@$(COMPOSE) run --rm migrate \
		python -m smeshariki_ai.rag restore $(REF) \
		$(if $(REVISION),--revision $(REVISION),) \
		$(if $(filter 1,$(APPLY)),--apply,) --format "$(or $(FORMAT),text)"

.PHONY: data-encrypt data-decrypt

DATA_CRYPT := uv run --quiet --locked --script .agents/skills/data-crypt/scripts/data_crypt.py

data-encrypt:
	@$(DATA_CRYPT) encrypt

data-decrypt:
	@$(DATA_CRYPT) decrypt $(if $(filter 1,$(FORCE)),--force,)

.PHONY: benchmark

BENCHMARK_DIR := backend/tests/fixtures/lore_benchmark

benchmark:
	@uv run --project backend --locked python -m smeshariki_ai.rag lore-benchmark \
		$(BENCHMARK_DIR)/lore \
		--questions $(BENCHMARK_DIR)/questions.yaml \
		--answers $(BENCHMARK_DIR)/answers.json \
		--context --k "$(or $(K),5)"

.PHONY: lore-check

lore-check:
	@test -n "$(DIR)" || { \
		echo "Usage: make lore-check DIR=<path>" >&2; \
		exit 2; \
	}
	@uv run --project backend --locked python -m smeshariki_ai.rag lore-check "$(DIR)" --format "$(or $(FORMAT),text)"

.PHONY: lore-clean

lore-clean:
	@test -n "$(DIR)" || { \
		echo "Usage: make lore-clean DIR=<path> [APPLY=1]" >&2; \
		exit 2; \
	}
	@uv run --project backend --locked python -m smeshariki_ai.rag lore-clean "$(DIR)" \
		$(if $(filter 1,$(APPLY)),--apply,) --format "$(or $(FORMAT),text)"

.PHONY: knowledge-benchmark

knowledge-benchmark:
	@test -n "$(DIR)" || { \
		echo "Usage: make knowledge-benchmark DIR=<path> QUESTIONS=<yaml>" >&2; \
		exit 2; \
	}
	@test -n "$(QUESTIONS)" || { \
		echo "Usage: make knowledge-benchmark DIR=<path> QUESTIONS=<yaml>" >&2; \
		exit 2; \
	}
	@uv run --project backend --locked python -m smeshariki_ai.rag knowledge-benchmark "$(DIR)" \
		--questions "$(QUESTIONS)" --format "$(or $(FORMAT),text)"

.PHONY: lore-load

lore-load:
	@test -n "$(DIR)" || { \
		echo "Usage: make lore-load DIR=<path> [FORMAT=json]" >&2; \
		exit 2; \
	}
	@test -d "$(DIR)" || { \
		echo "Error: lore package $(DIR) is not a directory." >&2; \
		exit 2; \
	}
	@$(MAKE) --no-print-directory migrate >&2
	@$(COMPOSE) run --rm \
		-v "$(abspath $(DIR)):/lore:ro" migrate \
		python -m smeshariki_ai.rag lore-load /lore --format "$(or $(FORMAT),text)"

.PHONY: lore-search

lore-search:
	@test -n "$(QUERY)" || { \
		echo "Usage: make lore-search QUERY=\"...\" [TOPK=5] [FORMAT=json]" >&2; \
		exit 2; \
	}
	@$(COMPOSE) build backend >&2
	@$(COMPOSE) run --rm migrate \
		python -m smeshariki_ai.rag lore-search "$(QUERY)" \
		--top-k "$(or $(TOPK),5)" --format "$(or $(FORMAT),text)"

.PHONY: lore-benchmark

LORE_BENCHMARK_ENV = $(if $(filter 1,$(HYBRID)),RAG_HYBRID_ENABLED=true BACKEND_IMAGE_SUFFIX=-hybrid-benchmark)

lore-benchmark:
	@test -n "$(DIR)" || { \
		echo "Usage: make lore-benchmark DIR=<path> QUESTIONS=<yaml> [K=5] [ANSWERS=<json>] [CONTEXT=1] [HYBRID=1]" >&2; \
		exit 2; \
	}
	@test -n "$(QUESTIONS)" || { \
		echo "Usage: make lore-benchmark DIR=<path> QUESTIONS=<yaml> [K=5] [ANSWERS=<json>] [CONTEXT=1] [HYBRID=1]" >&2; \
		exit 2; \
	}
	@test -d "$(DIR)" || { \
		echo "Error: lore package $(DIR) is not a directory." >&2; \
		exit 2; \
	}
	@test -f "$(QUESTIONS)" || { \
		echo "Error: questions file $(QUESTIONS) not found." >&2; \
		exit 2; \
	}
	@$(LORE_BENCHMARK_ENV) $(COMPOSE) build backend >&2
	@$(LORE_BENCHMARK_ENV) $(COMPOSE) run --rm \
		-v "$(abspath $(DIR)):/lore:ro" \
		-v "$(abspath $(QUESTIONS)):/questions.yaml:ro" \
		$(if $(ANSWERS),-v "$(abspath $(ANSWERS)):/answers.json:ro",) \
		migrate python -m smeshariki_ai.rag lore-benchmark /lore \
		--questions /questions.yaml --k "$(or $(K),5)" \
		$(if $(ANSWERS),--answers /answers.json,) \
		$(if $(filter 1,$(CONTEXT)),--context,) \
		$(if $(filter 1,$(EXPAND)),--expand,) \
		$(if $(filter 1,$(HYBRID)),--hybrid,) \
		--format "$(or $(FORMAT),text)"

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
