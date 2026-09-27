"""Background ``zett start`` and ``zett status`` behavior."""

import asyncio
import os
import re
import socket
import sys
from datetime import datetime
from pathlib import Path

import pytest

from zett import cli
from zett._compat import UTC
from zett.application.runtime import BackgroundStartError, RuntimeService
from zett.cli import main
from zett.config import settings
from zett.infra.scheduler import processes
from zett.infra.scheduler.processes import BACKGROUND_LOG_FILE_NAME, BackgroundServerProcess
from zett.infra.scheduler.runtime_state import RuntimeProcessController, RuntimeStateStore
from zett.schemas import ProcessRole, RuntimeStatus, ServerRuntimeState, ServerStartResult


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class FakeLauncher:
    """Record one launch call and optionally bind the requested port."""

    def __init__(self, *, pid: int, listen: bool) -> None:
        self.pid = pid
        self.listen = listen
        self.calls: list[dict[str, object]] = []
        self.listener: socket.socket | None = None

    def __call__(self, *, host: str, port: int, reload: bool, log_path: Path) -> BackgroundServerProcess:
        self.calls.append({"host": host, "port": port, "reload": reload, "log_path": log_path})
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("uvicorn startup traceback\n", encoding="utf-8")
        if self.listen:
            self.listener = socket.socket()
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listener.bind((host, port))
            self.listener.listen()
        return BackgroundServerProcess(pid=self.pid, log_path=log_path)

    def close(self) -> None:
        if self.listener is not None:
            self.listener.close()
            self.listener = None


def _service(
    tmp_path: Path,
    *,
    launcher: FakeLauncher,
    timeout_seconds: float = 2.0,
) -> RuntimeService:
    return RuntimeService(
        controller=RuntimeProcessController(RuntimeStateStore(tmp_path / "runtime.json")),
        launcher=launcher,
        timeout_seconds=timeout_seconds,
        poll_seconds=0.01,
    )


async def test_start_in_background_returns_once_the_port_answers(tmp_path: Path) -> None:
    port = _free_port()
    launcher = FakeLauncher(pid=os.getpid(), listen=True)
    try:
        result = await _service(tmp_path, launcher=launcher).start_in_background(
            host="127.0.0.1",
            port=port,
            reload=False,
        )
    finally:
        launcher.close()

    assert result == ServerStartResult(
        pid=os.getpid(),
        port=port,
        url=f"http://127.0.0.1:{port}",
        log_path=str(tmp_path / "logs" / BACKGROUND_LOG_FILE_NAME),
    )
    assert launcher.calls == [
        {"host": "127.0.0.1", "port": port, "reload": False, "log_path": tmp_path / "logs" / BACKGROUND_LOG_FILE_NAME}
    ]


async def test_start_in_background_rejects_a_second_live_server(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "runtime.json")
    await store.write(ServerRuntimeState(server_pid=os.getpid(), port=6312))
    launcher = FakeLauncher(pid=os.getpid(), listen=False)

    with pytest.raises(RuntimeError, match="already running"):
        await _service(tmp_path, launcher=launcher).start_in_background(
            host="127.0.0.1",
            port=6313,
            reload=False,
        )

    assert launcher.calls == []


async def test_start_in_background_reports_a_child_that_never_binds(tmp_path: Path) -> None:
    launcher = FakeLauncher(pid=999_999_991, listen=False)
    service = _service(tmp_path, launcher=launcher, timeout_seconds=0.2)

    with pytest.raises(BackgroundStartError) as failure:
        await service.start_in_background(host="127.0.0.1", port=_free_port(), reload=False)

    message = str(failure.value)
    assert "did not start in the background" in message
    assert "no longer running" in message
    assert "uvicorn startup traceback" in message
    assert "background.log" in message


