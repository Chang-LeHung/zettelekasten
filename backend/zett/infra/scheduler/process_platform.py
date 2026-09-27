"""Platform-specific process primitives for the scheduler, CLI, and helpers.

Everything that differs between POSIX and Windows lives here so the runtime
state machine, the process launcher, and synchronous helpers such as ``git``
stay platform agnostic. The Windows branches follow the documented behaviour of
``os.kill``, which maps to ``TerminateProcess`` for any signal other than
``CTRL_C_EVENT`` and ``CTRL_BREAK_EVENT``. They are unit tested by forcing the
platform flag; CI also runs the full suite on Windows and macOS.
"""

import os
import signal
import socket
import subprocess  # noqa: S404
import sys
from typing import Any

WINDOWS = sys.platform == "win32"

# Windows refuses the call instead of ignoring an unsupported flag, so the
# constant is only read on the Windows branch.
CREATE_NEW_PROCESS_GROUP = 0x00000200
# A console-subsystem helper started by a parent that owns no console would
# otherwise open its own console window.
CREATE_NO_WINDOW = 0x08000000
# A background server must outlive the terminal that started it, and on Windows
# that means no attached console at all.
DETACHED_PROCESS = 0x00000008

_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def spawn_kwargs() -> dict[str, Any]:
    """Return ``Popen`` kwargs that detach a child from the console group.

    POSIX gets its own session; Windows gets a new process group, which keeps a
    console Ctrl+C from hitting the supervised scheduler and workers.
    """
    if WINDOWS:
        return {"creationflags": CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def background_spawn_kwargs() -> dict[str, Any]:
    """Return ``Popen`` kwargs for a server that outlives this process.

    ``zett start`` returns to the shell while the server keeps running, so the
    child must not share the caller's terminal: POSIX starts a new session, and
    Windows starts a process without a console at all. Supervised scheduler and
    worker children use ``spawn_kwargs`` instead, because they stay attached to
    the Web process that owns and restarts them.
    """
    if WINDOWS:
        return {"creationflags": DETACHED_PROCESS}
    return {"start_new_session": True}


def helper_process_kwargs() -> dict[str, Any]:
    """Return ``subprocess`` kwargs for one short-lived helper process.

    Helpers such as ``git`` are started synchronously inside the console the
    server already owns, so POSIX needs nothing. On Windows the child is started
    windowless instead of opening a second console window.
    """
    if WINDOWS:
        return {"creationflags": CREATE_NO_WINDOW}
    return {}


def is_process_running(pid: int) -> bool:
    """Return whether ``pid`` is alive without disturbing it."""
    if pid <= 1:
        return False
    if WINDOWS:
        return _windows_process_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_process(pid: int, *, force: bool) -> None:
    """Terminate ``pid``; raises ``ProcessLookupError`` when it is already gone.

    Windows has no catchable termination signal, so the graceful and forced
    phases are the same call there and callers should expect an immediate stop.
    """
    if WINDOWS:
        os.kill(pid, signal.SIGTERM)
        return
    os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)


def command_line(pid: int) -> str | None:
    """Return a best-effort command line for ``pid``.

    POSIX reads it from ``ps``. Windows only exposes the image path through the
    diagnostic tools we are willing to shell out to, which is not enough to
    confirm a process belongs to this application, so this reports ``None`` and
    callers fall back to the recorded runtime state.
    """
    if WINDOWS:
        return None
    output = _run_command(["ps", "-p", str(pid), "-o", "command="])
    if output is None:
        return None
    return output.strip() or None


def pids_listening_on(port: int) -> list[int]:
    """Return the PIDs listening on ``port``, or an empty list when unknown."""
    if WINDOWS:
        return _parse_windows_netstat(_run_command(["netstat", "-ano", "-p", "TCP"]), port)
    output = _run_command(["lsof", "-ti", f"tcp:{port}"])
    if output is None:
        return []
    return sorted({int(value) for value in output.split() if value.isdigit()})


def port_is_open(port: int, *, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """Return whether something accepts a connection on ``host:port``."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def dialable_host(host: str) -> str:
    """Return the host a local client should dial for a bind address.

    A wildcard bind listens on every interface, which is not something a URL or
    a readiness probe can name, so those cases resolve to the loopback address.
    """
    return "127.0.0.1" if host in {"0.0.0.0", "::", "::0", "*"} else host


def restrict_file_mode(descriptor: int) -> None:
    """Apply owner-only file permissions where the platform supports them.

    Windows has no POSIX mode bits and no ``os.fchmod``, so this is a
    documented no-op there instead of an ``AttributeError``.
    """
    if WINDOWS:
        return
    os.fchmod(descriptor, 0o600)


def _windows_process_running(pid: int) -> bool:
    """Return whether a Windows process is alive via ``GetExitCodeProcess``."""
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _parse_windows_netstat(output: str | None, port: int) -> list[int]:
    """Parse ``netstat -ano`` rows for listeners on ``port``."""
    if output is None:
        return []
    pids: set[int] = set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].upper() != "TCP":
            continue
        local_address, state, pid = fields[1], fields[3], fields[4]
        if state.upper() != "LISTENING" or not pid.isdigit():
            continue
        if local_address.rsplit(":", 1)[-1] != str(port):
            continue
        pids.add(int(pid))
    return sorted(pids)


def _run_command(command: list[str], *, timeout: float = 2.0) -> str | None:
    """Run a diagnostic command, returning ``None`` when it is unavailable."""
    try:
        result = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


__all__ = [
    "WINDOWS",
    "background_spawn_kwargs",
    "command_line",
    "dialable_host",
    "helper_process_kwargs",
    "is_process_running",
    "pids_listening_on",
    "port_is_open",
    "restrict_file_mode",
    "spawn_kwargs",
    "terminate_process",
]
