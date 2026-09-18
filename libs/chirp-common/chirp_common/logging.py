from __future__ import annotations

import logging
import sys
from typing import Any

try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:# pragma: no cover - older python-json-logger
    from pythonjsonlogger.jsonlogger import JsonFormatter

from chirp_common import context

_CONFIGURED = False

class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in context.log_fields().items():
            setattr(record, key, value)
        return True

class _Formatter(JsonFormatter):
    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["level"] = record.levelname.lower()
        log_record["logger"] = record.name
        log_record.pop("taskName", None)

def configure_logging(service_name: str, level: str = "INFO", *, json: bool = True) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    if json:
        handler.setFormatter(
            _Formatter("%(asctime)s %(level)s %(name)s %(message)s", timestamp=True)
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")
        )
    handler.addFilter(_ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").propagate = True

    logging.LoggerAdapter(root, {"service": service_name})
    root.info("logging configured", extra={"service": service_name})
    _CONFIGURED = True

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
