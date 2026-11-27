# Architecture decision records

ADRs record the rationale for durable architecture and engineering decisions.
The thematic documentation describes the current implementation and contracts.
SDD records agreed behavior, implementation sequence, and verification evidence
for major features and shared contracts. Link these artifacts where relevant.

Use MADR when a cross-module or hard-to-reverse decision has significant
trade-offs that need options and consequences explained. Use a Y-statement for
other durable architecture or engineering decisions. Routine cosmetic edits do
not need an ADR. Existing decisions need records when they are revisited, not as
a retrospective documentation requirement.

Give each record the next available numeric prefix and a descriptive filename.
When a decision changes, link to the new record. Keep the record concise and
cite relevant code, documentation, and SDD artifacts.

## Records

- [001 — Modular backend and in-process RAG tools](001-modular-backend.md) (MADR)
- [002 — Configuration at the composition root](002-configuration-composition-root.md) (Y-statement)
- [003 — Optional backend image dependencies](003-optional-backend-dependencies.md) (Y-statement)

## MADR template

```markdown
# <Title>

## Context and decision drivers

<Problem, constraints, and decision drivers>

## Options considered

- <Option and relevant trade-offs>
- <Alternative and relevant trade-offs>

## Decision

<Chosen option and reasons>

## Consequences

<Benefits, costs, and risks>

## Confirmation

<How compliance or outcome will be checked>

## References

<Relevant documentation, code, and SDD links>
```

The format follows [MADR](https://adr.github.io/madr/decisions/adr-template.html).

## Y-statement template

```markdown
# <Title>

In the context of <situation>, facing <concern>, we decided for <choice> and
against <alternative>, to achieve <benefit>, accepting <consequence>.

References: <relevant documentation, code, and SDD links>
```

The format follows the [Y-statement approach](https://www.inf.usi.ch/sites/inf.usi.ch/files/storage/attachments/document/usi-guestlectureabbv11.pdf#page=19).
