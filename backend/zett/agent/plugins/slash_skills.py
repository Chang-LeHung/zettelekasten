"""Expose local SKILL.md files as container-registered slash commands."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from zett_agent.events import (
    AgentEvent,
)
from zett_agent.extensions.skill import (
    READ_SKILL_TOOL_NAME,
    SkillExtension,
)
from zett_agent.messages import (
    ImageContent,
    TextContent,
    UserMessage,
)

from ...messages import MessagePartCodec
from ..container import ZettelkastenContainer, ZettelkastenExt
from ..slash import SlashCommandInvocation

_CODEC = MessagePartCodec()


class SkillSlashCommandExtension(ZettelkastenExt):
    """Register one slash command for every valid local Agent Skill."""

    name = "skills"

    def __init__(self, roots: Sequence[str | Path]) -> None:
        self._roots = tuple(roots)

    async def register(self, container: ZettelkastenContainer) -> None:
        """Discover current skills and register their slash command handlers."""
        for skill in SkillExtension(self._roots).skills:
            container.register_slash_command(
                owner=self.name,
                name=skill.name,
                description=skill.description,
                command_type="skill",
                handler=self._handler(skill.path),
            )

    @staticmethod
    def _handler(path: Path):
        """Build one handler that points the Agent at the skill it must load."""

        async def handler(invocation: SlashCommandInvocation) -> AsyncIterator[AgentEvent]:
            if not path.is_file():
                raise ValueError(f"Skill is no longer readable: {path.name}")
            skill_name = path.parent.name
            original_text = invocation.message.text.strip()
            prompt = (
                f"The user invoked the /{skill_name} slash command, which selects the {skill_name} skill "
                f"for this turn. Its instructions are not included here: call `{READ_SKILL_TOOL_NAME}` with "
                f"`{skill_name}` only when you need them, and follow the returned instructions.\n\n"
                "User request:\n"
                f"{original_text}"
            )
            parts = [
                TextContent(prompt),
                *(part for part in invocation.message.parts if isinstance(part, ImageContent)),
            ]
            message = UserMessage(
                content=parts,
                # The Raw Log keeps the expanded prompt that the model actually
                # read; raw_parts preserves the whole original user message,
                # including images, so the conversation UI can render it back.
                attributes={
                    "slash_command": {
                        "name": skill_name,
                        "type": "skill",
                        "raw_parts": [part.model_dump() for part in _CODEC.to_front_parts(invocation.message.parts)],
                    }
                },
            )
            async for event in invocation.prompt(message=message):
                yield event

        return handler


__all__ = ["SkillSlashCommandExtension"]
