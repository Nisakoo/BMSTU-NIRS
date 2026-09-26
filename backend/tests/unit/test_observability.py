import json
import logging
from io import StringIO

from smeshariki_ai.observability import (
    EventFormatter,
    LoggingConfig,
    bind_context,
    configure_logging,
    log_event,
)


def test_json_and_human_formats_share_safe_fields() -> None:
    logger = logging.getLogger("smeshariki_ai.test.observability")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    output = StringIO()
    handler = logging.StreamHandler(output)
    logger.addHandler(handler)
    try:
        with bind_context(request_id="request-1", dialog_id="dialog-1"):
            handler.setFormatter(EventFormatter("json"))
            log_event(
                logger,
                logging.INFO,
                "http.request.completed",
                method="POST",
                duration_ms=1.25,
                status_code=202,
            )
            handler.setFormatter(EventFormatter("human"))
            log_event(logger, logging.INFO, "http.request.completed", duration_ms=2.5)
        log_event(logger, logging.INFO, "dialog.created")
    finally:
        logger.removeHandler(handler)

    json_line, human_line, unbound_line = output.getvalue().splitlines()
    record = json.loads(json_line)
    assert record["timestamp"].endswith("Z")
    assert record["request_id"] == "request-1"
    assert record["dialog_id"] == "dialog-1"
    assert record["call_id"] is None
    assert record["duration_ms"] == 1.25
    assert record["status_code"] == 202
    assert 'request_id="request-1"' in human_line
    assert "duration_ms=2.5" in human_line
    assert "request-1" not in unbound_line


def test_configure_logging_replaces_own_handler_and_keeps_root_level() -> None:
    app_logger = logging.getLogger("smeshariki_ai")
    root = logging.getLogger()
    root_level = root.level

    configure_logging(LoggingConfig(level="DEBUG", format="json"))
    configure_logging(LoggingConfig(level="WARNING", format="human"))

    assert app_logger.level == logging.WARNING
    assert (
        len(
            [h for h in app_logger.handlers if getattr(h, "_smeshariki_handler", False)]
        )
        == 1
    )
    assert root.level == root_level
    assert logging.getLogger("LiteLLM").disabled


def test_warning_level_filters_info_without_changing_third_party_loggers() -> None:
    app_logger = logging.getLogger("smeshariki_ai")
    third_party = logging.getLogger("other_library")
    third_party_level = third_party.level
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(EventFormatter("json"))
    app_logger.addHandler(handler)
    try:
        configure_logging(LoggingConfig(level="WARNING", format="json"))
        log_event(app_logger, logging.INFO, "dialog.created")
        log_event(
            app_logger,
            logging.WARNING,
            "dialog.subscription.closed",
            reason="queue_overflow",
        )
    finally:
        app_logger.removeHandler(handler)

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [record["event"] for record in records] == ["dialog.subscription.closed"]
    assert third_party.level == third_party_level
