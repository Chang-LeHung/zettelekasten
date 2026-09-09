import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from time import gmtime

from ...config import settings

LOGGER_NAMESPACE = "zett"
LOG_FILE_NAME = "zett.log"
MAX_LOG_FILE_BYTES = 64 * 1024 * 1024
LOG_BACKUP_COUNT = 1
LOG_FORMAT = "%(asctime)sZ %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s"

_configuration_lock = Lock()
_configured_signature: tuple[Path, int, int, str] | None = None


class UTCFormatter(logging.Formatter):
    """Format timestamps in UTC so records remain comparable across environments."""

    converter = gmtime


def _level_number(level: str) -> int:
    """Resolve a configured level name and fall back to INFO for invalid values."""
    return logging.getLevelNamesMapping().get(level.upper(), logging.INFO)


def _close_handlers(logger: logging.Logger) -> None:
    """Remove and close handlers owned by the Zett logger during reconfiguration."""
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def configure_logging(
    log_directory: Path | None = None,
    *,
    max_bytes: int = MAX_LOG_FILE_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
    level: str | None = None,
) -> Path:
    """Configure idempotent console and size-based file logging for Zett.

    A backup count of one keeps exactly two possible files: the active log and
    one rotated predecessor. Optional limits make rotation behavior testable
    without changing production defaults.
    """
    global _configured_signature

    directory = (log_directory or settings.log_directory).expanduser().resolve()
    resolved_level = (level or settings.log_level).upper()
    signature = (directory, max_bytes, backup_count, resolved_level)
    log_path = directory / LOG_FILE_NAME
    with _configuration_lock:
        if _configured_signature == signature:
            return log_path
        directory.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(LOGGER_NAMESPACE)
        _close_handlers(logger)
        logger.setLevel(_level_number(resolved_level))
        logger.propagate = False

        formatter = UTCFormatter(
            fmt=LOG_FORMAT,
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        _configured_signature = signature
    return log_path


def uvicorn_log_config(level: str | None = None) -> dict[str, object]:
    """Build a Uvicorn logging configuration with Zett source locations."""
    configured_level = (level or settings.log_level).upper()
    if configured_level not in logging.getLevelNamesMapping():
        configured_level = "INFO"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "zett": {
                "()": "zett.infra.log.UTCFormatter",
                "fmt": LOG_FORMAT,
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            }
        },
        "handlers": {
            "default": {"class": "logging.StreamHandler", "formatter": "zett", "stream": "ext://sys.stderr"},
            "access": {"class": "logging.StreamHandler", "formatter": "zett", "stream": "ext://sys.stdout"},
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": configured_level, "propagate": False},
            "uvicorn.error": {"level": configured_level},
            "uvicorn.access": {"handlers": ["access"], "level": configured_level, "propagate": False},
        },
    }


def shutdown_logging() -> None:
    """Flush and close only handlers owned by the Zett logging component."""
    global _configured_signature

    with _configuration_lock:
        _close_handlers(logging.getLogger(LOGGER_NAMESPACE))
        _configured_signature = None


def get_logger(module_name: str) -> logging.Logger:
    """Return a namespaced logger whose handlers report the caller location.

    ``get_logger`` only selects the logger hierarchy. ``LOG_FORMAT`` uses the
    standard ``filename`` and ``lineno`` LogRecord attributes, so each emitted
    record points to the source call site rather than this factory function.
    """
    normalized_name = module_name.removeprefix("zett.").strip(".")
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{normalized_name}" if normalized_name else LOGGER_NAMESPACE)
