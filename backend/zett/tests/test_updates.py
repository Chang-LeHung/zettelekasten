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


def test_detect_installer_reads_the_environment_that_owns_the_copy(tmp_path: Path) -> None:
    uv_tool = installer_module.detect_installer(prefix=Path("/Users/x/.local/share/uv/tools/zettelekasten"))
    assert uv_tool.command is not None and uv_tool.command[:2] == ("uv", "tool")
    assert "uv tool install" in uv_tool.detail

    pipx = installer_module.detect_installer(prefix=Path("/home/x/.local/pipx/venvs/zettelekasten"))
    assert pipx.command is not None and pipx.command[0] == "pipx"
    assert "pipx" in pipx.detail

    # A checkout looks like `<root>/.git` next to `<root>/backend/pyproject.toml`,
    # with the imported package at `<root>/backend/zett`.
    checkout = tmp_path / "backend" / "zett"
    checkout.mkdir(parents=True)
    (tmp_path / "backend" / "pyproject.toml").write_text("[project]\nname='zettelekasten'\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    source = installer_module.detect_installer(prefix=tmp_path / "venv", package_root=checkout)
    assert source.command is None
    assert "git pull" in source.detail

    pip = installer_module.detect_installer(prefix=tmp_path / "venv", package_root=tmp_path / "site/zett")
    assert pip.can_install
    assert pip.detail.startswith("Installed by pip")


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
