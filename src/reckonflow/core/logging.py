"""I set up structured logging with structlog

I emit field-rich logs so I can search by request id, level, and timestamp later
"""

import logging
import sys

import structlog


def setup_logging(*, debug: bool = False) -> None:
    """I configure console-friendly logs in debug and JSON logs otherwise"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer()
        if debug
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """I return a named structured logger"""
    # structlog types get_logger as Any; I narrow it once here so every caller
    # gets real completion and mypy --strict stays happy
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
