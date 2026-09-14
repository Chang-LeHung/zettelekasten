"""Zett-specific artifact tools and conversation context."""

import asyncio
import json

from zett_agent import AgentExtension, AgentRunContext, SystemMessage, tool

from ..infra.dao import artifact_storage
from ..models import ArtifactListOptions
from ..schemas import AgentArtifact, AgentArtifactWrite, ArtifactContent, ArtifactCreateContent, ArtifactStatus


class ZettelkastenExtension(AgentExtension):
    """Expose typed artifact operations and current artifacts to the model."""

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register artifact tools bound to the current conversation."""
        session_id = context.config.session_id

        @tool
        def create_artifact(content: ArtifactCreateContent, raw_content: str | None = None) -> AgentArtifact:
            """Create a draft card, article, image, slide deck, or LaTeX PDF in this conversation.

            Args:
                content: Complete type-specific artifact content.
                raw_content: Optional original user text represented by the artifact.

            Snippet:
                create_artifact(content={"artifact_type": "card", "title": "...", "content": "..."})
                create_artifact(content={"artifact_type": "latex_pdf", "pdf_name": "paper.pdf"})
                create_artifact(content={"artifact_type": "slides", "title": "...", "content": "# Topic\n\n--\n\n## Detail\n\n---\n\n# Next topic"})
                create_artifact(content={"artifact_type": "slides", "title": "Processes", "content": "<!-- slide:cover -->\\n# Processes\\n\\n## From programs to execution\\n\\nAuthor name\\n\\n[Website](https://example.com)\\n\\n---\\n# Overview\\n\\n--\\n## Process state\\n\\n- One idea"})

            Guidelines:
                - Create an artifact only when it is a useful output of the conversation.
                - To start a LaTeX project, call create_artifact(content={"artifact_type": "latex_pdf", "pdf_name": "paper.pdf"}). Do not supply project_path, title, summary, or source text.
                - Creation allocates a project directory and returns content.project_path. Treat that returned path as authoritative: never guess it, hard-code a root, or reconstruct it from the session ID or PDF name.
                - After creation, use filesystem/shell tools to write all project sources and dependencies inside the returned project_path. Compile there and produce the returned pdf_name directly inside that directory.
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
                update_artifact(artifact_id="...", content={"artifact_type": "slides", "title": "Processes", "content": "<!-- slide:cover -->\\n# Processes\\n\\n## Optional subtitle\\n\\nAuthor name\\n\\n---\\n# Overview\\n\\n--\\n## Details\\n\\n- One idea"})

            Guidelines:
                - Read the artifact information already present in context before replacing it.
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
