"""Built-in skills are written into the user skill root and stay discoverable."""

from pathlib import Path

from fastapi.testclient import TestClient
from zett_agent import SkillFileParser

from zett.agent import config as agent_config
from zett.agent import extensions as agent_extensions
from zett.infra.skills import builtin
from zett.main import app


def skill_path(root: Path) -> Path:
    return root / builtin.ARTIFACT_SYNTAX_SKILL_NAME / builtin.SKILL_FILE_NAME


def test_install_writes_a_discoverable_artifact_syntax_skill(tmp_path: Path) -> None:
    written = builtin.install_builtin_skills(tmp_path)

    assert written == (skill_path(tmp_path),)
    parsed = SkillFileParser().parse(skill_path(tmp_path))
    assert parsed is not None
    assert parsed.name == builtin.ARTIFACT_SYNTAX_SKILL_NAME
    assert "artifact" in parsed.description


def test_install_keeps_an_existing_skill_file_untouched(tmp_path: Path) -> None:
    edited = skill_path(tmp_path)
    edited.parent.mkdir(parents=True)
    edited.write_text("---\nname: zett-artifact-syntax\ndescription: Mine.\n---\nMine.", encoding="utf-8")

    assert builtin.install_builtin_skills(tmp_path) == ()
    assert edited.read_text(encoding="utf-8").endswith("Mine.")


def test_skill_body_covers_every_artifact_type() -> None:
    for heading in ("## Markdown", "## Card", "## Article", "## Image", "## Slides", "## LaTeX PDF"):
        assert heading in builtin.ARTIFACT_SYNTAX_SKILL
    for rule in ("<!-- slide:cover -->", "<!-- slide:html -->", "'---'", "'--'"):
        assert rule in builtin.ARTIFACT_SYNTAX_SKILL


def test_startup_provisions_the_skill_before_serving(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "skills"
    monkeypatch.setattr(agent_config, "DEFAULT_ZETT_SKILL_ROOTS", (str(root),))

    with TestClient(app):
        # Startup is the only writer; the request itself must not be needed.
        assert skill_path(root).is_file()


def test_artifact_guidelines_point_at_the_installed_skill() -> None:
    source = Path(agent_extensions.artifacts.__file__).read_text(encoding="utf-8")

    # Both artifact tools must send the model to the skill instead of restating its rules.
    assert source.count(builtin.ARTIFACT_SYNTAX_SKILL_NAME) == 2
    assert builtin.ARTIFACT_SYNTAX_SKILL_NAME in builtin.ARTIFACT_SYNTAX_SKILL
