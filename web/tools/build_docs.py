#!/usr/bin/env python3
"""Render the Markdown documentation into the site's own HTML pages.

This replaces a static-site theme: the pages use the same tokens, header, and
typography as the landing page in ``web/``, and nothing about the output is
theme-specific. Run it through ``uv`` so the Markdown dependencies are present:

    uv run --project backend python web/tools/build_docs.py

It writes ``site/docs/`` (one directory per page, Material-style URLs), a search
index at ``site/docs/search.json``, and the two Pygments themes at
``site/styles/pygments.css``. ``make site`` runs it together with the landing
page copy.
"""

from __future__ import annotations

import html
import json
import posixpath
import re
import shutil
from pathlib import Path

import markdown
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import ClassNotFound, get_lexer_by_name

REPO = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO / "docs"
SITE_DIR = REPO / "site"
OUT_DIR = SITE_DIR / "docs"
STYLES_DIR = SITE_DIR / "styles"

#: Source of truth for the site navigation: (section, [(label, source file)]).
NAV: list[tuple[str, list[tuple[str, str]]]] = [
    ("", [("Overview", "index.md")]),
    (
        "User guide",
        [
            ("Conversations", "guide/conversations.md"),
            ("Artifacts and the library", "guide/artifacts.md"),
            ("Assets", "guide/assets.md"),
            ("Scheduled tasks", "guide/scheduled-tasks.md"),
            ("Channels", "guide/channels.md"),
            ("Settings and local data", "guide/settings.md"),
        ],
    ),
    (
        "Developer guide",
        [
            ("Plugins", "plugins/index.md"),
            ("Agent plugins", "plugins/agent-plugins.md"),
            ("Channel plugins", "plugins/channel-plugins.md"),
        ],
    ),
    (
        "Reference",
        [
            ("Backend", "backend.md"),
            ("agim SDK", "agim.md"),
            ("WeChat channel plugin", "weixin.md"),
        ],
    ),
]

URL_SCHEME = re.compile(r"^(?:[a-z]+:|#|/)", re.I)
FENCE = re.compile(r"^(`{3,}|~{3,})(.*)$")
TAG = re.compile(r"<[^>]+>")


def page_url(source: str) -> str:
    """Return the site URL of one Markdown source, with Material's shape."""
    stem = source[: -len(".md")] if source.endswith(".md") else source
    if stem in ("index", ""):
        return "/docs/"
    if stem.endswith("/index"):
        return f"/docs/{stem[: -len('index')]}"
    return f"/docs/{stem}/"


def render_code_block(code: str, language: str, title: str) -> str:
    """Highlight one fenced block and label it, as raw HTML.

    Markdown has no notion of a fence title, so titled blocks are rendered here
    with Pygments instead of being handed to the Markdown engine.
    """
    try:
        lexer = get_lexer_by_name(language or "text")
    except ClassNotFound:
        lexer = get_lexer_by_name("text")
    body = pygments_highlight(code, lexer, HtmlFormatter(cssclass="highlight"))
    return (
        "\n"
        f'<div class="code-block"><div class="code-block__title">{html.escape(title)}</div>\n{body}</div>\n'
    )


def render_titled_fences(text: str) -> str:
    """Replace ```lang title="x" fences with rendered, titled code blocks."""
    lines = text.splitlines()
    output: list[str] = []
    index = 0

    while index < len(lines):
        match = FENCE.match(lines[index].lstrip())
        title_match = re.search(r'title="([^"]*)"', match.group(2)) if match else None
        if not match or not title_match:
            output.append(lines[index])
            index += 1
            continue

        marker = match.group(1)
        info = match.group(2)
        language = (info[: title_match.start()] + info[title_match.end() :]).strip()
        body: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            closing = FENCE.match(lines[cursor].lstrip())
            if (
                closing
                and closing.group(1)[0] == marker[0]
                and len(closing.group(1)) >= len(marker)
                and not closing.group(2).strip()
            ):
                break
            body.append(lines[cursor])
            cursor += 1

        output.append(
            render_code_block("\n".join(body), language, title_match.group(1))
        )
        index = cursor + 1

    return "\n".join(output)


def rewrite_links(markup: str, source: str) -> str:
    """Resolve links and images against the source file, then rewrite to URLs."""
    source_dir = posixpath.dirname(source)

    def resolve(target: str) -> str:
        return (
            posixpath.normpath(posixpath.join(source_dir, target))
            if source_dir
            else target
        )

    def replace(match: re.Match[str]) -> str:
        attribute, href = match.group(1), match.group(2)
        if URL_SCHEME.match(href):
            return match.group(0)
        path, separator, fragment = href.partition("#")
        if not path:
            return match.group(0)
        # Resolve as-is: stripping a leading "./" would also eat the "../" of a
        # cross-section link and silently point at a page that does not exist.
        target = resolve(path)
        if target.endswith(".md"):
            url = page_url(target)
        else:
            url = f"/docs/{target}"
        if separator:
            url = f"{url}#{fragment}"
        return f'{attribute}="{url}"'

    return re.sub(r'\b(href|src)="([^"]+)"', replace, markup)


