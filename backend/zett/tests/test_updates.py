"""The update check, the installer it picks, and the API that exposes both."""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zett.application.api.routes import updates as update_routes
from zett.application.runtime.updates import UpdateService, installed_version, version_key
from zett.infra.updates import installer as installer_module
from zett.infra.updates.pypi import PypiError
from zett.main import app
from zett.schemas import UpdateInstallResult, UpdateStatus


def uv_tool_installer() -> installer_module.Installer:
    """The installer a `uv tool` copy of Zett reports, used as a test stand-in."""
    return installer_module.Installer(
        ("uv", "tool", "install", "--force", "{requirement}"),
        "Installed by uv; the update runs `uv tool install --force` for the new release.",
    )


class FakePypi:
    """A PyPI client that answers from memory and counts its calls."""

    def __init__(self, version: str = "0.0.2", *, error: str | None = None) -> None:
        self.version = version
        self.error = error
        self.lookups = 0

    async def latest_version(self) -> str:
        self.lookups += 1
        if self.error is not None:
            raise PypiError(self.error)
        return self.version


def test_version_key_orders_releases_and_ignores_pre_release_suffixes() -> None:
    assert version_key("0.0.2") > version_key("0.0.1")
    assert version_key("0.1.0") > version_key("0.0.9")
    assert version_key("1.0.0rc1") == version_key("1.0.0")
    assert version_key("") == ()


def test_installed_version_falls_back_for_an_uninstalled_distribution() -> None:
    assert installed_version("zettelekasten") != ""
    assert installed_version("zett-nothing-installs-this") == "0.0.0"


def found(name: str) -> str:
    """A ``which`` that finds every tool, so detection is decided by the environment alone."""
    return f"/usr/bin/{name}"


