import logging

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from smeshariki_ai.application import AgentService
from smeshariki_ai.bootstrap import (
    build_agent_service,
    configure_logging,
    create_application,
)
from smeshariki_ai.config import ApplicationConfig, load_config


def test_load_config_uses_defaults() -> None:
    config = load_config({})

    assert config == ApplicationConfig(
        agent_system_prompt="You are a helpful Smeshariki assistant.",
        agent_max_iterations=4,
    )


def test_load_config_reads_agent_environment() -> None:
    config = load_config(
        {
            "AGENT_SYSTEM_PROMPT": "Custom prompt",
            "AGENT_MAX_ITERATIONS": "2",
        }
    )

    assert config.agent_system_prompt == "Custom prompt"
    assert config.agent_max_iterations == 2


def test_load_config_rejects_invalid_iteration_limit() -> None:
    with pytest.raises(ValidationError):
        load_config({"AGENT_MAX_ITERATIONS": "0"})


def test_bootstrap_builds_service_and_fastapi_application() -> None:
    config = ApplicationConfig()

    service = build_agent_service(config)
    app = create_application(config)

    assert isinstance(service, AgentService)
    assert isinstance(app, FastAPI)
    assert app.title == "smeshariki-ai"
    assert isinstance(app.state.agent_service, AgentService)


def test_configure_logging_enables_application_info_events() -> None:
    application_logger = logging.getLogger("smeshariki_ai")
    original_level = application_logger.level
    application_logger.setLevel(logging.WARNING)

    try:
        configure_logging()
        assert application_logger.level == logging.INFO
    finally:
        application_logger.setLevel(original_level)


def test_main_exports_application() -> None:
    from smeshariki_ai.main import app

    assert isinstance(app, FastAPI)
