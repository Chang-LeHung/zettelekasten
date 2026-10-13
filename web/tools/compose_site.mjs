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

/** The Chinese tree is a mirror under `docs/zh/` with its own search index. */
const LOCALES = [
  { dir: '', url: 'docs/', skip: new Set(['zh']) },
  { dir: 'zh', url: 'docs/zh/', skip: new Set() },
]

/** A snippet line pulls a package README in, exactly as the docs build does. */
const SNIPPET = /^--8<--\s+"([^"]+)"$/gm

function normalizeBase(value) {
  const trimmed = value.replace(/^\/+|\/+$/g, '')
  return trimmed ? `/${trimmed}/` : '/'
}

/**
 * Each landing page is written for the site root, so carry the base into it.
 * The English page owns `/`; the Chinese page is its own document under `/zh/`.
 */
function writeLanding() {
  writeLandingPage('index.html', 'index.html')
  writeLandingPage('zh/index.html', 'zh/index.html')
}

function writeLandingPage(source, target) {
  const page = fs
    .readFileSync(path.join(web, source), 'utf8')
    .replaceAll('href="/', `href="${base}`)
    .replaceAll('src="/', `src="${base}`)
    .replace(
      '<meta charset="utf-8" />',
      `<meta charset="utf-8" />\n    <meta name="zett-base" content="${base}" />`,
    )
  const out = path.join(site, target)
  fs.mkdirSync(path.dirname(out), { recursive: true })
  fs.writeFileSync(out, page)
  console.log(`built site/${target} with base ${base}`)
}

function copyLandingAssets() {
  for (const name of ['assets', 'styles', 'scripts']) {
    fs.cpSync(path.join(web, name), path.join(site, name), { recursive: true })
  }
}

function* markdownPages(dir, prefix = '', skip = new Set()) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    if (entry.name.startsWith('.') && entry.isDirectory()) continue
    if (UNPUBLISHED.has(entry.name) || skip.has(entry.name)) continue
    const relative = path.posix.join(prefix, entry.name)
    if (entry.isDirectory()) {
      yield* markdownPages(path.join(dir, entry.name), relative)
    } else if (entry.name.endsWith('.md')) {
      yield relative
    }
  }
}

/** The page's clean URL: `index.md` is the section index, the rest keep a slug. */
function pageUrl(relative, urlRoot) {
  const withoutExtension = relative.replace(/\.md$/, '')
  const slug = withoutExtension.replace(/(^|\/)index$/, '$1')
  return slug ? `${base}${urlRoot}${slug}/` : `${base}${urlRoot}`
}

function readSource(relative, root = docs) {
  const markdown = fs.readFileSync(path.join(root, relative), 'utf8')
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

/** Headings may carry an explicit anchor (`## Title {#slug}`); search shows only the words. */
const withoutAnchor = (heading) => heading.replace(/\s*\{#[^}]+\}\s*$/, '').trim()

/** A page without a level-one heading is a home page: use its hero line, then the site name. */
function pageTitle(markdown, relative) {
  const heading = /^#\s+(.+)$/m.exec(markdown)?.[1]
  if (heading) return withoutAnchor(heading)
  const hero = /^hero:[\s\S]*?^\s+text:\s*(.+)$/m.exec(markdown)?.[1]
  return hero ? hero.replace(/^["']|["']$/g, '').trim() : path.basename(relative, '.md')
}

/**
 * The landing page's search dialog is part of the product page, so it keeps its
 * index: one file per language, each listing only that language's pages. The
 * documentation pages themselves use VitePress's own search.
 */
function writeSearchIndex() {
  for (const locale of LOCALES) {
    const root = path.join(docs, locale.dir)
    if (!fs.existsSync(root)) continue
    const index = []
    for (const relative of markdownPages(root, '', locale.skip)) {
      const markdown = readSource(relative, root)
      const headings = [...markdown.matchAll(/^#{2,3}\s+(.+)$/gm)].map((match) => withoutAnchor(match[1]))
      index.push({
        title: pageTitle(markdown, relative),
        url: pageUrl(relative, locale.url),
        section: headings[0] ?? (locale.dir ? '概览' : 'Overview'),
        headings,
        text: plainText(markdown).slice(0, 200),
      })
    }
    const target = path.join(site, locale.url, 'search.json')
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.writeFileSync(target, JSON.stringify(index, null, 1))
    console.log(`built site/${locale.url}search.json (${index.length} pages)`)
  }
}

writeLanding()
copyLandingAssets()
writeSearchIndex()
