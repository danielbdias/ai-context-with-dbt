"""JSON logging with a per-request id.

Only explicitly passed fields are logged, so message bodies and passwords
cannot leak by accident.
"""

import json
import logging
import sys
from datetime import UTC, datetime

LOGGER_NAME = "web"


class JsonFormatter(logging.Formatter):
    """Render records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as JSON, merging fields passed via `extra`."""
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        return json.dumps(payload)


def configure_logging() -> logging.Logger:
    """Attach a JSON stdout handler to the `web` logger (idempotent)."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_event(event: str, **fields: object) -> None:
    """Log one structured event."""
    logging.getLogger(LOGGER_NAME).info(event, extra={"fields": fields})
