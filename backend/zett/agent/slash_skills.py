"""Expose local SKILL.md files as container-registered slash commands."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from zett_agent import AgentEvent, ImageContent, SkillExtension, TextContent, UserMessage

from ..messages import MessagePartCodec
from .slash import SlashCommandInvocation, ZettelkastenContainer

_CODEC = MessagePartCodec()


class SkillSlashCommandExtension:
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
        """Build one handler that sends the skill instructions to the Agent."""

        async def handler(
            container: ZettelkastenContainer,
            invocation: SlashCommandInvocation,
        ) -> AsyncIterator[AgentEvent]:
            try:
                instructions = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise ValueError(f"Skill is no longer readable: {path.name}") from error
            skill_name = path.parent.name
            original_text = invocation.message.text.strip()
            prompt = (
                f"The user invoked the /{skill_name} slash command. That command loaded the "
                f"{skill_name} skill for this turn, so treat the request below as a "
                "skill-driven request instead of an ordinary message.\n\n"
                f"Skill: {skill_name}\n\n"
                "Skill instructions:\n"
                f"{instructions}\n\n"
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
            async for event in container.stream_to_agent(invocation, message=message):
                yield event

        return handler


__all__ = ["SkillSlashCommandExtension"]
