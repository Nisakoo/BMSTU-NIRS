# smeshariki-ai

## Project map and flow

- `frontend/` contains the vanilla JavaScript chat, login and admin pages. Vite builds them and Nginx serves them.
- `backend/src/smeshariki_ai/api/` exposes HTTP and SSE. `application/` coordinates dialog requests and events.
- `agent/` runs the model and tool loop. `agent/providers/` adapts LLM providers through an internal interface.
- `dialogs/`, `auth/`, `admin/`, and `speech/` own their respective domain services and contracts.
- `rag/` owns knowledge ingestion, indexing and retrieval. RAG is an agent tool inside the backend.
- `db/` and `cache/` provide PostgreSQL, migration and Redis adapters. `config.py` loads configuration at the process boundary. `bootstrap.py` assembles dependencies.
- `docker/` contains Compose files, Dockerfiles, environment examples and container scripts. Caddy routes `/api` to the backend and other traffic to Nginx.
- `docs/README.md` indexes architecture and contracts. `specs/` contains SDD changes. `docs/adr/` records decisions.

A browser sends same-origin HTTP requests through Caddy. Use SSE for streamed responses unless a specification requires another transport. The API calls application services, which coordinate dialog history, the agent and its tools. The agent streams results via SSE. The backend owns access to LLMs, PostgreSQL, Redis and object storage.

## Mandatory rules

- The project and Python distribution are `smeshariki-ai`. The import package is `smeshariki_ai`.
- Keep the backend a modular monolith. Keep HTTP separate from domain services, inject infrastructure dependencies and use the LLM provider and tool interfaces.
- Use PostgreSQL for RAG storage and run ingestion or reindexing as backend commands. Do not introduce a separate public RAG service or vector database without an agreed architecture change.
- Only `load_config` reads process environment. Components receive their own configuration through the composition root. Docker Compose loads `docker/.env`.
- Keep deployment files under `docker/`. Run documented commands from the repository root or specify the path under `docker/`.
- Never commit secrets or plaintext private corpus data. Keep `docker/.env` and `data/` ignored, commit only `docker/.env.example` as the environment template and `encrypted/data.enc` as the private corpus. Tests and examples use synthetic data. Use `.agents/skills/data-crypt/SKILL.md` for the encrypted corpus and do not ask for or enter the team passphrase.
- Preserve dialog ownership and authorization across all entry points. Return the same response for foreign and unknown dialogs, including for administrators. Keep tokens in HttpOnly cookies and fail closed on authentication infrastructure errors.
- Never log user or model text, tool payloads, credentials, or external exception messages. Insert dynamic content in the frontend as text.
- Use `uv` for Python environments, dependencies and commands. Use Make targets as the standard project entry points. Preserve `make run`, `make migrate`, `make test`, `make test-integration`, `make lint`, `make format`, `make data-encrypt` and `make data-decrypt`.
- Update relevant architecture and contract documentation in `docs/` when a component, boundary or contract changes, and update `docs/README.md` when the global map changes. If documentation conflicts, the latest agreed specification and successful verification govern. Consult them when changing existing behavior.
- Commit titles follow Conventional Commits, for example `fix(auth): reject expired sessions`. Mark breaking changes with `!` and a `BREAKING CHANGE` footer.

## Change workflow

Use `.agents/skills/sdd/SKILL.md` for substantial product-wide or cross-module features and changes to public or shared contracts, including HTTP, SSE, persisted data and cross-module interfaces. Obtain explicit approval at the specification and plan gates. Edit `specs/status.yaml` only through the SDD status CLI. Limit each `spec.md` to 80 lines, `plan.md` to 200 and `verification.md` to 30.

Implement local fixes, small UI adjustments and other contained changes directly. Inspect the affected implementation and contracts first, then make the change and verify its consequences. Preserve existing behavior outside the requested scope.

Record durable architectural decisions in `docs/adr/`. Use MADR for significant trade-offs or architectural boundaries that need context, alternatives and consequences. Use a concise Y-statement for other durable decisions. Follow the ADR guidance in that directory.

## Acceptance and verification

- A change is complete when the requested behavior and affected contracts are verified, relevant documentation is updated, and any remaining limitation is reported.
- Run automated tests when executable code, test code, runtime configuration or behavioral contracts change, including a change in the meaning of a documented supported guarantee. For prose or formatting changes with no behavior or contract change, review the diff and links without running tests. Verify purely visual acceptance directly and run the closest tests when executable behavior changes.
- Identify the changed behavior and its dependencies. Run tests for the changed module and every consumer or entry point that can observe the change. Include API or SSE client tests when wire format or observable behavior changes. Include affected shared authentication, configuration, persistence or protocol consumers and real infrastructure adapter tests when those boundaries change.
- Do not run suites for independent modules whose behavior and contracts cannot be affected. If a boundary is uncertain, widen the selection. Use the full suite for cross-cutting changes or when the affected boundary cannot be determined.
- Select existing tests before adding new ones. Add tests for distinct core flows, contracts or material failure risks. Cover meaningful outcome boundaries and avoid tests tied only to visual details or implementation trivia. Use deterministic fakes for unit tests and real infrastructure for adapter integration tests.
- Examples from the repository root include `node --test frontend/tests/ui.test.js`, `uv run --project backend --locked pytest backend/tests/unit/agent/test_runtime.py`, and `make test-integration PYTEST_ARGS="backend/tests/integration/rag"`. `make test` runs the broader local suite and can skip infrastructure tests when services are absent. `make test-integration` supplies temporary PostgreSQL and Redis.
