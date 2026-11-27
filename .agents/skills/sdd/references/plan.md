# Plan

Start only after specification approval. Set `in-progress` through the status CLI.

1. Inspect the affected code, contracts, existing tests and direct consumers. Map downstream effects and infrastructure boundaries before choosing checks or new cases.
2. Identify the smallest set of tests that proves each changed behavior and affected contract. Include real adapter integration when its boundary changes. Exclude independent modules. Widen the scope when a boundary is uncertain.
3. Add test cases only for distinct core behavior, contracts or material failure risks that existing tests do not cover. Use review for prose and formatting with no behavior or contract change.
4. Write `plan.md` in at most 200 physical lines including blanks. Order small verifiable tasks and record affected files, criteria and exact checks, including existing tests and any necessary new cases.
5. Present the plan, set `in-queue` through the CLI while waiting and obtain explicit user approval before implementation.
