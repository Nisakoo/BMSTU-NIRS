---
name: sdd
description: Guides major product or cross-module features and public or shared contract changes through Specify, Plan, Implement and Verify.
---

# SDD

Use SDD for substantial product-wide or cross-module features and changes to public or shared contracts, including HTTP, SSE, persisted data and cross-module interfaces. Local fixes and visual changes with no shared contract change use the direct workflow in `AGENTS.md`.

Follow `specify -> plan -> implement -> verify`. Read `specs/status.yaml` before selecting a change. Create, update or delete registry entries only with the CLI in [status](references/status.md). Read the applicable stage instructions before starting it.

- [specify](references/specify.md), using the [template](references/spec-template.md)
- [plan](references/plan.md)
- [implement](references/implement.md)
- [verify](references/verify.md)

Obtain explicit user approval before moving from specify to plan and from plan to implement. Mark a change `done` only after successful verify. Each physical line counts, including blank lines. `spec.md` is limited to 80 lines, `plan.md` to 200 and `verification.md` to 30. Keep artifacts concise and link to existing contracts instead of duplicating them.
