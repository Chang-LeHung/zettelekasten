#!/usr/bin/env node
/**
 * Compose the published site: the hand-written landing page owns the root and
 * the VitePress build sits under `/docs/`.
 *
 * VitePress renders the documentation and provides its own search, so this
 * script only does what the documentation tool cannot: rewrite the landing
 * page's root-absolute URLs with the site base, copy the landing assets beside
 * it, and write the small index the landing page's own search dialog reads.
 *
 *   node web/tools/compose_site.mjs --base /zettelekasten/
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '../..')
const web = path.join(repo, 'web')
const docs = path.join(repo, 'docs')
const site = path.join(repo, 'site')

const argIndex = process.argv.indexOf('--base')
const base = normalizeBase(argIndex === -1 ? '/' : process.argv[argIndex + 1])

/** Directories under `docs/` that never reach the published tree. */
const UNPUBLISHED = new Set(['.vitepress', 'internal', 'node_modules', 'public'])

/** A snippet line pulls a package README in, exactly as the docs build does. */
const SNIPPET = /^--8<--\s+"([^"]+)"$/gm

function normalizeBase(value) {
  const trimmed = value.replace(/^\/+|\/+$/g, '')
  return trimmed ? `/${trimmed}/` : '/'
}

/** The landing page is written for the site root, so carry the base into it. */
function writeLanding() {
  const page = fs
    .readFileSync(path.join(web, 'index.html'), 'utf8')
    .replaceAll('href="/', `href="${base}`)
    .replaceAll('src="/', `src="${base}`)
    .replace(
      '<meta charset="utf-8" />',
      `<meta charset="utf-8" />\n    <meta name="zett-base" content="${base}" />`,
    )
  fs.mkdirSync(site, { recursive: true })
  fs.writeFileSync(path.join(site, 'index.html'), page)
  console.log(`built site/index.html with base ${base}`)
}

function copyLandingAssets() {
  for (const name of ['assets', 'styles', 'scripts']) {
    fs.cpSync(path.join(web, name), path.join(site, name), { recursive: true })
  }
}

function* markdownPages(dir, prefix = '') {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    if (entry.name.startsWith('.') && entry.isDirectory()) continue
    if (UNPUBLISHED.has(entry.name)) continue
    const relative = path.posix.join(prefix, entry.name)
    if (entry.isDirectory()) {
      yield* markdownPages(path.join(dir, entry.name), relative)
    } else if (entry.name.endsWith('.md')) {
      yield relative
    }
  }
}

/** The page's clean URL: `index.md` is the section index, the rest keep a slug. */
function pageUrl(relative) {
  const withoutExtension = relative.replace(/\.md$/, '')
  const slug = withoutExtension.replace(/(^|\/)index$/, '$1')
  return slug ? `${base}docs/${slug}/` : `${base}docs/`
}

function readSource(relative) {
  const markdown = fs.readFileSync(path.join(docs, relative), 'utf8')
  return markdown.replace(SNIPPET, (_, target) => fs.readFileSync(path.resolve(repo, target), 'utf8'))
}

function plainText(markdown) {
  return markdown
    .replace(/^---\n[\s\S]*?\n---\n/, '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/[#*_`>|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * The landing page's search dialog is part of the product page, so it keeps its
 * index. The documentation pages themselves use VitePress's own search.
 */
function writeSearchIndex() {
  const index = []
  for (const relative of markdownPages(docs)) {
    const markdown = readSource(relative)
    const title = /^#\s+(.+)$/m.exec(markdown)?.[1] ?? path.basename(relative, '.md')
    const headings = [...markdown.matchAll(/^#{2,3}\s+(.+)$/gm)].map((match) => match[1].trim())
    index.push({
      title: title.trim(),
      url: pageUrl(relative),
      section: headings[0] ?? 'Overview',
      headings,
      text: plainText(markdown).slice(0, 200),
    })
  }
  const target = path.join(site, 'docs', 'search.json')
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, JSON.stringify(index, null, 1))
  console.log(`built site/docs/search.json (${index.length} pages)`)
}

writeLanding()
copyLandingAssets()
writeSearchIndex()
