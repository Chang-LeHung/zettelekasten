"""Logging helpers for the standalone IM gateway."""

import logging


def configure_logging() -> None:
    """Configure process-wide gateway logging once."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """Return one gateway logger."""
    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger"]
