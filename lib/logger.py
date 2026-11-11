
import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Format log records as structured JSON."""

    RESERVED_FIELDS = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }

    def format(self, record):
        log_data = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include custom structured fields passed through `extra`.
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_FIELDS and not key.startswith("_"):
                log_data[key] = value

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


def configure_logging(level=logging.INFO):
    """Configure the root logger with JSON output."""

    root_logger = logging.getLogger()

    if not any(
        getattr(handler, "_flowmesh_handler", False)
        for handler in root_logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._flowmesh_handler = True
        root_logger.addHandler(handler)

    root_logger.setLevel(level)


def get_logger(name):
    """Return a named logger using FlowMesh logging configuration."""

    configure_logging()
    return logging.getLogger(name)
