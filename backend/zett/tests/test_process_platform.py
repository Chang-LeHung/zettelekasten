"""Platform-specific process primitives for the scheduler and CLI."""

import os
import signal

import pytest

from zett.infra.scheduler import process_platform

WINDOWS_NETSTAT = """\

Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:6280         0.0.0.0:0              LISTENING       86519
  TCP    127.0.0.1:6280         127.0.0.1:51750        ESTABLISHED     86519
  TCP    127.0.0.1:6299         0.0.0.0:0              LISTENING       999
  TCP    [::]:6280              [::]:0                 LISTENING       86520
  UDP    0.0.0.0:500            *:*
"""


def test_spawn_kwargs_use_a_new_session_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_platform, "WINDOWS", False)

    assert process_platform.spawn_kwargs() == {"start_new_session": True}


def test_spawn_kwargs_use_a_process_group_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_platform, "WINDOWS", True)

    assert process_platform.spawn_kwargs() == {"creationflags": process_platform.CREATE_NEW_PROCESS_GROUP}


def test_helper_process_kwargs_stay_plain_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_platform, "WINDOWS", False)

    assert process_platform.helper_process_kwargs() == {}


def test_helper_process_kwargs_hide_the_console_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_platform, "WINDOWS", True)

    assert process_platform.helper_process_kwargs() == {"creationflags": process_platform.CREATE_NO_WINDOW}


def test_is_process_running_rejects_sentinel_pids() -> None:
    assert process_platform.is_process_running(0) is False
    assert process_platform.is_process_running(1) is False


def test_is_process_running_uses_signal_zero_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(process_platform, "WINDOWS", False)
    monkeypatch.setattr(process_platform.os, "kill", lambda pid, sig: calls.append((pid, sig)))

    assert process_platform.is_process_running(os.getpid()) is True
    assert calls == [(os.getpid(), 0)]


def test_is_process_running_treats_a_missing_process_as_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(process_platform, "WINDOWS", False)
    monkeypatch.setattr(process_platform.os, "kill", missing)

    assert process_platform.is_process_running(4242) is False


def test_is_process_running_uses_the_windows_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    probed: list[int] = []
    monkeypatch.setattr(process_platform, "WINDOWS", True)
    monkeypatch.setattr(process_platform, "_windows_process_running", lambda pid: probed.append(pid) or True)

    assert process_platform.is_process_running(4242) is True
    assert probed == [4242]


def test_terminate_process_escalates_only_when_forced_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(process_platform, "WINDOWS", False)
    monkeypatch.setattr(process_platform.os, "kill", lambda pid, sig: calls.append((pid, sig)))
    # Windows has no SIGKILL, so the forced-POSIX branch needs the signal here.
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)

    process_platform.terminate_process(4242, force=False)
    process_platform.terminate_process(4242, force=True)

    assert calls == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]


def test_terminate_process_uses_terminate_process_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(process_platform, "WINDOWS", True)
    monkeypatch.setattr(process_platform.os, "kill", lambda pid, sig: calls.append((pid, sig)))

    process_platform.terminate_process(4242, force=False)
    process_platform.terminate_process(4242, force=True)

    # Windows cannot catch SIGTERM, so both phases map to TerminateProcess.
    assert calls == [(4242, signal.SIGTERM), (4242, signal.SIGTERM)]


def test_restrict_file_mode_avoids_fchmod_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(_descriptor: int, _mode: int) -> None:
        raise AssertionError("os.fchmod does not exist on Windows")

    monkeypatch.setattr(process_platform, "WINDOWS", True)
    monkeypatch.setattr(process_platform.os, "fchmod", explode, raising=False)

    process_platform.restrict_file_mode(7)


def test_restrict_file_mode_sets_owner_only_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(process_platform, "WINDOWS", False)
    # Windows has no os.fchmod, so the forced-POSIX branch needs the helper here.
    monkeypatch.setattr(
        process_platform.os, "fchmod", lambda descriptor, mode: calls.append((descriptor, mode)), raising=False
    )

    process_platform.restrict_file_mode(7)

    assert calls == [(7, 0o600)]


def test_command_line_reads_ps_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_platform, "WINDOWS", False)
    monkeypatch.setattr(
        process_platform,
        "_run_command",
        lambda command, timeout=2.0: "/usr/bin/python -m zett.cli worker\n",
    )

    assert process_platform.command_line(4242) == "/usr/bin/python -m zett.cli worker"


def test_command_line_is_unknown_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_platform, "WINDOWS", True)

    assert process_platform.command_line(4242) is None


def test_pids_listening_on_parses_windows_netstat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_platform, "WINDOWS", True)
    monkeypatch.setattr(process_platform, "_run_command", lambda command, timeout=2.0: WINDOWS_NETSTAT)

    assert process_platform.pids_listening_on(6280) == [86519, 86520]
    assert process_platform.pids_listening_on(6299) == [999]
    assert process_platform.pids_listening_on(1234) == []


def test_pids_listening_on_parses_lsof_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_platform, "WINDOWS", False)
    monkeypatch.setattr(process_platform, "_run_command", lambda command, timeout=2.0: "86519\n999\n")

    assert process_platform.pids_listening_on(6280) == [999, 86519]


def test_diagnostic_commands_degrade_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(command: list[str], timeout: float = 2.0) -> str | None:
        return None

    monkeypatch.setattr(process_platform, "_run_command", unavailable)

    assert process_platform.command_line(4242) is None
    assert process_platform.pids_listening_on(6280) == []
