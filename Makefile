SHELL := /bin/sh

COMPOSE_FILE := docker/compose.yaml
ENV_FILE := docker/.env

.PHONY: help run test

help:
	@echo "Available commands:"
	@echo "  make run   Run the backend and its infrastructure"
	@echo "  make test  Run all configured project tests"

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

test:
	@echo "Error: Python product tests are not configured yet." >&2
	@exit 1
