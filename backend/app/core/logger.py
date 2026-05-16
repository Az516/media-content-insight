"""Structured logging for the backend.

The module exposes two named loggers:

* :data:`logger` -- the application logger (``"app"``). General-purpose
  messages emitted from services, API handlers, and utilities go here.
* :data:`audit_logger` -- the audit-only logger (``"audit"``). It records
  one JSON-line entry per task lifecycle event as required by requirement
  20.5 (``{keyword, started_at, finished_at, note_count, status}``).

Both loggers emit JSON-line records to ``stderr`` via a custom
:class:`JSONLineFormatter` so that downstream tooling can ingest the output
without ad-hoc parsing. Log levels follow the standard
:mod:`logging` conventions.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Mapping


# Standard set of attributes carried by every :class:`logging.LogRecord` so
# that we can detect "extra" fields supplied by callers without hard-coding
# them all.
_RESERVED_LOG_RECORD_ATTRS = frozenset(
    {
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
        "asctime",
        "message",
        "taskName",
    }
)


class JSONLineFormatter(logging.Formatter):
    """Format log records as a single JSON line.

    Any keyword argument supplied to a logger call via ``extra=`` is
    surfaced verbatim in the resulting JSON object, which makes the format
    suitable for both regular application logs and the audit log.
    """

    def format(self, record: logging.LogRecord) -> str:
        # ``record.created`` is a UNIX timestamp; convert to UTC ISO-8601 to
        # keep records timezone-aware and easy to correlate with database
        # ``started_at`` / ``finished_at`` values.
        ts = (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Surface any user-supplied ``extra`` fields. The ``logging`` module
        # smuggles them onto the record's ``__dict__``; we copy anything that
        # is not part of the reserved core attribute set.
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_ATTRS or key.startswith("_"):
                continue
            payload[key] = _to_jsonable(value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False)


def _to_jsonable(value: Any) -> Any:
    """Best-effort conversion of arbitrary values to JSON-serialisable types."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_jsonable(v) for v in value]
    return str(value)


def _ensure_handler(target: logging.Logger) -> None:
    """Attach a JSON-line stderr handler to ``target`` if it has none."""
    if target.handlers:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JSONLineFormatter())
    target.addHandler(handler)
    # Each named logger manages its own handlers; do not double-emit by
    # bubbling up to the root logger.
    target.propagate = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the application and audit loggers.

    Calling this function more than once is safe; handlers are only attached
    when the target logger has none already.
    """
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    _ensure_handler(app_logger)

    audit = logging.getLogger("audit")
    # Audit records are deliberately emitted at INFO level regardless of the
    # application log level so that they are never accidentally suppressed
    # by raising the application log level.
    audit.setLevel(logging.INFO)
    _ensure_handler(audit)


# Configure on import so that simply doing ``from app.core.logger import
# logger`` gives the caller a ready-to-use logger.
configure_logging()


#: Application-wide logger used for general informational and error output.
logger: logging.Logger = logging.getLogger("app")


#: Audit-only logger used for the ``{keyword, started_at, finished_at,
#: note_count, status}`` task lifecycle records mandated by requirement 20.5.
audit_logger: logging.Logger = logging.getLogger("audit")