def strip_tags(markup: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", markup))).strip()


def render_page(
    *,
    source: str,
    label: str,
    section: str,
    markup: str,
    toc: list[dict],
    repo_url: str,
) -> tuple[str, dict]:
    """Render one documentation page and build its search entry."""
    # Headings carry a permalink anchor; it must not leak into titles or search.
    prose = re.sub(r'<a class="headerlink"[^>]*>.*?</a>', "", markup, flags=re.S)
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", prose, re.S)
    title = strip_tags(title_match.group(1)) if title_match else label

    nav_html: list[str] = []
    for nav_section, pages in NAV:
        if nav_section:
            nav_html.append(
                f'<p class="docs-nav__section">{html.escape(nav_section)}</p>'
            )
        nav_html.append('<ul class="docs-nav__list">')
        for nav_label, nav_source in pages:
            current = nav_source == source
            attributes = (
                ' class="docs-nav__link is-active" aria-current="page"'
                if current
                else ' class="docs-nav__link"'
            )
            nav_html.append(
                f'<li><a href="{page_url(nav_source)}"{attributes}>{html.escape(nav_label)}</a></li>'
            )
        nav_html.append("</ul>")

    toc_html: list[str] = []
    for item in toc:
        toc_html.append(
            f'<li><a class="docs-toc__link" href="#{item["id"]}">{html.escape(item["name"])}</a></li>'
        )
        for child in item.get("children", []):
            toc_html.append(
                f'<li><a class="docs-toc__link is-nested" href="#{child["id"]}">{html.escape(child["name"])}</a></li>'
            )

    order = [page_source for _, pages in NAV for _, page_source in pages]
    index = order.index(source)
    pager_html: list[str] = []
    if index > 0:
        previous = order[index - 1]
        pager_html.append(
            f'<a href="{page_url(previous)}"><span>Previous</span>{html.escape(previous_label(previous))}</a>'
        )
    if index < len(order) - 1:
        following = order[index + 1]
        pager_html.append(
            f'<a class="is-next" href="{page_url(following)}"><span>Next</span>{html.escape(previous_label(following))}</a>'
        )

    shell = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)} · Zett</title>
    <meta name="description" content="{html.escape(strip_tags(markup)[:180])}" />
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="Zett" />
    <meta property="og:title" content="{html.escape(title)} · Zett" />
    <meta property="og:description" content="{html.escape(strip_tags(markup)[:180])}" />
    <meta property="og:url" content="https://chang-lehung.github.io/zettelekasten{page_url(source)}" />
    <meta property="og:image" content="https://chang-lehung.github.io/zettelekasten/assets/og.png" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:image" content="https://chang-lehung.github.io/zettelekasten/assets/og.png" />
    <link rel="icon" href="/assets/favicon.ico" />
    <link rel="stylesheet" href="/styles/tokens.css" />
    <link rel="stylesheet" href="/styles/base.css" />
    <link rel="stylesheet" href="/styles/docs.css" />
    <link rel="stylesheet" href="/styles/pygments.css" />
  </head>
  <body>
    <a class="skip-link" href="#content">Skip to content</a>
    <header class="nav nav--solid">
      <button class="icon-button docs__nav-toggle" type="button" data-docs-nav-toggle aria-label="Toggle navigation" aria-expanded="false">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M4 12h16M4 17h16" stroke-linecap="round" /></svg>
      </button>
      <a class="nav__brand" href="/"><img src="/assets/logo.png" width="26" height="26" alt="" /><span>Zett</span></a>
      <nav class="nav__links" aria-label="Primary">
        <a href="/docs/guide/conversations/">Guide</a>
        <a href="/docs/plugins/">Plugins</a>
        <a href="/docs/">Docs</a>
        <a href="{repo_url}">GitHub</a>
      </nav>
      <div class="nav__actions nav__actions--end">
        <button class="icon-button" type="button" data-search-open aria-label="Search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="6" /><path d="m20 20-3.6-3.6" stroke-linecap="round" /></svg>
        </button>
        <button class="icon-button" type="button" data-theme-toggle aria-label="Switch to dark mode">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M20 12.5A8 8 0 1 1 11.5 4a6.5 6.5 0 0 0 8.5 8.5Z" stroke-linejoin="round" /></svg>
        </button>
      </div>
    </header>

    <div class="docs">
      <nav class="docs__nav" data-docs-nav aria-label="Documentation">
        {"".join(nav_html)}
      </nav>
      <main class="docs__main" id="content">
        <article class="docs-content">
{markup}
        </article>
        <nav class="docs-pager" aria-label="Pagination">{"".join(pager_html)}</nav>
      </main>
      <aside class="docs__toc" aria-label="On this page">
        <p class="docs-toc__title">On this page</p>
        <ul class="docs-toc__list">{"".join(toc_html)}</ul>
      </aside>
    </div>

    <footer class="footer">
      <div class="footer__brand"><img src="/assets/logo.png" width="22" height="22" alt="" /><span>Zett</span></div>
      <nav class="footer__links" aria-label="Footer">
        <a href="/docs/">Documentation</a>
        <a href="/docs/plugins/">Plugins</a>
        <a href="{repo_url}">GitHub</a>
        <a href="{repo_url}/blob/main/LICENSE">MIT License</a>
      </nav>
    </footer>

    <div class="search-dialog" data-search-dialog role="dialog" aria-label="Search the documentation">
      <div class="search-dialog__panel">
        <div class="search-dialog__field">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="6" /><path d="m20 20-3.6-3.6" stroke-linecap="round" /></svg>
          <input type="search" placeholder="Search the documentation…" aria-label="Search the documentation" />
        </div>
        <p class="search-dialog__empty" data-search-empty hidden>Type to search the documentation.</p>
        <ul class="search-dialog__results" data-search-results></ul>
      </div>
    </div>

    <script type="module" src="/scripts/shared.js"></script>
    <script type="module" src="/scripts/docs.js"></script>
  </body>
