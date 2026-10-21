"""Zett's own file and shell tools.

zett-agent ships a bundle (``CodingExtension``) that pairs ``read_file`` with
``view_image``: one tool for text, another for an image. Its ``read`` tool does
both, detecting an image from its signature, so Zett registers that one tool and
offers no second way to look at a file.

The tools operate with the host process's permissions in the working directory.
They are a capability bundle, not a sandbox.
"""

from pathlib import Path

from zett_agent.agent import AgentRunContext
from zett_agent.extensions.base import AgentExtension
from zett_agent.messages import SystemMessage
from zett_agent.tools.coding import bash, delete_file, edit, glob, grep, read, read_file, write_file


class FileToolsExtension(AgentExtension):
    """Register Zett's file tools.

    ``read`` covers text and a local image, which only helps a model that reads
    images. For a text-only model the extension offers ``read_file`` instead, so
    the model is never handed pixels it cannot use.
    """

    def __init__(self, *, multimodal: bool = True) -> None:
        self.multimodal = multimodal

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register one request-scoped set of file tools."""
        context.register_tool(read if self.multimodal else read_file)
        context.register_tool(glob)
        context.register_tool(grep)
        context.register_tool(write_file)
        context.register_tool(edit)
        context.register_tool(delete_file)
        context.register_tool(bash)

    async def on_state(self, context: AgentRunContext) -> None:
        """Name the directory every relative path and shell command resolves from."""
        message = SystemMessage(content=_working_directory_instructions(Path.cwd().resolve(), self.multimodal))
        instructions = [item for item in context.state.messages if isinstance(item, SystemMessage)]
        context.add_message(message, index=len(instructions))


_READ_NOTE = "`read` returns a text line range or, for a PNG, JPEG, GIF, or WebP file, the image itself."
_READ_FILE_NOTE = "`read_file` returns a line range of a UTF-8 text file; this model cannot read images."


def _working_directory_instructions(working_directory: Path, multimodal: bool) -> str:
    """Describe the path base shared by the file tools and shell commands.

    The text is identical on every turn of one session — it names a location,
    not a snapshot — so it extends the prompt-cache prefix instead of rebuilding
    it.
    """
    return (
        "# Filesystem environment\n"
        f'Current working directory: "{working_directory}".\n'
        "Relative filesystem paths are resolved from this directory. Absolute paths are also allowed.\n"
        f"{_READ_NOTE if multimodal else _READ_FILE_NOTE}\n"
        "Shell commands run from this directory."
    )


__all__ = ["FileToolsExtension"]
