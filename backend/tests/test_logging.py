import logging
import sys
from logging.handlers import RotatingFileHandler

import pytest

from zett.infra.log import LOG_FILE_NAME, configure_logging, get_logger, shutdown_logging, uvicorn_log_config


@pytest.fixture(autouse=True)
def clean_logging_handlers():
    """Prevent temporary handlers from leaking into later tests."""
    yield
    shutdown_logging()


def test_kcs_logging_rotates_between_two_bounded_files(tmp_path) -> None:
    log_path = configure_logging(tmp_path, max_bytes=512, backup_count=1, level="INFO")
    logger = get_logger("zett.tests.rotation")

    for index in range(100):
        logger.info("record=%d payload=%s", index, "x" * 80)
    for handler in logging.getLogger("zett").handlers:
        handler.flush()

    log_files = sorted(tmp_path.glob(f"{LOG_FILE_NAME}*"))
    rotating_handlers = [
        handler for handler in logging.getLogger("zett").handlers if isinstance(handler, RotatingFileHandler)
    ]

    assert log_path == tmp_path / LOG_FILE_NAME
    assert [path.name for path in log_files] == ["zett.log", "zett.log.1"]
    assert len(rotating_handlers) == 1
    assert rotating_handlers[0].maxBytes == 512
    assert rotating_handlers[0].backupCount == 1
    assert "zett.tests.rotation" in "".join(path.read_text() for path in log_files)
    assert "test_logging.py:" in "".join(path.read_text() for path in log_files)


def test_logging_configuration_is_idempotent(tmp_path) -> None:
    configure_logging(tmp_path, max_bytes=1024, backup_count=1)
    handler_count = len(logging.getLogger("zett").handlers)

    configure_logging(tmp_path, max_bytes=1024, backup_count=1)

    assert len(logging.getLogger("zett").handlers) == handler_count


def test_log_record_reports_the_exact_source_call_site(tmp_path) -> None:
    log_path = configure_logging(tmp_path)
    logger = get_logger("zett.tests.location")

    expected_line = sys._getframe().f_lineno + 1
    logger.info("location marker")
    for handler in logging.getLogger("zett").handlers:
        handler.flush()

    assert f"test_logging.py:{expected_line} location marker" in log_path.read_text()


def test_invalid_log_level_falls_back_to_info(tmp_path) -> None:
    configure_logging(tmp_path, level="not-a-level")

    assert logging.getLogger("zett").level == logging.INFO


def test_uvicorn_log_format_includes_source_location() -> None:
    configuration = uvicorn_log_config()
    formatters = configuration["formatters"]

    assert isinstance(formatters, dict)
    assert "%(filename)s:%(lineno)d" in formatters["zett"]["fmt"]
