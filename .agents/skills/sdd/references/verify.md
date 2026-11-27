# Verify

Set `in-progress` through the status CLI if needed. Match every acceptance criterion to evidence from a behavior test, an integration check or review. Run the checks selected for the final change and impacted consumers. Include infrastructure checks where applicable and document skipped checks and coverage gaps. Review the final diff, scope and documentation.

Record commands, results and counts where available, failures, skips and known gaps in `verification.md`, at most 30 physical lines including blanks. Mark `done` through the CLI only when all acceptance criteria are verified. Otherwise fix the issue and repeat verification, or set `in-queue` if work stops.
