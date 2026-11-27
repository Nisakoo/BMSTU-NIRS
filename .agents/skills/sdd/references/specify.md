# Specify

1. Study the request, `AGENTS.md`, relevant code and existing contracts. Confirm that SDD applies.
2. Register a new change as `draft` through the status CLI. Reuse an existing entry when applicable.
3. Write `specs/changes/<change-id>/spec.md` using the template, within 80 physical lines including blanks. State the goal, scope, constraints, essential scenarios and observable acceptance criteria. Pair each criterion with its verification method, including existing tests or review where applicable. Do not implement tests at this stage.
4. Identify material assumptions and unresolved questions. Split independently verifiable capabilities when appropriate.
5. Present the specification and wait for explicit user approval. Keep it `draft` until approval, then set `in-queue` through the CLI.
