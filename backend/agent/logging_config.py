"""
Structured logging configuration for AI Revenue Recovery Agent.

Provides:
- Correlation ID tracking across request lifecycle
- JSON-formatted logs for easy parsing
- Context propagation through all components
"""

import logging
import json
import sys
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import uuid4
from contextvars import ContextVar

# Context variable for correlation ID (thread-safe)
_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

class CorrelationIdFilter(logging.Filter):
    """Add correlation_id to log records."""

    def filter(self, record):
        record.correlation_id = _correlation_id.get() or 'no-correlation-id'
        return True

class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'correlation_id': getattr(record, 'correlation_id', 'no-correlation-id'),
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)

def setup_logging(json_format: bool = False):
    """
    Configure structured logging for the application.

    Args:
        json_format: If True, use JSON formatting. Otherwise, use human-readable format.
    """

    # Create logger
    logger = logging.getLogger('recovery_agent')
    logger.setLevel(logging.INFO)

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    # Add correlation ID filter
    handler.addFilter(CorrelationIdFilter())

    # Choose formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '[%(asctime)s] [%(correlation_id)s] [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

def set_correlation_id(correlation_id: str):
    """Set correlation ID for current context."""
    _correlation_id.set(correlation_id)

def get_correlation_id() -> Optional[str]:
    """Get correlation ID from current context."""
    return _correlation_id.get()

def generate_correlation_id() -> str:
    """Generate new correlation ID."""
    return f"req_{uuid4().hex[:16]}"

def get_logger(name: str = 'recovery_agent'):
    """
    Get logger instance with correlation ID support.

    Usage:
        from agent.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Processing transaction", extra={'extra_fields': {'transaction_id': tx_id}})
    """
    return logging.getLogger(name)

def log_with_context(logger: logging.Logger, level: str, message: str, **context):
    """
    Log message with additional context fields.

    Args:
        logger: Logger instance
        level: Log level ('info', 'warning', 'error', 'debug')
        message: Log message
        **context: Additional context fields to include in log
    """
    log_func = getattr(logger, level.lower())
    log_func(message, extra={'extra_fields': context})

# Initialize default logger
default_logger = setup_logging(json_format=False)
