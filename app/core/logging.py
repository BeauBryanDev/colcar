"""Logging setup for the backend.
"""

from __future__ import annotations

import logging
import logging.config
import sys
from typing import Any

from app.core.config import Settings, get_settings

# Loggers that are noisy at INFO and rarely tell us anything we want.
_NOISY: dict[str, str] = {
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "urllib3": "WARNING",
    "qdrant_client": "WARNING",
    "sentence_transformers": "WARNING",
    "transformers": "WARNING",
    "FlagEmbedding": "WARNING",
    "filelock": "WARNING",
    "huggingface_hub": "WARNING",
    # uvicorn.access duplicates our own request logging; keep it off by default.
    "uvicorn.access": "WARNING",
}

_CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)-28s %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_configured = False

# Do not shows secret values in the log, even if the log level is DEBUG.
class RedactingFilter(logging.Filter):
    """Replace known secret values with `***` anywhere in a log record.
    """

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        # Short values would match everywhere and mangle unrelated output.
        self._secrets = [s for s in secrets if s and len(s) >= 8]

    def _scrub(self, value: Any) -> Any:
        
        if not isinstance(value, str):
            return value
        
        for secret in self._secrets:
            
            if secret in value:
                
                value = value.replace(secret, "***REDACTED***")
                
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        
        record.msg = self._scrub(record.msg)
        
        if record.args:
            
            if isinstance(record.args, dict):
                
                record.args = {k: self._scrub(v) for k, v in record.args.items()}
                
            else:
                
                record.args = tuple(self._scrub(a) for a in record.args)
                
        return True


def _secret_values(settings: Settings) -> list[str]:
    """Every secret the app knows about, unwrapped for substring matching."""
    return [
        settings.anthropic_api_key.get_secret_value(),
        settings.qdrant_api_key.get_secret_value(),
    ]


def setup_logging(settings: Settings | None = None, *, force: bool = False) -> None:
    """Configure root logging. Idempotent unless `force=True`."""
    global _configured
    if _configured and not force:
        return

    s = settings or get_settings()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(RedactingFilter(_secret_values(s)))

    root = logging.getLogger()
    root.handlers.clear()  # uvicorn installs its own; ours replaces it
    root.addHandler(handler)
    root.setLevel(s.log_level.upper())

    for name, level in _NOISY.items():
        
        logging.getLogger(name).setLevel(level)

    # uvicorn's own loggers propagate to root so everything shares our format
    # and, importantly, our redaction filter.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    _configured = True
    logging.getLogger(__name__).info(
        "Logging ready: level=%s environment=%s", s.log_level.upper(), s.environment
    )


def get_logger(name: str) -> logging.Logger:
    """Convenience for modules that would rather not import logging directly."""
    return logging.getLogger(name)
