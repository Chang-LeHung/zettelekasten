"""Argument types shared by the commands."""

from __future__ import annotations

import argparse
from collections.abc import Callable


def bounded_int(minimum: int, maximum: int) -> Callable[[str], int]:
    """Return an argparse type that rejects an integer outside ``minimum..maximum``."""

    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return number

    return parse


def bounded_float(minimum: float, maximum: float) -> Callable[[str], float]:
    """Return an argparse type that rejects a number outside ``minimum..maximum``."""

    def parse(value: str) -> float:
        try:
            number = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return number

    return parse
