import logging
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock

from ...config import settings

LOGGER_NAMESPACE = "zett"
LOG_FILE_NAME = "zett.log"
MAX_LOG_FILE_BYTES = 64 * 1024 * 1024
LOG_BACKUP_COUNT = 1
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s"

#: Human-readable wall-clock time; the offset is appended by the formatter.
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

#: Longest text fragment a log record carries when it previews message content.
LOG_PREVIEW_CHARS = 60

_configuration_lock = Lock()
_configured_signature: tuple[Path, int, int, str] | None = None


class LocalTimeFormatter(logging.Formatter):
    """Format timestamps in the host's local time with an explicit UTC offset.

    Records are read next to local wall-clock events, so the timestamp is local
    time rather than a UTC instant the reader has to convert. The ``±HH:MM``
    suffix keeps that choice unambiguous, so a log copied from another machine
    still says which zone produced it.
    """

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        moment = datetime.fromtimestamp(record.created).astimezone()
        stamp = moment.strftime(datefmt or LOG_DATE_FORMAT)
        return f"{stamp}{_offset_suffix(moment)}"


#: Name this module's formatter had before it moved from UTC to local time.
#: uvicorn builds its log config in the parent process and resolves that config
#: by name in every reload or worker child, so a server started before the
#: rename keeps asking for this name until it restarts; without the alias that
#: child dies while configuring logging.
UTCFormatter = LocalTimeFormatter


def _offset_suffix(moment: datetime) -> str:
    """Render one datetime's UTC offset as ``+HH:MM`` or ``-HH:MM``."""
    total_minutes = int((moment.utcoffset() or timedelta(0)).total_seconds() // 60)
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{'-' if total_minutes < 0 else '+'}{hours:02d}:{minutes:02d}"


def _level_number(level: str) -> int:
    """Resolve a configured level name and fall back to INFO for invalid values."""
    resolved = logging.getLevelName(level.upper())
    return resolved if isinstance(resolved, int) else logging.INFO


def _close_handlers(logger: logging.Logger) -> None:
    """Remove and close handlers owned by the Zett logger during reconfiguration."""
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def configure_logging(
    log_directory: Path | None = None,
    *,
    file_name: str = LOG_FILE_NAME,
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
    normalized_file_name = file_name.strip()
    if not normalized_file_name or Path(normalized_file_name).name != normalized_file_name:
        raise ValueError("Log file name must be a non-empty file name without directories")
    log_path = directory / normalized_file_name
    signature = (log_path, max_bytes, backup_count, resolved_level)
    with _configuration_lock:
        if _configured_signature == signature:
            return log_path
        directory.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(LOGGER_NAMESPACE)
        _close_handlers(logger)
        logger.setLevel(_level_number(resolved_level))
        logger.propagate = False

        formatter = LocalTimeFormatter(
            fmt=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT,
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
    if not isinstance(logging.getLevelName(configured_level), int):
        configured_level = "INFO"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "zett": {
                "()": "zett.infra.log.LocalTimeFormatter",
                "fmt": LOG_FORMAT,
                "datefmt": LOG_DATE_FORMAT,
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


def log_preview(value: str, *, limit: int = LOG_PREVIEW_CHARS) -> str:
    """Return one single-line, length-capped rendering of text for a log record.

    Runs of whitespace collapse so a preview never breaks the one-record-per-line
    log format, and the result is truncated so a long prompt or answer stays a
    short, scannable hint instead of flooding the file.
    """
    flattened = " ".join(value.split())
    return flattened if len(flattened) <= limit else f"{flattened[:limit]}…"
