# Implement

Start only after the specification and plan are approved. Set `in-progress` through the status CLI.

Implement the approved tasks in order and run their selected checks. When a distinct core behavior or material regression needs a new test, use RED -> GREEN -> REFACTOR. Reproduce failures and fix their cause. Add a regression test only when existing coverage would miss that failure and the case warrants a test under the project rules.

Run tests for changed executable code, tests, runtime configuration or behavioral contracts. Select impacted modules and consumers as described in `AGENTS.md`; do not run independent suites. Review prose and formatting changes without a behavior or contract change. If requirements change, return to specify. If work pauses before verify, set `in-queue` through the CLI. Do not mark `done` at this stage.
