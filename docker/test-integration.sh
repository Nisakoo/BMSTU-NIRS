#!/bin/sh
# Run the backend test suite against disposable PostgreSQL and Redis.
# Usage: make test-integration [PYTEST_ARGS="<pytest arguments>"]
set -u

PROJECT=smeshariki-ai-test
COMPOSE_FILE=docker/compose.test.yaml

compose() {
	docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

cleanup() {
	compose down -v --remove-orphans >/dev/null 2>&1
}

if ! docker info >/dev/null 2>&1; then
	echo "Error: Docker is not available. Start Docker and retry." >&2
	exit 1
fi

# Remove leftovers of an interrupted run before starting.
cleanup

trap 'status=$?; trap - EXIT; cleanup; exit "$status"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if ! compose up -d --wait --wait-timeout 120 >&2; then
	echo "Error: failed to start the test environment ($PROJECT)." >&2
	exit 1
fi

postgres_address=$(compose port postgres 5432) || exit 1
redis_address=$(compose port redis 6379) || exit 1

TEST_DATABASE_URL="postgresql+asyncpg://test:test@${postgres_address}/test"
TEST_REDIS_URL="redis://${redis_address}/0"
export TEST_DATABASE_URL TEST_REDIS_URL

set -f
# shellcheck disable=SC2086 # PYTEST_ARGS is split into pytest arguments.
uv run --project backend --locked pytest ${PYTEST_ARGS:-backend}
