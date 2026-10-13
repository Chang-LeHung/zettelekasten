#!/usr/bin/env node
/**
 * Keep the Chinese documentation a faithful mirror of the English one.
 *
 * Every English page under docs/ must have a page at the same path under
 * docs/zh/ that keeps the same structure: the same heading levels, an explicit
 * anchor on every translated heading equal to the slug of the English heading
 * (so links such as `settings.md#ai-providers` keep working), the same number
 * of fenced code blocks with the same code, the same link targets, admonitions
 * and table rows. It only checks structure; wording is the translator's job.
 *
 *   node web/tools/check-translations.mjs
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const docs = path.join(repo, 'docs')
const SKIP = new Set(['.vitepress', 'internal', 'node_modules', 'public', 'zh'])

/** Pages that pull a package README in with a snippet line have no body to compare. */
const SNIPPET = /^--8<--\s+"[^"]+"$/m

function* pages(dir, prefix = '') {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP.has(entry.name) || entry.name.startsWith('.')) continue
    const relative = path.posix.join(prefix, entry.name)
    if (entry.isDirectory()) yield* pages(path.join(dir, entry.name), relative)
    else if (entry.name.endsWith('.md')) yield relative
  }
}

/** VitePress's heading slug: lowercase, punctuation dropped, words joined by hyphens. */
function slug(heading) {
  return heading
    .replace(/`/g, '')
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s_-]/gu, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

const headings = (text) => [...text.matchAll(/^(#{2,3}) (.+)$/gm)].map((m) => ({ level: m[1], text: m[2].trim() }))
const fences = (text) => [...text.matchAll(/^```[^\n]*\n([\s\S]*?)^```/gm)].map((m) => m[1])
const links = (text) => [...text.matchAll(/\]\(([^)\s]+)/g)].map((m) => m[1])
const count = (text, re) => (text.match(re) ?? []).length

/** Code compares equal when only prose comments differ. */
const code = (block) =>
  block
    .split('\n')
    .map((line) => (line.trim().startsWith('#') ? '#' : line.replace(/\s+#\s.*$/, '')))
    .join('\n')

const problems = []
const fail = (file, message) => problems.push(`docs/zh/${file}: ${message}`)

for (const relative of pages(docs)) {
  const en = fs.readFileSync(path.join(docs, relative), 'utf8')
  const target = path.join(docs, 'zh', relative)
  if (!fs.existsSync(target)) {
    fail(relative, 'missing Chinese page')
    continue
  }
  const zh = fs.readFileSync(target, 'utf8')
  if (SNIPPET.test(en)) continue

  const eh = headings(en)
  const zhh = headings(zh)
  if (eh.map((h) => h.level).join() !== zhh.map((h) => h.level).join()) {
    fail(relative, `heading levels differ (${eh.length} vs ${zhh.length})`)
  } else {
    eh.forEach((heading, i) => {
      const id = /\{#([^}]+)\}\s*$/.exec(zhh[i].text)?.[1]
      if (id !== slug(heading.text)) fail(relative, `heading "${heading.text}" needs {#${slug(heading.text)}}, found ${id ? `{#${id}}` : 'no id'}`)
    })
  }

  const ef = fences(en)
  const zf = fences(zh)
  if (ef.length !== zf.length) fail(relative, `code blocks differ (${ef.length} vs ${zf.length})`)
  else ef.forEach((block, i) => code(block) !== code(zf[i]) && fail(relative, `code block ${i + 1} changed`))

  const el = links(en)
  const zl = links(zh)
  if (el.join('\n') !== zl.join('\n')) fail(relative, 'link targets differ')
  if (count(en, /^:::/gm) !== count(zh, /^:::/gm)) fail(relative, 'admonitions differ')
  if (count(en, /^\|/gm) !== count(zh, /^\|/gm)) fail(relative, 'table rows differ')
}

if (problems.length) {
  console.error(problems.join('\n'))
  console.error(`\n${problems.length} translation problem(s). Keep docs/zh/ a structural mirror of docs/.`)
  process.exit(1)
}
console.log('docs/zh mirrors docs: structure, anchors, code and links match')
