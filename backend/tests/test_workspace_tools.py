import pytest

from zett.agent.workspace_tools import WorkspaceTools
from zett.infra.agent_session_dao import agent_session_storage
from zett.schemas import AgentSessionCreate


def test_workspace_tools_read_write_edit_search_and_execute_command() -> None:
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    tools = WorkspaceTools(session_id)

    assert tools.write_file("/notes/design.md", "snapshot and raw log")["bytes_written"] == 20
    assert tools.read_file("/notes/design.md")["content"] == "snapshot and raw log"
    assert tools.edit_file("/notes/design.md", "raw log", "WAL")["replacements"] == 1
    assert tools.grep("snapshot", "/notes")["matches"]
    assert "/notes/design.md" in tools.glob("**/*.md")["matches"]
    command = tools.execute_shell("wc -w notes/design.md")
    assert command["exit_code"] == 0
    assert "3" in command["stdout"]


@pytest.mark.parametrize(
    "command",
    ["cat /etc/passwd", "ls ..", "ls | head", "sh -c pwd", "rg --pre cat token", "grep -f /etc/passwd data"],
)
def test_workspace_shell_rejects_unsafe_commands(command: str) -> None:
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    tools = WorkspaceTools(session_id)

    with pytest.raises(ValueError):
        tools.execute_shell(command)
