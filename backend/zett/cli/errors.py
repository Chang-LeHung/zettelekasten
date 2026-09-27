"""Shared command plumbing: usage errors and one exit-status policy."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable


class UsageError(RuntimeError):
    """Raised when the flags cannot describe a valid request."""


def run(parser: argparse.ArgumentParser, handler: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> int:
    """Run one command handler and turn its failures into an exit status.

    A flag problem is a usage error (2) the parser renders with its own usage
    line; a server that cannot be reached or that refuses the request is a
    runtime failure (1) printed on stderr, so a script can tell "the command
    was typed wrong" from "the server said no".
    """
    from .client import ServerRequestError, ServerUnavailableError

    try:
        return handler(args)
    except UsageError as error:
        parser.error(str(error))
        raise AssertionError("parser.error always exits") from error
    except (ServerUnavailableError, ServerRequestError) as error:
        print(f"{parser.prog}: {error}", file=sys.stderr)
        return 1
