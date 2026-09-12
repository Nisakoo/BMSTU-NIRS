---
name: sdd
description: Guides project changes through Specify, Plan, Implement, and Verify. Use when creating a feature, changing behavior, fixing a bug, or making an architectural change.
---

# SDD

Веди разработку последовательно:

```text
specify -> plan -> implement -> verify
```

Перед началом определи текущий этап и прочитай только соответствующую инструкцию:

- [specify](references/specify.md) — сформулировать и согласовать требования;
- [plan](references/plan.md) — подготовить и согласовать план;
- [implement](references/implement.md) — реализовать план небольшими проверяемыми шагами;
- [verify](references/verify.md) — доказать соответствие спецификации.

Для новой спецификации используй [шаблон](references/spec-template.md).

Не переходи от `specify` к `plan` и от `plan` к `implement` без явного одобрения пользователя. Не называй работу выполненной до успешного `verify`. Для изменений Python-кода продукта также требуется успешный `make test`. Не добавляй автоматические тесты, проверяющие только структуру каталогов, README или служебные файлы.

Подход адаптирован из [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills): спецификация до кода, небольшие вертикальные задачи, TDD и обязательная проверка результата.
