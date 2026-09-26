"""Safe, structured application events and request-local log context."""

import asyncio
import json
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["human", "json"]


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: LogLevel = "INFO"
    format: LogFormat = "human"


_CONTEXT_NAMES = ("request_id", "dialog_id", "call_id", "tool_call_id")
_CONTEXT = {name: ContextVar[str | None](name, default=None) for name in _CONTEXT_NAMES}
_SAFE_FIELDS = frozenset(
    {
        "started_at",
        "duration_ms",
        "outcome",
        "method",
        "route",
        "status_code",
        "iteration",
        "iterations",
        "history_size",
        "max_iterations",
        "result_type",
        "tool_name",
        "tool_status",
        "reason",
        "error_type",
        "model",
        "message_count",
        "tool_count",
        "time_to_first_token_ms",
        "usage_available",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    }
)
_BASE_FIELDS = ("timestamp", "level", "logger", "event", *_CONTEXT_NAMES)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@contextmanager
def bind_context(**values: str | None) -> Iterator[None]:
    invalid = values.keys() - _CONTEXT.keys()
    if invalid:
        raise ValueError("Unsupported log context field")
    tokens = [(name, _CONTEXT[name].set(value)) for name, value in values.items()]
    try:
        yield
    finally:
        for name, token in reversed(tokens):
            _CONTEXT[name].reset(token)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    invalid = fields.keys() - _SAFE_FIELDS - _CONTEXT.keys()
    if invalid:
        raise ValueError("Unsupported log event field")
    if not logger.isEnabledFor(level):
        return
    context = {name: _CONTEXT[name].get() for name in _CONTEXT_NAMES}
    for name in _CONTEXT_NAMES:
        if name in fields:
            context[name] = fields.pop(name)
    values = {**context, **fields}
    details = " ".join(
        f"{name}={value}" for name, value in values.items() if value is not None
    )
    logger.log(
        level,
        f"{event} {details}" if details else event,
        extra={"event": event, "log_fields": values, **values},
    )


class EventFormatter(logging.Formatter):
    def __init__(self, output_format: LogFormat) -> None:
        super().__init__()
        self.output_format = output_format

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", record.getMessage().split(" ", 1)[0])
        fields = getattr(record, "log_fields", {})
        result: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": event,
            **{name: fields.get(name) for name in _CONTEXT_NAMES},
        }
        result.update(
            {name: value for name, value in fields.items() if name in _SAFE_FIELDS}
        )
        if self.output_format == "json":
            return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        return " ".join(
            f"{name}={json.dumps(value, ensure_ascii=False) if isinstance(value, str) else value}"
            for name, value in result.items()
            if value is not None or name in _BASE_FIELDS[:4]
        )


def configure_logging(config: LoggingConfig) -> None:
    app_logger = logging.getLogger("smeshariki_ai")
    for handler in tuple(app_logger.handlers):
        if getattr(handler, "_smeshariki_handler", False):
            app_logger.removeHandler(handler)
            handler.close()
    handler = logging.StreamHandler(sys.stdout)
    handler._smeshariki_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(EventFormatter(config.format))
    app_logger.addHandler(handler)
    app_logger.setLevel(getattr(logging, config.level))
    app_logger.propagate = False
    # LiteLLM has its own handler and may format upstream payloads itself.
    # The adapter emits the safe metadata needed for diagnosing its failures.
    logging.getLogger("LiteLLM").disabled = True


class RequestLogMiddleware:
    """Measure an HTTP request until its final ASGI body, including SSE streams."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("smeshariki_ai.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope["path"] == "/api" or scope["path"].startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        started_at = utc_now()
        started = time.monotonic()
        scope.setdefault("state", {})["request_id"] = request_id
        status_code = 500
        response_started = False
        failure_type: str | None = None
        finished = False

        def route_fields() -> dict[str, Any]:
            route = scope.get("route")
            path_params = scope.get("path_params", {})
            raw_dialog_id = path_params.get("dialog_id")
            try:
                dialog_id = str(UUID(str(raw_dialog_id))) if raw_dialog_id else None
            except ValueError:
                dialog_id = None
            return {
                "route": getattr(route, "path", None),
                "dialog_id": dialog_id,
            }

        def finish(outcome: str) -> None:
            nonlocal finished
            if finished:
                return
            finished = True
            log_event(
                self.logger,
                logging.ERROR if outcome == "failed" else logging.INFO,
                f"http.request.{outcome}",
                method=scope["method"],
                status_code=status_code,
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome=outcome,
                error_type=failure_type,
                **route_fields(),
            )

        async def send_with_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        (b"x-request-id", request_id.encode("ascii")),
                    ],
                }
            await send(message)
            if message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                finish(
                    "failed"
                    if failure_type is not None or status_code >= 500
                    else "completed"
                )

        with bind_context(request_id=request_id):
            log_event(
                self.logger,
                logging.INFO,
                "http.request.started",
                method=scope["method"],
                started_at=started_at,
            )
            try:
                await self.app(scope, receive, send_with_id)
            except asyncio.CancelledError:
                finish("cancelled")
                raise
            except Exception as error:
                failure_type = type(error).__name__
                if not response_started:
                    await send_with_id(
                        {
                            "type": "http.response.start",
                            "status": 500,
                            "headers": [(b"content-type", b"application/json")],
                        }
                    )
                await send_with_id(
                    {
                        "type": "http.response.body",
                        "body": b'{"detail":"Internal server error."}'
                        if status_code == 500
                        else b"",
                        "more_body": False,
                    }
                )
            finally:
                if not finished:
                    finish("cancelled")
