"""Zett-specific artifact tools and conversation context."""

import asyncio
import json

from zett_agent import AgentExtension, AgentRunContext, SystemMessage, tool

from ..infra.dao import artifact_storage
from ..models import ArtifactListOptions
from ..schemas import AgentArtifact, AgentArtifactWrite, ArtifactContent, ArtifactStatus


class ZettelkastenExtension(AgentExtension):
    """Expose typed artifact operations and current artifacts to the model."""

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register artifact tools bound to the current conversation."""
        session_id = context.config.session_id

        @tool
        def create_artifact(content: ArtifactContent, raw_content: str | None = None) -> AgentArtifact:
            """Create a draft card, article, image, or slide deck in this conversation.

            Args:
                content: Complete type-specific artifact content.
                raw_content: Optional original user text represented by the artifact.

            Snippet:
                create_artifact(content={"artifact_type": "card", "title": "...", "content": "..."})
                create_artifact(content={"artifact_type": "slides", "title": "...", "content": "# Topic\n\n--\n\n## Detail\n\n---\n\n# Next topic"})

            Guidelines:
                - Create an artifact only when it is a useful output of the conversation.
                - Keep newly generated artifacts in draft state until the user asks to save them.
                - A card contains one idea; use the fewest words that preserve its meaning.
                - Keep card titles, summaries, and bodies simple, direct, and brief.
                - Use Markdown, not raw HTML or CSS. Separate paragraphs and block elements with blank lines.
                - Use '# Title', '## Section', and '### Subsection'; use '**important**' sparingly and '- item' for lists.
                - Quote with '> quoted text'; prefix each quoted paragraph with '>' and use '>>' for nested quotes.
                - Place each figure alone in a paragraph: '![descriptive alt text](image-url "Caption")'.
                - Figure captions use the optional image title, falling back to alt text; the UI adds 'Figure N:' automatically.
                - Do not manually number figures or repeat captions below them. Inline images do not receive figure captions.
                - Use an accessible image URL, never a local filesystem path; do not invent image or asset URLs.
                - Use '$x^2$' for inline math and a standalone '$$' line before and after display math; do not add rules or backgrounds.
                - Use single backticks for inline code and triple-backtick fences with a language such as python, cpp, or rust.
                - Put Mermaid source in a triple-backtick fence labeled 'mermaid'; the UI renders the diagram.
                - Use pipe tables with a header separator such as '| --- | --- |'; keep columns short and readable.
                - For slides, use an exact '---' line between horizontal sections.
                - Use an exact '--' line for vertically related slides inside the same section.
                - Slide separators must have no surrounding spaces. Do not use standalone '--' or '---' as decoration or code inside a deck.
                - A slide deck must contain at least two non-empty pages.
                - Begin every page, including vertical pages, with its own concise Markdown heading.
                - Start each horizontal section with a title-only page; place its content below using '--'.
                - Keep each slide concise: one idea, a short heading, and no more than six brief bullets.
            """
            return artifact_storage.create(
                AgentArtifactWrite(session_id=session_id, content=content, raw_content=raw_content)
            )

        @tool
        def update_artifact(artifact_id: str, content: ArtifactContent) -> AgentArtifact:
            """Replace the editable content of an existing conversation artifact.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.
                content: Complete replacement content.

            Snippet:
                update_artifact(artifact_id="...", content={"artifact_type": "article", "title": "..."})

            Guidelines:
                - Read the artifact information already present in context before replacing it.
                - Keep cards focused on one idea and remove every word that does not add meaning.
                - Use Markdown, not raw HTML or CSS; separate paragraphs, lists, and blocks with blank lines.
                - Use '# Title', '## Section', '### Subsection', '**important**', and '- item' for structure.
                - Use '> quoted text' for quotations and '>>' for nested quotes; the UI supplies the quote styling.
                - Put each figure alone in a paragraph: '![descriptive alt text](image-url "Caption")'.
                - The UI adds 'Figure N:' using the image title or alt text; never manually number or duplicate captions.
                - Inline images have no figure caption. Preserve accessible image URLs; never substitute local paths or invented URLs.
                - Use '$x^2$' for inline math and standalone '$$' lines around display math, without decorative rules or backgrounds.
                - Use single backticks for inline code and triple-backtick fences labeled with the code language.
                - Mermaid diagrams use a triple-backtick 'mermaid' fence; tables use pipes and a '| --- | --- |' header separator.
                - Preserve strict slide navigation: '---' between sections and '--' within a section.
                - Give every slide its own concise Markdown heading.
                - Each horizontal section begins with a title-only page, followed by '--' and its content pages.
                - Slide separators must be exact unpadded lines; never use standalone '--' or '---' as decoration or code inside a deck.
            """
            current = self._artifact(session_id, artifact_id)
            return artifact_storage.update(
                artifact_id,
                AgentArtifactWrite(
                    session_id=session_id,
                    content=content,
                    raw_content=current.raw_content,
                    status=current.status,
                    metadata=current.metadata,
                ),
            )

        @tool
        def save_artifact(artifact_id: str) -> AgentArtifact:
            """Mark one draft artifact as saved after explicit user approval.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.

            Snippet:
                save_artifact(artifact_id="...")

            Guidelines:
                - Call this only when the user explicitly requests saving the artifact.
            """
            current = self._artifact(session_id, artifact_id)
            return artifact_storage.update(
                artifact_id,
                AgentArtifactWrite(
                    session_id=session_id,
                    content=current.content,
                    raw_content=current.raw_content,
                    status=ArtifactStatus.SAVED,
                    metadata=current.metadata,
                ),
            )

        @tool
        def delete_artifact(artifact_id: str) -> bool:
            """Delete one artifact from this conversation.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.

            Snippet:
                delete_artifact(artifact_id="...")

            Guidelines:
                - Delete only when the user's intent is explicit.
            """
            self._artifact(session_id, artifact_id)
            return artifact_storage.delete(artifact_id)

        for registered in (create_artifact, update_artifact, save_artifact, delete_artifact):
            context.register_tool(registered)

    async def on_state(self, context: AgentRunContext) -> None:
        """Expose current artifacts as model context."""
        session_id = context.config.session_id
        artifacts = await asyncio.to_thread(
            artifact_storage.list,
            ArtifactListOptions(session_id=session_id, limit=500),
        )
        payload = {
            "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
        }
        if payload["artifacts"]:
            workspace = SystemMessage(
                content="Current Zett conversation workspace:\n" + json.dumps(payload, ensure_ascii=False)
            )
            instructions = [item for item in context.state.messages if isinstance(item, SystemMessage)]
            dialogue = [item for item in context.state.messages if not isinstance(item, SystemMessage)]
            context.state.messages[:] = [*instructions, workspace, *dialogue]

    @staticmethod
    def _artifact(session_id: str, artifact_id: str) -> AgentArtifact:
        artifact = artifact_storage.get_for_session(session_id, artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact not found in this session: {artifact_id}")
        return artifact
