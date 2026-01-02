"""Structured JSON logging configuration for Reasoner.

Provides:
- JSON-formatted log output with structured fields
- Request ID correlation via contextvars
- Dual output (console + file)
- Secret redaction
- Log rotation
"""

import json
import logging
import logging.handlers
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ============================================================================
# Context Variables for Request Correlation
# ============================================================================

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
component_var: ContextVar[Optional[str]] = ContextVar("component", default=None)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID for the current async context."""
    request_id_var.set(request_id)


def set_component(component: str) -> None:
    """Set the component name for the current context."""
    component_var.set(component)


# ============================================================================
# Secret Redaction
# ============================================================================

# Patterns to redact (compiled for performance)
SECRET_PATTERNS = [
    (re.compile(r'(api[_-]?key)["\']?\s*[:=]\s*["\']?([^"\'\s,}]{8,})', re.I), r'\1=***REDACTED***'),
    (re.compile(r'(bearer\s+)([a-zA-Z0-9._-]{20,})', re.I), r'\1***REDACTED***'),
    (re.compile(r'(authorization)["\']?\s*[:=]\s*["\']?([^"\'\s,}]{20,})', re.I), r'\1=***REDACTED***'),
    (re.compile(r'(token)["\']?\s*[:=]\s*["\']?([^"\'\s,}]{20,})', re.I), r'\1=***REDACTED***'),
    (re.compile(r'(password)["\']?\s*[:=]\s*["\']?([^"\'\s,}]{4,})', re.I), r'\1=***REDACTED***'),
    (re.compile(r'(secret)["\']?\s*[:=]\s*["\']?([^"\'\s,}]{8,})', re.I), r'\1=***REDACTED***'),
    # Email addresses (PII)
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '***EMAIL***'),
]


def redact_secrets(text: str) -> str:
    """Redact sensitive information from log messages."""
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


# ============================================================================
# JSON Formatter
# ============================================================================

class JSONFormatter(logging.Formatter):
    """JSON log formatter with structured fields and secret redaction."""

    # Fields to exclude from extra (internal logging fields)
    INTERNAL_FIELDS = {
        "name", "msg", "args", "created", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs", "pathname",
        "process", "processName", "relativeCreated", "stack_info",
        "thread", "threadName", "exc_info", "exc_text", "message",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Build structured log entry
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": redact_secrets(record.getMessage()),
            "logger": record.name,
        }

        # Add request ID from context
        request_id = request_id_var.get()
        if request_id:
            log_entry["request_id"] = request_id

        # Add component from context
        component = component_var.get()
        if component:
            log_entry["component"] = component

        # Add error info if exception
        if record.exc_info and record.exc_info[0]:
            log_entry["error"] = {
                "type": record.exc_info[0].__name__,
                "message": redact_secrets(str(record.exc_info[1])) if record.exc_info[1] else "",
                "traceback": redact_secrets(self.formatException(record.exc_info)),
            }

        # Add extra fields (avoid internal logging fields)
        for key, value in record.__dict__.items():
            if key not in self.INTERNAL_FIELDS and not key.startswith("_"):
                if isinstance(value, str):
                    log_entry[key] = redact_secrets(value)
                else:
                    log_entry[key] = value

        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter with colors and secret redaction."""

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console output."""
        color = self.COLORS.get(record.levelname, "")
        request_id = request_id_var.get() or "-"
        component = component_var.get() or record.name.split(".")[-1]

        # Format: timestamp level [request_id] component: message
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        message = redact_secrets(record.getMessage())

        prefix = f"{color}{timestamp} {record.levelname:8}{self.RESET}"
        req_id_short = request_id[:8] if request_id != "-" else "-"
        context = f"[{req_id_short:>8}] {component:15}"

        formatted = f"{prefix} {context} {message}"

        # Add duration if present
        if hasattr(record, "duration_ms"):
            formatted += f" ({record.duration_ms}ms)"

        # Add exception if present
        if record.exc_info:
            formatted += f"\n{redact_secrets(self.formatException(record.exc_info))}"

        return formatted


# ============================================================================
# Logging Setup
# ============================================================================

_logging_configured = False


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "./logs",
    log_file: str = "app.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    enable_console: bool = True,
    enable_file: bool = True,
) -> None:
    """Configure structured logging for the application.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory for log files.
        log_file: Name of the log file.
        max_bytes: Maximum size per log file before rotation.
        backup_count: Number of rotated files to keep.
        enable_console: Whether to output to console.
        enable_file: Whether to output to file.
    """
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    # Ensure log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Get root logger and clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Console handler (human-readable)
    if enable_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(ConsoleFormatter())
        console_handler.setLevel(getattr(logging, log_level.upper()))
        root_logger.addHandler(console_handler)

    # File handler (JSON, rotating)
    if enable_file:
        file_path = log_path / log_file
        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter())
        file_handler.setLevel(logging.DEBUG)  # Capture all levels to file
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Use this instead of logging.getLogger() to ensure consistent setup.
    """
    return logging.getLogger(name)
