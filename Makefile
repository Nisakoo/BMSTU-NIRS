SHELL := /bin/sh

UV ?= uv
UV_CACHE_DIR ?= /tmp/smeshariki-ai-uv-cache
UV_LINK_MODE ?= copy

export UV_CACHE_DIR
export UV_LINK_MODE

.PHONY: help run test

help:
	@echo "Available commands:"
	@echo "  make run   Run the base RAG CLI"
	@echo "  make test  Run all Python product tests"

run:
	@$(UV) run --project backend python -m smeshariki_ai.rag

test:
	@$(UV) run --project backend pytest -c backend/pyproject.toml backend/tests
