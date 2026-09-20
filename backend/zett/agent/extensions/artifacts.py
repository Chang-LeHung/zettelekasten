"""Zett-specific artifact tools."""

from typing import Annotated

from pydantic import Field
from zett_agent import AgentExtension, AgentRunContext, tool

from ...application.artifact_pruner import AgentArtifactPreview, ArtifactPruner
from ...application.tagging import tag_service
from ...infra.dao import artifact_storage
from ...schemas import (
    AgentArtifactEntity,
    AgentArtifactWrite,
    ArtifactContent,
    ArtifactCreateContent,
    ArtifactListOptions,
)

artifact_pruner = ArtifactPruner()


class ArtifactExtension(AgentExtension):
    """Expose typed artifact operations to the model."""

    # Do not add an on_state() workspace system message. A conversation starts
    # with no artifacts, and later create/update/delete tool calls and results
    # already remain in model context. Rebuilding a full snapshot in the leading
    # system prefix would invalidate prompt-cache prefixes without adding new
    # information the model has not already seen.

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register artifact tools bound to the current conversation."""
        session_id = context.config.session_id

        @tool
        async def create_artifact(
            content: ArtifactCreateContent, raw_content: str | None = None
        ) -> AgentArtifactEntity:
            """Create a draft card, article, image, slide deck, or LaTeX PDF in this conversation.

            Args:
                content: Complete type-specific artifact content.
                raw_content: Optional original user text represented by the artifact.

            Snippet:
                create_artifact(content={"artifact_type": "card", "title": "...", "content": "..."})
                create_artifact(content={"artifact_type": "latex_pdf", "pdf_name": "paper.pdf"})
                create_artifact(content={"artifact_type": "slides", "title": "...", "content": "# Topic\\n\\n--\\n\\n## Detail\\n\\n---\\n\\n# Next topic"})
                create_artifact(content={"artifact_type": "slides", "title": "Processes", "content": "<!-- slide:cover -->\\n# Processes\\n\\n## From programs to execution\\n\\nAuthor name\\n\\n[Website](https://example.com)\\n\\n---\\n# Overview\\n\\n--\\n## Process state\\n\\n- One idea"})

            Guidelines:
                - Create an artifact only when it is a useful output of the conversation.
                - Creation writes draft content only. The user publishes it; never claim an artifact is saved.
                - To start a LaTeX project, call create_artifact(content={"artifact_type": "latex_pdf", "pdf_name": "paper.pdf"}). Do not supply project_path, title, summary, or source text.
                - Creation allocates a project directory and returns content.project_path as an object key relative to ZETT_STORAGE_ROOT. Treat that returned key as authoritative: never guess it or reconstruct it from the session ID or PDF name.
                - Filesystem/shell tools run from the repository directory, so resolve the returned key under `Path.home() / ".zettelekasten"` before writing project sources and compiling the returned pdf_name.
                - Creation, metadata updates, and saving do not require an existing PDF and do not compile automatically. Preserve the returned project_path when updating. Preview becomes available after compilation; deleting the artifact record preserves the project files.
                - Keep newly generated artifacts in draft state until the user asks to save them.
                - A card contains one idea; use the fewest words that preserve its meaning.
                - Keep card titles, summaries, and bodies simple, direct, and brief.
                - Prefer Markdown. For custom layout, raw HTML with inline Grid/Flex styles is supported; scripts, event handlers, global style tags and fixed overlays are blocked.
                - Write HTML directly, not inside a code fence. Inside HTML blocks use HTML tags for text formatting; separate Markdown blocks with blank lines.
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
                - Cover layout is opt-in: put '<!-- slide:cover -->' alone on the first line of the page, outside code fences. The marker is hidden in the rendered slide, not stored separately.
                - Put '# Title' immediately after the marker. Then add optional '## Subtitle', a plain author paragraph, optional '[Link label](https://...)', and optional images; separate these blocks with blank lines.
                - A cover opening a horizontal section is centered vertically and horizontally, with a large title and no title underline. Its H2 subtitle is smaller and muted; author and links remain centered paragraphs, not extracted metadata.
                - Cover images keep their proportions in equal-size slots, up to three per row, wrapping additional images. A standalone image gets an automatic Figure caption above it; multiple images in one paragraph have no automatic captions.
                - Use '![Organization](accessible-url)' for a captioned logo, or place several image expressions on one line for a caption-free logo row. Never invent author names, image URLs, or local file paths.
                - Keep covers brief; this is a preset layout, not automatic pagination. Start the next section with an exact '---' line; use '--' only when the next page belongs below the cover in the same section.
                - A marked cover at a section's start replaces the generated chapter title page; do not add a duplicate title-only page. Unmarked Markdown never receives the cover preset.
                - For a fully custom page, put '<!-- slide:html -->' alone on its first line, followed by raw HTML such as '<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px"><div><h1>Title</h1><p>Text</p></div><img src="/existing-image.png" style="width:100%;object-fit:contain"></div>'.
                - The HTML marker suppresses automatic headings and a generated chapter opener. Write your own heading, spacing and alignment; use HTML tags inside HTML blocks, not Markdown syntax. Do not wrap the HTML in a code fence.
                - Both markers select presentation only: the entire page stays in the existing Markdown content field. Do not use JSON metadata or combine both markers on one page.
                - Use an exact '--' line for vertically related slides inside the same section.
                - Slide separators must have no surrounding spaces. Do not use standalone '--' or '---' as decoration or code inside a deck.
                - A slide deck must contain at least two non-empty pages.
                - Give ordinary and cover pages a concise Markdown heading (after the marker for covers); HTML pages supply their own HTML heading.
                - Ordinary horizontal sections start with a title-only page followed by '--' and content pages; explicit cover or HTML openers are exceptions.
                - Keep each slide concise: one idea, a short heading, and no more than six brief bullets.
            """
            created = await artifact_storage.create(
                AgentArtifactWrite(session_id=session_id, draft_content=content, raw_content=raw_content)
            )
            return await tag_service.sync_confirmed_suggestions(created)

        @tool
        async def get_artifact(artifact_id: str) -> AgentArtifactEntity:
            """Return one artifact with its published content and its draft.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.

            Snippet:
                get_artifact(artifact_id="...")

            Guidelines:
                - Use to fetch the latest content of an artifact after changes.
                - `content` is what the user published; `draft_content` is the working copy you edit, and the two are equal right after a save.
            """
            return await self._artifact(session_id, artifact_id)

        @tool
        async def query_artifacts(
            query: str | None = None,
            artifact_types: tuple[str, ...] = (),
            statuses: tuple[str, ...] = (),
            all_sessions: bool = False,
            limit: Annotated[int, Field(ge=1, le=500)] = 20,
        ) -> list[AgentArtifactPreview]:
            """Search artifacts by title text, type, and status.

            Every result carries both sides of the artifact: `published_content`
            is what the user saved and `draft_content` is the current working
            copy, which equals the published content right after a save.

            Args:
                query: Case-insensitive text matched against artifact titles.
                artifact_types: Optional kinds such as card, article, image, slides, or latex_pdf.
                statuses: Optional lifecycle states such as draft or saved.
                all_sessions: When true, search across every session instead of only this conversation.
                limit: Maximum number of artifacts to return.

            Snippet:
                query_artifacts(query="paper", statuses=["saved"])
                query_artifacts(artifact_types=["card"], all_sessions=True)

            Guidelines:
                - Use to find artifacts in this conversation before reading or updating them.
                - Set all_sessions to search the entire library, for example when the user asks about artifacts from other conversations.
                - Current conversation artifact previews are already in context; query narrows by title, type, or state.
                - Query results contain bounded content previews. Call get_artifact before updating when the complete content is needed.
            """
            artifacts = await artifact_storage.list(
                ArtifactListOptions(
                    session_id=None if all_sessions else session_id,
                    artifact_types=artifact_types,
                    statuses=statuses,
                    query=query,
                    limit=limit,
                )
            )
            return artifact_pruner.prune(artifacts)

        @tool
        async def update_artifact(artifact_id: str, content: ArtifactContent) -> AgentArtifactEntity:
            """Replace the draft content of an existing conversation artifact.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.
                content: Complete replacement draft content.

            Snippet:
                update_artifact(artifact_id="...", content={"artifact_type": "article", "title": "..."})
                update_artifact(artifact_id="...", content={"artifact_type": "slides", "title": "Processes", "content": "<!-- slide:cover -->\\n# Processes\\n\\n## Optional subtitle\\n\\nAuthor name\\n\\n---\\n# Overview\\n\\n--\\n## Details\\n\\n- One idea"})

            Guidelines:
                - Call get_artifact to read the complete artifact before replacing its draft.
                - Updates write draft content only. The published artifact is untouched until the user saves.
                - Keep cards focused on one idea and remove every word that does not add meaning.
                - Markdown and sanitized raw HTML with inline Grid/Flex styles are supported; no scripts, global style tags or fixed overlays. HTML code fences display source only.
                - Use '# Title', '## Section', '### Subsection', '**important**', and '- item' for structure.
                - Use '> quoted text' for quotations and '>>' for nested quotes; the UI supplies the quote styling.
                - Put each figure alone in a paragraph: '![descriptive alt text](image-url "Caption")'.
                - The UI adds 'Figure N:' using the image title or alt text; never manually number or duplicate captions.
                - Inline images have no figure caption. Preserve accessible image URLs; never substitute local paths or invented URLs.
                - Use '$x^2$' for inline math and standalone '$$' lines around display math, without decorative rules or backgrounds.
                - Use single backticks for inline code and triple-backtick fences labeled with the code language.
                - Mermaid diagrams use a triple-backtick 'mermaid' fence; tables use pipes and a '| --- | --- |' header separator.
                - Preserve strict slide navigation: '---' between sections and '--' within a section.
                - Preserve explicit page layouts; never infer a cover from ordinary prose. Put exactly one marker, '<!-- slide:cover -->' or '<!-- slide:html -->', alone on the page's first line and outside code fences.
                - Cover syntax: marker, '# Title', optional '## Subtitle', plain author paragraph, optional '[Link label](url)', then optional '![Organization](url)' images. Separate blocks with blank lines; all content stays Markdown, not separate fields.
                - At a section opener, the cover preset centers the page vertically and horizontally: large title without an underline, smaller muted H2 subtitle, centered author and links. Preserve this hierarchy instead of using H2 for the author.
                - Cover images use equal-size, uncropped slots, up to three per row with wrapping. Standalone images have automatic Figure captions above them; several images on one line make a row without automatic captions.
                - Keep covers concise and preserve real authors and accessible image URLs. Use '---' after the cover for a new horizontal section, or '--' for a related vertical page.
                - A marked cover or HTML opener replaces the generated section title page. Do not prepend another title-only page or add a marker unless the user wants that layout.
                - HTML pages use raw tags and inline Grid/Flex styles after '<!-- slide:html -->', with their own HTML heading and spacing. They get no automatic heading or cover styling; fenced HTML remains visible source, not rendered layout.
                - Ordinary pages retain Markdown headings and ordinary horizontal sections retain title-only openers followed by '--' and content. These rules do not add extra headings or openers to explicit HTML or cover pages.
                - Slide separators must be exact unpadded lines; never use standalone '--' or '---' as decoration or code inside a deck.
            """
            current = await self._artifact(session_id, artifact_id)
            updated = await artifact_storage.update(
                artifact_id,
                AgentArtifactWrite(
                    session_id=session_id,
                    content=current.content,
                    draft_content=content,
                    raw_content=current.raw_content,
                    status=current.status,
                    metadata=current.metadata,
                ),
            )
            return await tag_service.sync_confirmed_suggestions(updated)

        @tool
        async def delete_artifact(artifact_id: str) -> bool:
            """Delete one artifact from this conversation.

            Args:
                artifact_id: Stable ID of an artifact in this conversation.

            Snippet:
                delete_artifact(artifact_id="...")

            Guidelines:
                - Delete only when the user's intent is explicit.
            """
            await self._artifact(session_id, artifact_id)
            return await artifact_storage.delete(artifact_id)

        for registered in (
            create_artifact,
            get_artifact,
            query_artifacts,
            update_artifact,
            delete_artifact,
        ):
            context.register_tool(registered)

    @staticmethod
    async def _artifact(session_id: str, artifact_id: str) -> AgentArtifactEntity:
        artifact = await artifact_storage.get_for_session(session_id, artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact not found in this session: {artifact_id}")
        return artifact
