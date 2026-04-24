"""Logging bootstrap — wires structlog over the stdlib logging handlers so
every log emitter (structlog, logger.info, aiogram, uvicorn) produces a
uniform output format.

Behaviour:

* Development (LOG_LEVEL=DEBUG or non-production TTY): colourful
  ``ConsoleRenderer`` for human-friendly traces.
* Production (anything else): JSON lines, one event per line — ready for
  ingestion by Loki/Elastic/CloudWatch.

A correlation id is injected by ``app.bootstrap.correlation.correlation_id_var``
(set by telegram and web middleware). It appears on every log record under
``correlation_id`` so a single update can be traced across adapters.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.bootstrap.correlation import correlation_id_var


def _add_correlation_id(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    _ = logger, method_name
    cid = correlation_id_var.get()
    if cid:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


def configure_logging(level: str) -> None:
    """Configure both stdlib logging and structlog. Safe to call multiple
    times — the second call resets the configuration (useful for tests)."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    use_json = numeric_level > logging.DEBUG

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _add_correlation_id,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if use_json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # ``force=True``-like semantics without calling basicConfig: wipe existing
    # handlers and install ours so earlier basicConfig() calls don't leave a
    # second, unstructured handler behind.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Quiet uvicorn's access logger — it double-logs every request with its
    # own format and is unavoidably noisy in structured output.
    logging.getLogger("uvicorn.access").setLevel(max(logging.WARNING, numeric_level))


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Shortcut so callers can ``from app.bootstrap.logger import get_logger``
    without learning about structlog's factory API."""
    return structlog.get_logger(name) if name else structlog.get_logger()
