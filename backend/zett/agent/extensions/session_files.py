"""Name the directory that holds one conversation's submitted files."""

from zett_agent import AgentExtension, AgentRunContext, SystemMessage

from ...application.files.object_store import session_directory_key
from ...infra.files.object_store import get_object_store


class SessionFilesExtension(AgentExtension):
    """Inject the stable location of the conversation's own uploaded files.

    Images and other files submitted with a message are also written below the
    session directory, which gives the model a path it can hand to
    ``view_image``, a LaTeX build, or a shell command. Those tools need an
    absolute path: the files live under ``storage_root`` rather than the working
    directory the filesystem tools otherwise start from.

    Only the directory is named. The text is byte-identical on every turn of one
    session, so it extends the leading system prefix instead of invalidating it.
    Which files exist, and how they are named, is deliberately left out even
    though it would read helpfully: that is per-turn information, so describing
    it would rebuild the prefix whenever the user submits another image, and it
    would break again the day the naming scheme changes. The filesystem tools
    answer the same question on demand.
    """

    async def on_state(self, context: AgentRunContext) -> None:
        """Place the session directory after existing system instructions."""
        state = context.state
        message = SystemMessage(content=self._session_files_instructions(context))
        instructions = [item for item in state.messages if isinstance(item, SystemMessage)]
        context.add_message(message, index=len(instructions))

    def _session_files_instructions(self, context: AgentRunContext) -> str:
        """Describe where this conversation's submitted images and files live."""
        directory = get_object_store().resolve(session_directory_key(context.config.session_id))
        return (
            "# Session files\n"
            f'Images and other files submitted with this conversation are stored under "{directory}".\n'
            "Read those paths with the filesystem tools when a task needs the file rather than the pixels."
        )


__all__ = ["SessionFilesExtension"]
