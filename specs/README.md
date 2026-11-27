# SDD records

Apply SDD to major features and public or shared contract changes as described in
[the SDD skill](../.agents/skills/sdd/SKILL.md). Keep `spec.md` within 80 lines,
`plan.md` within 200 lines, and `verification.md` within 30 lines.

Completed records are historical snapshots. Later changes can supersede their
requirements, decisions, and test results. For the current architecture and
contracts, start with [the architecture catalogue](../docs/README.md) and its
component pages. The registry in [status.yaml](status.yaml) tracks retained
records.

Earlier versions of condensed records and retired cosmetic histories remain in
Git. For example, run `git show 5af56b5:specs/changes/<change-id>/spec.md`
from the repository root to inspect a record as it existed before this cleanup.
