# Configuration at the composition root

In the context of configuring backend components, facing the need for explicit,
repeatable dependencies and component isolation, we decided to load configuration
at the process boundary and pass component-owned configuration through the
composition root, against letting each component read environment variables,
to make construction and tests deterministic, accepting that the root must wire
and validate the configuration required by each component.

References: [Configuration](../configuration.md), [bootstrap](../../backend/src/smeshariki_ai/bootstrap.py),
[configuration implementation](../../backend/src/smeshariki_ai/config.py),
[configuration specification](../../specs/changes/backend-config/spec.md).