def test_detect_installer_reads_the_environment_that_owns_the_copy(tmp_path: Path) -> None:
    uv_tool = installer_module.detect_installer(
        prefix=Path("/Users/x/.local/share/uv/tools/zettelekasten"), which=found
    )
    # uv's own upgrade, which keeps the Python, the extensions, and the install-time options.
    assert uv_tool.command is not None and uv_tool.command[:3] == ("/usr/bin/uv", "tool", "upgrade")
    assert "uv tool upgrade" in uv_tool.detail
    assert uv_tool.fallback is not None and uv_tool.fallback[:4] == ("/usr/bin/uv", "tool", "install", "--force")

    pipx = installer_module.detect_installer(prefix=Path("/home/x/.local/pipx/venvs/zettelekasten"), which=found)
    assert pipx.command == ("/usr/bin/pipx", "upgrade", "zettelekasten")
    assert "pipx" in pipx.detail

    # A checkout looks like `<root>/.git` next to `<root>/backend/pyproject.toml`,
    # with the imported package at `<root>/backend/zett`.
    checkout = tmp_path / "backend" / "zett"
    checkout.mkdir(parents=True)
    (tmp_path / "backend" / "pyproject.toml").write_text("[project]\nname='zettelekasten'\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    source = installer_module.detect_installer(prefix=tmp_path / "venv", package_root=checkout, which=found)
    assert source.command is None
    assert "git pull" in source.detail

    pip = installer_module.detect_installer(
        prefix=tmp_path / "venv", package_root=tmp_path / "site/zett", which=found, has_pip=lambda: True
    )
    assert pip.can_install
    assert pip.detail.startswith("Installed by pip")


def test_the_receipt_names_the_installer_wherever_the_environment_lives(tmp_path: Path) -> None:
    # UV_TOOL_DIR and PIPX_HOME move the environment: nothing in the path says "uv" or "pipx".
    uv_env = tmp_path / "anywhere" / "one"
    uv_env.mkdir(parents=True)
    (uv_env / "uv-receipt.toml").write_text("[tool]\nrequirements = [{ name = 'zettelekasten' }]\n", encoding="utf-8")
    pipx_env = tmp_path / "elsewhere" / "two"
    pipx_env.mkdir(parents=True)
    (pipx_env / "pipx_metadata.json").write_text("{}", encoding="utf-8")

    uv = installer_module.detect_installer(prefix=uv_env, package_root=tmp_path / "site/zett", which=found)
    assert uv.command is not None and uv.command[0] == "/usr/bin/uv"
    pipx = installer_module.detect_installer(prefix=pipx_env, package_root=tmp_path / "site/zett", which=found)
    assert pipx.command is not None and pipx.command[0] == "/usr/bin/pipx"


def test_a_uv_update_keeps_the_python_and_the_extensions_beside_zett(tmp_path: Path) -> None:
    env = tmp_path / "tool"
    env.mkdir()
    (env / "uv-receipt.toml").write_text(
        """[tool]
requirements = [
    { name = "zettelekasten", specifier = "==0.0.4" },
    { name = "pyfiglet" },
    { name = "zett-weixin", specifier = ">=0.0.1" },
]
entrypoints = [
    { name = "zett", install-path = "/x/bin/zett" },
]
""",
        encoding="utf-8",
    )
    installer = installer_module.detect_installer(prefix=env, package_root=tmp_path / "site/zett", which=found)

    # A receipt pinned to ==0.0.4 makes the upgrade a no-op, so a reinstall names the new bound.
    assert installer.fallback is not None
    command = list(installer.fallback)
    # The same Python as the running copy, or uv would pick its default and change it.
    assert command[command.index("--python") + 1] == f"{sys.version_info.major}.{sys.version_info.minor}"
    # Every other requirement of the receipt, and not Zett itself: that is the new bound.
    withs = [command[index + 1] for index, value in enumerate(command) if value == "--with"]
    assert withs == ["pyfiglet", "zett-weixin>=0.0.1"]
    assert command[-1] == "{requirement}"


def test_a_receipt_entry_that_cannot_be_kept_is_reported(tmp_path: Path, captured_logs: list[str]) -> None:
    env = tmp_path / "tool"
    env.mkdir()
    (env / "uv-receipt.toml").write_text(
        '[tool]\nrequirements = [\n    { name = "zettelekasten" },\n    { name = "mine", directory = "/src/mine" },\n]\n',
        encoding="utf-8",
    )
    assert installer_module.with_arguments(env) == ()
    assert any("cannot keep" in message for message in captured_logs)


def test_zett_installed_from_a_file_is_not_mistaken_for_an_extension(tmp_path: Path, captured_logs: list[str]) -> None:
    env = tmp_path / "tool"
    env.mkdir()
    (env / "uv-receipt.toml").write_text(
        '[tool]\nrequirements = [\n    { name = "zettelekasten", path = "/dist/zettelekasten-0.0.6.whl" },\n'
        '    { name = "pyfiglet" },\n]\n',
        encoding="utf-8",
    )
    assert installer_module.with_arguments(env) == ("--with", "pyfiglet")
    assert not any("cannot keep" in message for message in captured_logs)


def test_a_tool_that_installed_zett_but_is_not_on_path_says_so(tmp_path: Path) -> None:
    env = tmp_path / "tool"
    env.mkdir()
    (env / "uv-receipt.toml").write_text("[tool]\nrequirements = []\n", encoding="utf-8")
    lost = installer_module.detect_installer(prefix=env, package_root=tmp_path / "site/zett", which=lambda _: None)
    assert lost.command is None and "not on this process's PATH" in lost.detail

    no_pip = installer_module.detect_installer(
        prefix=tmp_path / "venv", package_root=tmp_path / "site/zett", which=found, has_pip=lambda: False
    )
    assert no_pip.command is None and "no pip" in no_pip.detail


async def test_status_reports_a_newer_release_and_reuses_the_cache() -> None:
    client = FakePypi("0.0.2")
    service = UpdateService(
        client=client,  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
    )

    first = await service.status()
    assert first.latest == "0.0.2"
    assert first.update_available is (version_key("0.0.2") > version_key(first.current))
    assert first.can_install is first.update_available
    assert "uv tool install" in first.detail
    assert first.checked_at is not None
    assert client.lookups == 1

    await service.status()
    assert client.lookups == 1, "a fresh answer is reused"

    await service.status(refresh=True)
    assert client.lookups == 2, "an explicit refresh asks again"


async def test_status_asks_for_a_restart_once_the_installed_version_moves_past_the_running_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zett.application.runtime import updates as updates_module

    def build(running: str) -> UpdateService:
        return UpdateService(
            client=FakePypi("0.0.3"),  # type: ignore[arg-type]
            installer_factory=uv_tool_installer,
            running_version=running,
        )

    # Before the install the disk and the process agree.
    monkeypatch.setattr(updates_module, "installed_version", lambda distribution="": "0.0.1")
    before = await build("0.0.1").status(refresh=True)
    assert (before.current, before.installed, before.restart_required) == ("0.0.1", "0.0.1", False)
    assert before.update_available is True

    # The installer rewrote the files; only a restart changes the running code.
    monkeypatch.setattr(updates_module, "installed_version", lambda distribution="": "0.0.2")
    after = await build("0.0.1").status(refresh=True)
    assert (after.current, after.installed, after.restart_required) == ("0.0.1", "0.0.2", True)
    # Newer releases are still measured against the disk, not against the stale process.
    assert after.update_available is True and version_key(after.latest or "") > version_key(after.installed)

    restarted = await build("0.0.2").status(refresh=True)
    assert restarted.restart_required is False


async def test_an_environment_replaced_under_a_running_copy_asks_for_a_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zett.application.runtime import updates as updates_module

    # The running process cannot find its own distribution any more: another Python replaced the
    # environment. It must not read as an uninstalled checkout and keep offering the same update.
    monkeypatch.setattr(updates_module, "installed_version", lambda distribution="": "0.0.0")
    service = UpdateService(
        client=FakePypi("0.0.6"),  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
        running_version="0.0.5",
    )
    status = await service.status(refresh=True)
    assert status.restart_required is True
    assert status.installed == "0.0.6"
    assert status.update_available is False and status.can_install is False

    # A checkout that was never installed knows no version at all, and asks for nothing.
    checkout = UpdateService(
        client=FakePypi("0.0.6"),  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
        running_version="0.0.0",
    )
    assert (await checkout.status(refresh=True)).restart_required is False


async def test_status_reports_an_unreachable_index_without_failing() -> None:
    service = UpdateService(client=FakePypi(error="PyPI lookup failed: offline"))  # type: ignore[arg-type]
    status = await service.status(refresh=True)

    assert status.check_failed is True
    assert "offline" in status.detail
    assert status.latest is None
    assert status.update_available is False


async def test_status_ignores_a_stale_cache() -> None:
    client = FakePypi("0.0.3")
    service = UpdateService(client=client, interval=timedelta(0))  # type: ignore[arg-type]

    await service.status()
    await service.status()
    assert client.lookups == 2, "an expired answer is not reused"


async def test_install_hands_the_installer_a_requirement_not_a_file() -> None:
    calls: list[tuple[installer_module.Installer, str]] = []

    async def runner(installer: installer_module.Installer, requirement: str) -> installer_module.InstallOutcome:
        calls.append((installer, requirement))
        return installer_module.InstallOutcome(True, "Installed", ["Resolved 1 package"])

    service = UpdateService(
        client=FakePypi("0.0.2"),  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
        runner=runner,
    )
    result = await service.install("0.0.2")

    assert result.ok is True
    assert result.version == "0.0.2"
    assert result.needs_restart is True
    assert result.output_tail == ["Resolved 1 package"]
    # A lower bound, so the receipt a tool installer keeps never pins this release.
    assert [requirement for _, requirement in calls] == ["zettelekasten>=0.0.2"]


async def test_install_failure_does_not_ask_for_a_restart() -> None:
    async def runner(installer: installer_module.Installer, requirement: str) -> installer_module.InstallOutcome:
        return installer_module.InstallOutcome(False, "The installer exited with 1")

    service = UpdateService(
        client=FakePypi("0.0.2"),  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
        runner=runner,
    )
    result = await service.install("0.0.2")
    assert result.ok is False
    assert result.needs_restart is False


async def test_a_second_install_is_refused_while_one_runs() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def runner(installer: installer_module.Installer, requirement: str) -> installer_module.InstallOutcome:
        started.set()
        await release.wait()
        return installer_module.InstallOutcome(True, "Installed")

    service = UpdateService(
        client=FakePypi("0.0.2"),  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
        runner=runner,
    )
    first = asyncio.create_task(service.install("0.0.2"))
    await started.wait()
    second = await service.install("0.0.2")
    assert second.ok is False
    assert "already" in second.detail
    release.set()
    assert (await first).ok is True


async def test_run_installer_substitutes_the_requirement() -> None:
    installer = installer_module.Installer(
        (sys.executable, "-c", "import sys; print(sys.argv[1])", "{requirement}"),
        "test",
    )
    outcome = await installer_module.run_installer(installer, "zettelekasten>=0.0.2")
    assert outcome.ok is True
    assert outcome.output_tail == ["zettelekasten>=0.0.2"]


async def test_install_refuses_a_checkout_and_a_version_that_moved() -> None:
    checkout = UpdateService(
        client=FakePypi("0.0.2"),  # type: ignore[arg-type]
        installer_factory=lambda: installer_module.Installer(
            None,
            "This copy runs from a source checkout; update it with `git pull && make install`.",
        ),
    )
    refused = await checkout.install("0.0.2")
    assert refused.ok is False
    assert "git pull" in refused.detail

    moved = UpdateService(
        client=FakePypi("0.0.4"),  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
    )
    stale = await moved.install("0.0.2")
    assert stale.ok is False
    assert "0.0.4" in stale.detail


async def test_a_failed_or_refused_install_never_asks_for_a_restart() -> None:
    refused = await UpdateService(
        client=FakePypi("0.0.4"),  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
    ).install("0.0.2")
    assert (refused.ok, refused.needs_restart) == (False, False)

    checkout = await UpdateService(
        client=FakePypi("0.0.2"),  # type: ignore[arg-type]
        installer_factory=lambda: installer_module.Installer(None, "source checkout"),
    ).install("0.0.2")
    assert (checkout.ok, checkout.needs_restart) == (False, False)


async def test_install_goes_ahead_when_the_second_lookup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from zett.application.runtime import updates as updates_module

    monkeypatch.setattr(updates_module, "installed_version", lambda distribution="": "0.0.2")
    calls: list[str] = []

    async def runner(installer: installer_module.Installer, requirement: str) -> installer_module.InstallOutcome:
        calls.append(requirement)
        return installer_module.InstallOutcome(True, "Installed")

    # The check that offered 0.0.2 already worked; a flaky repeat must not cancel the update.
    service = UpdateService(
        client=FakePypi(error="PyPI lookup failed: ConnectTimeout"),  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
        runner=runner,
    )
    result = await service.install("0.0.2")
    assert result.ok is True
    assert calls == ["zettelekasten>=0.0.2"]


async def test_a_pinned_environment_is_reinstalled_when_the_upgrade_does_not_move(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zett.application.runtime import updates as updates_module

    ran: list[tuple[str, ...] | None] = []
    disk = {"version": "0.0.1"}

    async def runner(installer: installer_module.Installer, requirement: str) -> installer_module.InstallOutcome:
        ran.append(installer.command)
        if installer.command == ("uv", "tool", "install", "--force", "{requirement}"):
            disk["version"] = "0.0.3"  # only the reinstall moves a pinned environment
        return installer_module.InstallOutcome(True, "Installed")

    monkeypatch.setattr(updates_module, "installed_version", lambda distribution="": disk["version"])
    installer = installer_module.Installer(
        ("uv", "tool", "upgrade", "zettelekasten"),
        "uv",
        fallback=("uv", "tool", "install", "--force", "{requirement}"),
    )
    service = UpdateService(client=FakePypi("0.0.3"), installer_factory=lambda: installer, runner=runner)  # type: ignore[arg-type]

    result = await service.install("0.0.3")

    assert result.ok is True and result.needs_restart is True
    assert ran == [("uv", "tool", "upgrade", "zettelekasten"), ("uv", "tool", "install", "--force", "{requirement}")]


async def test_a_failed_upgrade_is_not_retried_with_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[int] = []

    async def runner(installer: installer_module.Installer, requirement: str) -> installer_module.InstallOutcome:
        ran.append(1)
        return installer_module.InstallOutcome(False, "The installer exited with 1")

    installer = installer_module.Installer(("uv", "tool", "upgrade"), "uv", fallback=("uv", "tool", "install"))
    service = UpdateService(client=FakePypi("0.0.3"), installer_factory=lambda: installer, runner=runner)  # type: ignore[arg-type]

    result = await service.install("0.0.3")
    # A network failure would fail the reinstall just as slowly: only a clean no-op earns a second try.
    assert result.ok is False and len(ran) == 1


async def test_install_trusts_the_disk_over_the_installers_exit_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from zett.application.runtime import updates as updates_module

    async def runner(installer: installer_module.Installer, requirement: str) -> installer_module.InstallOutcome:
        return installer_module.InstallOutcome(True, "Installed", ["Nothing to upgrade"])

    service = UpdateService(
        client=FakePypi("0.0.3"),  # type: ignore[arg-type]
        installer_factory=uv_tool_installer,
        runner=runner,
    )
    # The installer exited cleanly, but the release never reached the disk.
    monkeypatch.setattr(updates_module, "installed_version", lambda distribution="": "0.0.1")
    stuck = await service.install("0.0.3")
    assert stuck.ok is False and stuck.needs_restart is False
    assert "0.0.1 is still installed" in stuck.detail
    assert stuck.output_tail == ["Nothing to upgrade"]

    monkeypatch.setattr(updates_module, "installed_version", lambda distribution="": "0.0.3")
    moved = await service.install("0.0.3")
    assert moved.ok is True and moved.needs_restart is True


class _StubResponse:
    def __init__(self, status: int = 200, payload: object | None = None) -> None:
        self.status = status
        self.payload = payload

    def raise_for_status(self) -> None:
        import httpx

        if self.status >= 400:
            request = httpx.Request("GET", "https://pypi.org/pypi/zettelekasten/json")
            raise httpx.HTTPStatusError("bad", request=request, response=httpx.Response(self.status, request=request))

    def json(self) -> object:
        return self.payload


def _stub_httpx(monkeypatch: pytest.MonkeyPatch, steps: list[object]) -> list[object]:
    """Replace the HTTP client with a script of answers or errors, and record its timeouts."""
    import httpx

    timeouts: list[object] = []

    class Client:
        def __init__(self, *, timeout: object, follow_redirects: bool) -> None:
            timeouts.append(timeout)

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str) -> _StubResponse:
            step = steps.pop(0)
            if isinstance(step, BaseException):
                raise step
            return step  # type: ignore[return-value]

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    return timeouts


async def test_a_slow_link_gets_time_and_a_second_try(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from zett.infra.updates.pypi import PypiClient

    good = _StubResponse(payload={"info": {"version": "0.0.9"}})
    timeouts = _stub_httpx(monkeypatch, [httpx.ConnectTimeout(""), good])
    assert await PypiClient().latest_version() == "0.0.9"

    # More than the ten seconds a slow TLS handshake can take on its own.
    assert len(timeouts) == 2
    assert all(isinstance(t, httpx.Timeout) and (t.read or 0) >= 30 and (t.connect or 0) >= 15 for t in timeouts)


async def test_an_unreachable_index_is_named_even_when_the_error_has_no_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from zett.infra.updates.pypi import PypiClient

    # `str(httpx.ConnectTimeout(""))` is empty: the settings dialog used to read "PyPI lookup failed: ".
    _stub_httpx(monkeypatch, [httpx.ConnectTimeout(""), httpx.ConnectTimeout("")])
    with pytest.raises(PypiError, match="ConnectTimeout"):
        await PypiClient().latest_version()

    # An answer from the index is not retried: asking again returns the same status.
    steps: list[object] = [_StubResponse(status=503), _StubResponse(payload={"info": {"version": "9"}})]
    _stub_httpx(monkeypatch, steps)
    with pytest.raises(PypiError, match="HTTPStatusError"):
        await PypiClient().latest_version()
    assert len(steps) == 1


def test_restart_route_hands_the_request_to_the_runtime_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from zett.schemas import UpdateRestartResult

    class StubRuntime:
        async def request_restart(self) -> UpdateRestartResult:
            return UpdateRestartResult(ok=False, detail="This server was not started with `zett start`")

    monkeypatch.setattr(update_routes, "RuntimeService", StubRuntime)
    with TestClient(app) as client:
        answer = client.post("/api/updates/restart")
    assert answer.status_code == 200
    assert answer.json() == {"ok": False, "detail": "This server was not started with `zett start`"}


def test_update_routes_answer_and_surface_the_installer(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubService:
        async def status(self, *, refresh: bool = False) -> UpdateStatus:
            return UpdateStatus(
                current="0.0.1",
                latest="0.0.2",
                update_available=True,
                can_install=True,
                detail="uv tool",
            )

        async def install(self, version: str) -> UpdateInstallResult:
            return UpdateInstallResult(ok=True, version=version)

    monkeypatch.setattr(update_routes, "update_service", StubService())
    with TestClient(app) as client:
        status = client.get("/api/updates")
        assert status.status_code == 200
        assert status.json()["update_available"] is True
        assert status.json()["can_install"] is True

        installed = client.post("/api/updates/install", json={"version": "0.0.2"})
        assert installed.status_code == 200
        assert installed.json()["ok"] is True
        assert installed.json()["version"] == "0.0.2"

        assert client.post("/api/updates/install", json={"version": ""}).status_code == 422