async def test_start_in_background_reports_a_launcher_that_cannot_spawn(tmp_path: Path) -> None:
    def broken_launcher(**_: object) -> BackgroundServerProcess:
        raise OSError("permission denied")

    service = _service(tmp_path, launcher=FakeLauncher(pid=os.getpid(), listen=False))
    service.launcher = broken_launcher

    with pytest.raises(BackgroundStartError, match="permission denied"):
        await service.start_in_background(host="127.0.0.1", port=_free_port(), reload=False)


async def test_status_reports_the_recorded_pids_without_asking_the_server(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "runtime.json")
    await store.write(ServerRuntimeState(server_pid=os.getpid(), port=6315, worker_pids=[os.getpid()]))

    status = await _service(tmp_path, launcher=FakeLauncher(pid=os.getpid(), listen=False)).status()

    assert status.running is True
    assert [child.pid for child in status.children] == [os.getpid()]
    assert status.children[0].running is True


def test_cli_status_prints_running_roles_and_pid_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = ServerRuntimeState(
        server_pid=os.getpid(),
        port=6316,
        scheduler_pids=[os.getpid()],
        worker_pids=[999_999_990],
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(RuntimeService, "status", _reported_status(_seeded_store(tmp_path, state)))

    exit_code = main(["status"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Zett is running" in output
    assert "http://127.0.0.1:6316" in output
    assert f"pid={os.getpid()} running" in output
    assert "pid=999999990 not running" in output


def test_cli_status_exits_nonzero_when_not_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = ServerRuntimeState(server_pid=999_999_989, port=6317)
    monkeypatch.setattr(RuntimeService, "status", _reported_status(_seeded_store(tmp_path, state)))

    exit_code = main(["status"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Zett is not running" in output
    assert "stale runtime state" in output


def test_cli_start_short_flags_select_foreground_port_and_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(
        cli,
        "_run_server",
        lambda *, host, port, reload: launched.append((host, port, reload)) or 0,
    )

    exit_code = main(["start", "-f", "-p", "6391", "-r"])

    assert exit_code == 0
    assert launched == [("127.0.0.1", 6391, True)]


def test_cli_start_defaults_to_background(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    started: list[dict[str, object]] = []
    monkeypatch.setattr(RuntimeService, "start_in_background", _recording_start(started))

    exit_code = main(["start", "-p", "6390"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert started == [{"host": "127.0.0.1", "port": 6390, "reload": False}]
    assert "running in the background" in output
    assert "http://127.0.0.1:6390" in output


def test_cli_start_reports_a_failed_detached_start_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def failing_start(_: RuntimeService, *, host: str, port: int, reload: bool) -> ServerStartResult:
        del host, port, reload
        raise BackgroundStartError("Port 6280 is already in use")

    monkeypatch.setattr(RuntimeService, "start_in_background", failing_start)

    exit_code = main(["start"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Port 6280 is already in use" in captured.err
    assert captured.out == ""


def test_cli_help_lists_only_user_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    output = capsys.readouterr().out
    assert exit_info.value.code == 0
    for command in ("start", "status", "stop"):
        assert command in output
    # The scheduler and worker roles belong to `zett start`, not to this CLI.
    assert "scheduler" not in output
    assert "worker" not in output


def test_cli_description_matches_the_readme_tagline(capsys: pytest.CaptureFixture[str]) -> None:
    """`zett --help`, the packaged summary, and the README tell one sentence.

    The packaged summary is the README tagline without its sentence-final
    period, so the comparison normalizes that one character.
    """
    project = Path(__file__).resolve().parents[2]
    pyproject = project / "pyproject.toml"
    readme = " ".join((project.parent / "README.md").read_text(encoding="utf-8").split())
    summary = re.search(r'^description = "(.+)"$', pyproject.read_text(encoding="utf-8"), re.MULTILINE)
    assert summary is not None

    with pytest.raises(SystemExit):
        main(["--help"])

    help_text = " ".join(capsys.readouterr().out.split())
    assert cli.PROGRAM_DESCRIPTION.rstrip(".") == summary.group(1).rstrip(".")
    assert cli.PROGRAM_DESCRIPTION.rstrip(".") in readme
    assert cli.PROGRAM_DESCRIPTION in help_text


def test_cli_without_a_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0

    assert "COMMAND" in capsys.readouterr().out


def test_cli_rejects_bad_options_with_usage(capsys: pytest.CaptureFixture[str]) -> None:
    bad_invocations = (
        ["start", "--port", "70000"],
        ["start", "--port", "not-a-port"],
        ["start", "-b", "-f"],
        ["stop", "--timeout", "0.5"],
        ["worker", "--poll-interval", "0"],
        ["unknown"],
    )
    for argv in bad_invocations:
        with pytest.raises(SystemExit) as exit_info:
            main(argv)
        assert exit_info.value.code == 2
    assert "usage: zett" in capsys.readouterr().err


def test_cli_keeps_the_internal_roles_runnable_but_unlisted() -> None:
    """`zett start` spawns `python -m zett.cli <role>`, so roles stay parseable."""
    parser = cli.build_parser()

    scheduler = parser.parse_args(["scheduler", "--instance-id", "instance-1"])
    worker = parser.parse_args(["worker"])

    assert scheduler.handler is cli._scheduler
    assert scheduler.instance_id == "instance-1"
    assert worker.handler is cli._worker


def test_subprocess_launcher_starts_the_internal_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """The supervisor spawns the role subcommand, which must stay in the CLI."""
    commands: list[list[str]] = []

    class FakeProcess:
        pid = 4321

        def poll(self) -> None:
            return None

    def fake_popen(command: list[str], **_: object) -> FakeProcess:
        commands.append(command)
        return FakeProcess()

    monkeypatch.setattr(processes.subprocess, "Popen", fake_popen)

    managed = processes.SubprocessLauncher().start(ProcessRole.WORKER, "instance-1")

    assert managed.pid == 4321
    assert managed.is_running() is True
    assert commands == [[sys.executable, "-m", "zett.cli", "worker", "--instance-id", "instance-1"]]


def test_run_server_exports_the_bind_address_its_children_re_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reload worker and the supervised children read config from the env."""
    port = _free_port()
    monkeypatch.setattr(settings, "host", settings.host)
    monkeypatch.setattr(settings, "port", settings.port)
    monkeypatch.delenv("ZETT_HOST", raising=False)
    monkeypatch.delenv("ZETT_PORT", raising=False)
    served: list[dict[str, object]] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: served.append(kwargs))

    cli._run_server(host="127.0.0.1", port=port, reload=True)

    assert os.environ["ZETT_HOST"] == "127.0.0.1"
    assert os.environ["ZETT_PORT"] == str(port)
    assert len(served) == 1
    assert served[0]["host"] == "127.0.0.1"
    assert served[0]["port"] == port
    assert served[0]["reload"] is True
    assert served[0]["access_log"] is False


def _seeded_store(tmp_path: Path, state: ServerRuntimeState) -> RuntimeStateStore:
    """Write one runtime state file for a CLI status test."""
    store = RuntimeStateStore(tmp_path / "runtime.json")
    asyncio.run(store.write(state))
    return store


def _reported_status(store: RuntimeStateStore):
    """Build a patch target that reports one store through the real controller."""
    controller = RuntimeProcessController(store)

    async def status(_: RuntimeService) -> RuntimeStatus:
        return await controller.status()

    return status


def _recording_start(calls: list[dict[str, object]]):
    """Build a patch target that records one detached start instead of spawning."""

    async def start_in_background(
        _: RuntimeService,
        *,
        host: str,
        port: int,
        reload: bool,
    ) -> ServerStartResult:
        calls.append({"host": host, "port": port, "reload": reload})
        return ServerStartResult(
            pid=os.getpid(),
            port=port,
            url=f"http://{host}:{port}",
            log_path="/tmp/background.log",
        )

    return start_in_background