</html>
"""

    entry = {
        "title": title,
        "url": page_url(source),
        "section": section or "Overview",
        "headings": [item["name"] for item in toc],
        "text": strip_tags(prose)[:200],
    }
    return shell, entry


def previous_label(source: str) -> str:
    for _, pages in NAV:
        for label, page_source in pages:
            if page_source == source:
                return label
    return source


def flatten_toc(tokens: list[dict]) -> list[dict]:
    """Keep the top two heading levels for the right-hand column."""
    result: list[dict] = []
    for token in tokens:
        result.append(
            {
                "id": token["id"],
                "name": token["name"],
                "children": token.get("children", [])[:6],
            }
        )
    return result


def write_pygments_css() -> None:
    light = HtmlFormatter(style="friendly").get_style_defs(
        'html:not([data-theme="dark"]) .highlight'
    )
    dark = HtmlFormatter(style="native").get_style_defs(
        'html[data-theme="dark"] .highlight'
    )
    STYLES_DIR.mkdir(parents=True, exist_ok=True)
    (STYLES_DIR / "pygments.css").write_text(
        "/* Generated by web/tools/build_docs.py — do not edit. */\n"
        + light
        + "\n"
        + dark
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    markdown_engine = markdown.Markdown(
        extensions=[
            "extra",
            "sane_lists",
            "admonition",
            "toc",
            "pymdownx.snippets",
            "pymdownx.superfences",
            "pymdownx.highlight",
            "pymdownx.inlinehilite",
            "pymdownx.magiclink",
        ],
        extension_configs={
            "toc": {
                "permalink": True,
                "permalink_title": "Link to this section",
                "toc_depth": "2-3",
            },
            "pymdownx.snippets": {
                "base_path": [str(REPO)],
                "check_paths": True,
            },
            "pymdownx.highlight": {
                "use_pygments": True,
                "pygments_lang_class": False,
            },
        },
    )

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_pygments_css()

    repo_url = "https://github.com/Chang-LeHung/zettelekasten"
    index: list[dict] = []

    for section, pages in NAV:
        for label, source in pages:
            text = (DOCS_DIR / source).read_text(encoding="utf-8")
            markdown_engine.reset()
            markup = markdown_engine.convert(render_titled_fences(text))
            markup = rewrite_links(markup, source)
            toc = flatten_toc(markdown_engine.toc_tokens)
            page, entry = render_page(
                source=source,
                label=label,
                section=section,
                markup=markup,
                toc=toc,
                repo_url=repo_url,
            )
            target = OUT_DIR / page_url(source).removeprefix("/docs/") / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page, encoding="utf-8")
            index.append(entry)
            print(f"built {target.relative_to(REPO)}")

    source_assets = DOCS_DIR / "assets"
    if source_assets.is_dir():
        shutil.copytree(source_assets, OUT_DIR / "assets", dirs_exist_ok=True)

    (OUT_DIR / "search.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"built {OUT_DIR.relative_to(REPO)}/search.json ({len(index)} pages)")


if __name__ == "__main__":
    main()
