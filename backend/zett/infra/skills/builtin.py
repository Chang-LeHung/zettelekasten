"""Built-in Agent Skills that Zett provisions below the configured skill root.

The artifact body syntax lives here instead of inside tool docstrings: a tool
docstring is part of every request, while a skill enters context only when the
model calls ``read_skill``. The content is fixed in code, so startup can write a
missing skill file and a user edit is never overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKILL_FILE_NAME = "SKILL.md"

#: Name advertised to the model; guidelines must use exactly this value.
ARTIFACT_SYNTAX_SKILL_NAME = "zett-artifact-syntax"

ARTIFACT_SYNTAX_SKILL = """---
name: zett-artifact-syntax
description: Exact body syntax for Zett artifacts. Read before creating or updating a card, article, image, slide deck, or LaTeX PDF artifact.
---

# Zett artifact syntax

Every artifact body is Markdown with the extensions below. These rules are exact:
a separator or marker that differs by one character changes how the artifact renders.

## Markdown shared by cards, articles, and slides

- Use '# Title', '## Section', and '### Subsection' for structure.
- Use '**important**' sparingly, and '- item' for lists.
- Quote with '> quoted text'. Prefix every quoted paragraph with '>' and use '>>' for nested quotes.
- Use single backticks for inline code and triple-backtick fences with a language such as python, cpp, or rust.
- Use '$x^2$' for inline math. Put a standalone '$$' line before and after display math; add no rules or backgrounds.
- Put Mermaid source in a triple-backtick fence labeled 'mermaid'; the UI renders the diagram.
- Use pipe tables with a header separator such as '| --- | --- |' and keep columns short.
- Place each figure alone in a paragraph: '![descriptive alt text](image-url "Caption")'.
- Figure captions come from the optional image title, falling back to alt text, and the UI adds 'Figure N:' itself. Never number figures manually and never repeat a caption below the figure. Inline images get no caption.
- Use an accessible image URL, never a local filesystem path, and never invent an image or asset URL.
- Prefer Markdown. For custom layout, raw HTML with inline Grid/Flex styles is supported; scripts, event handlers, global style tags, and fixed overlays are blocked.
- Write HTML directly, not inside a code fence, and use HTML tags for formatting inside an HTML block. Separate Markdown blocks with blank lines.

## Card

- A card contains exactly one idea; use the fewest words that preserve its meaning.
- Keep the title, summary, and body simple, direct, and brief.

## Article

- An article is long-form Markdown; use the shared rules above, and add an optional subtitle when it helps.
- Prefer one idea per section and keep paragraphs short enough to read on a phone.

## Image

- Describe the image with 'prompt' and 'alt_text'; the alt text is what accessibility tooling reads.
- Reference the image with exactly one location: 'source_url' for an external or data URL, or 'asset_path' for an ObjectKey that already exists in storage.

## Slides

Page structure:

- Use an exact '---' line between horizontal sections and an exact '--' line between vertically related pages inside one section.
- Separators must be unpadded; never use a standalone '--' or '---' as decoration or code inside a deck.
- A deck needs at least two non-empty pages, and never an empty slide.
- Begin every page, including vertical detail pages, with its own short Markdown heading that names the slide's topic.
- Keep each slide to one idea: a short heading and at most six brief bullets, sized to fit one viewport.
- Start every ordinary horizontal section with a standalone title-only page, then use '--' before its content pages.

Cover pages:

- Cover layout is opt-in: put '<!-- slide:cover -->' alone on the page's first line, outside code fences. The marker is hidden when rendered and is not stored separately.
- Put '# Title' immediately after the marker, then an optional '## Subtitle', a plain author paragraph, an optional '[Link label](https://...)', and optional images. Separate those blocks with blank lines.
- A cover is centered vertically and horizontally with a large title and no title underline; its H2 subtitle is smaller and muted. Author and links stay centered paragraphs, not extracted metadata.
- Cover images keep their proportions in equal-size slots, up to three per row; extra images wrap to the next row. A standalone image gets an automatic Figure caption above it, while several images in one paragraph share a row without captions.
- Use '![Organization](accessible-url)' for a captioned logo, or put several image expressions on one line for a caption-free logo row. Never invent author names, image URLs, or local paths.
- Keep covers brief: this is a preset layout, not automatic pagination. Start the next section with an exact '---' line, and use '--' only when the next page belongs below the cover in the same section.
- A marked cover at the start of a section replaces the generated chapter title page, so do not add a duplicate title-only page. Markdown without a marker never receives the cover preset.

HTML pages:

- For a fully custom page, put '<!-- slide:html -->' alone on the page's first line, then raw HTML such as '<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px"><div><h1>Title</h1><p>Text</p></div><img src="/existing-image.png" style="width:100%;object-fit:contain"></div>'.
- The HTML marker suppresses automatic headings and the generated chapter opener, so write your own heading, spacing, and alignment with HTML tags rather than Markdown syntax, and do not wrap the HTML in a code fence.

Both markers:

- The markers select presentation only; the whole page stays in the existing Markdown content field. Do not use JSON metadata and never combine both markers on one page.

## LaTeX PDF

- A LaTeX PDF artifact stores only a reference: the server-assigned 'project_path' and the compiled 'pdf_name'.
- Create it with 'create_artifact(content={"artifact_type": "latex_pdf", "pdf_name": "paper.pdf"})'; the returned 'project_path' is an object key below the storage root and is authoritative.
- Write the sources into that directory, compile the returned 'pdf_name' there, and keep the project committed, because saving the artifact is refused while the project is not a clean git repository.
- The preview reads the compiled PDF bytes from 'project_path/pdf_name'; a missing or invalid PDF leaves the artifact metadata intact but previews nothing.

## Saving

- Creation writes content directly. Later updates stage a draft, and only the user's save publishes it.
- Never claim an artifact is saved unless the user saves it.
"""


@dataclass(frozen=True, slots=True)
class BuiltinSkill:
    """One skill Zett can write into a skill root."""

    name: str
    content: str


BUILTIN_SKILLS = (BuiltinSkill(name=ARTIFACT_SYNTAX_SKILL_NAME, content=ARTIFACT_SYNTAX_SKILL),)


def install_builtin_skills(root: Path) -> tuple[Path, ...]:
    """Write every missing built-in skill below one skill root.

    Existing files are left untouched, so an idempotent startup never rewrites a
    skill the user edited. Returns the paths that were written.
    """
    written: list[Path] = []
    for skill in BUILTIN_SKILLS:
        path = root / skill.name / SKILL_FILE_NAME
        if path.is_file():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(skill.content, encoding="utf-8")
        written.append(path)
    return tuple(written)


__all__ = [
    "ARTIFACT_SYNTAX_SKILL",
    "ARTIFACT_SYNTAX_SKILL_NAME",
    "BUILTIN_SKILLS",
    "BuiltinSkill",
    "install_builtin_skills",
]
