# Modular backend and in-process RAG tools

## Context and decision drivers

The application needs an agent that can consult structured knowledge and lore
while serving chat requests. Keep the agent independent of HTTP, support a
replaceable LLM provider, and operate a manageable local deployment.

## Options considered

- Run API, agent runtime, application services, and RAG in a modular backend.
  Internal interfaces separate responsibilities while calls stay in process.
- Deploy the agent and RAG as separate services. This allows independent
  deployment and scaling, but adds network contracts, service operations,
  failure modes, and coordination to the current deployment.

## Decision

Use a modular backend. The application service invokes the transport-independent
agent, which calls registered tools when needed. RAG indexing and retrieval
remain backend responsibilities, with PostgreSQL as their storage. Provider and
storage interfaces keep infrastructure choices outside the agent runtime.

The Svelte frontend consumes the same-origin HTTP and SSE interfaces. Its
TypeScript modules own browser state and presentation. Authorization, dialog
ownership and access to the agent and storage remain in the backend.

## Consequences

The deployment and tool-call path remain simpler, and modules can be tested
through their interfaces. Agent, API, and RAG share deployment and process
resources. Independent scaling or fault isolation would require a later
architectural change.

## Confirmation

Review module dependencies and bootstrap wiring when changing these boundaries.
Run affected agent, RAG, and integration contract tests when their code or
contracts change. Check the Compose topology for deployment changes.

## References

- [Frontend modules and state](../../frontend/README.md)
- [Architecture map](../README.md)
- [Agent architecture](../agent.md)
- [RAG architecture and tools](../rag.md)
- [RAG architecture specification](../../specs/changes/rag-architecture/spec.md)
