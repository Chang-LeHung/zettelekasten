import logging
import sys
from datetime import datetime
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


def test_log_timestamps_use_local_time_with_an_explicit_offset(tmp_path) -> None:
    """A log line names the operator's local time and its zone, not a bare UTC clock."""
    log_path = configure_logging(tmp_path, max_bytes=1024, backup_count=1, level="INFO")
    logger = get_logger("zett.tests.localtimt")

    logger.info("record=1")
    for handler in logging.getLogger("zett").handlers:
        handler.flush()

    line = log_path.read_text(encoding="utf-8").splitlines()[0]
    stamp = " ".join(line.split(" ")[:2])
    parsed = datetime.fromisoformat(stamp)
    local_now = datetime.now().astimezone()
    # Human-readable shape: a space between date and time, and no ISO ``T``.
    assert "T" not in stamp
    assert parsed.utcoffset() == local_now.utcoffset()
    assert abs((parsed.replace(tzinfo=None) - local_now.replace(tzinfo=None)).total_seconds()) < 60


def test_the_previous_formatter_name_still_resolves() -> None:
    """A reload child configured before the rename must still resolve its formatter."""
    import importlib

    module = importlib.import_module("zett.infra.log")

    assert module.UTCFormatter is module.LocalTimeFormatter


def test_logging_configuration_can_target_a_process_specific_file(tmp_path) -> None:
    log_path = configure_logging(tmp_path, file_name="scheduler.log")
    logger = get_logger("zett.tests.scheduler")

    logger.info("scheduler marker")
    for handler in logging.getLogger("zett").handlers:
        handler.flush()

    assert log_path == tmp_path / "scheduler.log"
    assert "scheduler marker" in log_path.read_text()


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
