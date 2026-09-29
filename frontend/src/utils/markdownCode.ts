/**
 * One highlight.js registry for every surface that renders Markdown.
 *
 * The web conversation and the Chrome panel must highlight — and name — the
 * same fence languages, or one answer looks different in each host. This is the
 * union of both hosts' former lists, plus the languages a knowledge thread
 * meets (LaTeX, plain text, GraphQL, SCSS, ...), so every surface can highlight
 * whatever the model fences.
 */
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import c from 'highlight.js/lib/languages/c'
import cpp from 'highlight.js/lib/languages/cpp'
import csharp from 'highlight.js/lib/languages/csharp'
import css from 'highlight.js/lib/languages/css'
import dart from 'highlight.js/lib/languages/dart'
import diff from 'highlight.js/lib/languages/diff'
import dockerfile from 'highlight.js/lib/languages/dockerfile'
import go from 'highlight.js/lib/languages/go'
import graphql from 'highlight.js/lib/languages/graphql'
import ini from 'highlight.js/lib/languages/ini'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import kotlin from 'highlight.js/lib/languages/kotlin'
import latex from 'highlight.js/lib/languages/latex'
import less from 'highlight.js/lib/languages/less'
import lua from 'highlight.js/lib/languages/lua'
import makefile from 'highlight.js/lib/languages/makefile'
import markdown from 'highlight.js/lib/languages/markdown'
import nginx from 'highlight.js/lib/languages/nginx'
import objectivec from 'highlight.js/lib/languages/objectivec'
import perl from 'highlight.js/lib/languages/perl'
import php from 'highlight.js/lib/languages/php'
import plaintext from 'highlight.js/lib/languages/plaintext'
import powershell from 'highlight.js/lib/languages/powershell'
import python from 'highlight.js/lib/languages/python'
import r from 'highlight.js/lib/languages/r'
import ruby from 'highlight.js/lib/languages/ruby'
import rust from 'highlight.js/lib/languages/rust'
import scala from 'highlight.js/lib/languages/scala'
import scss from 'highlight.js/lib/languages/scss'
import sql from 'highlight.js/lib/languages/sql'
import swift from 'highlight.js/lib/languages/swift'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'

const LANGUAGES = {
  bash, c, cpp, csharp, css, dart, diff, dockerfile, go, graphql, ini, java, javascript, json,
  kotlin, latex, less, lua, makefile, markdown, nginx, objectivec, perl, php, plaintext,
  powershell, python, r, ruby, rust, scala, scss, sql, swift, typescript, xml, yaml,
}

/** Shorthands a fence may use that highlight.js does not define on its own. */
const LANGUAGE_ALIASES: Record<string, string> = {
  'c++': 'cpp',
  'c#': 'csharp',
  console: 'bash',
  cu: 'cpp',
  cuda: 'cpp',
  docker: 'dockerfile',
  html: 'xml',
  js: 'javascript',
  make: 'makefile',
  md: 'markdown',
  nvcc: 'cpp',
  objc: 'objectivec',
  'objective-c': 'objectivec',
  ps1: 'powershell',
  py: 'python',
  shell: 'bash',
  shellsession: 'bash',
  tex: 'latex',
  ts: 'typescript',
  vue: 'xml',
  zsh: 'bash',
}

for (const [name, language] of Object.entries(LANGUAGES)) {
  hljs.registerLanguage(name, language)
}

/** The registered language a fence asks for, or '' when nothing can highlight it. */
export function resolveLanguage(language: string): string {
  const normalized = language.trim().toLowerCase()
  const resolved = LANGUAGE_ALIASES[normalized] ?? normalized
  return /^[a-z0-9_-]+$/u.test(resolved) && hljs.getLanguage(resolved) ? resolved : ''
}

/** Human label for a fenced block, e.g. `bash` → Shell or `tex` → LaTeX. */
export function languageLabelFor(language: string, resolvedLanguage: string): string {
  const normalized = (resolvedLanguage || language.trim().toLowerCase())
  const labels: Record<string, string> = {
    bash: 'Shell', c: 'C', cpp: 'C++', csharp: 'C#', css: 'CSS', dart: 'Dart', diff: 'Diff',
    dockerfile: 'Dockerfile', go: 'Go', graphql: 'GraphQL', ini: 'INI', java: 'Java',
    javascript: 'JavaScript', json: 'JSON', kotlin: 'Kotlin', latex: 'LaTeX', less: 'Less',
    lua: 'Lua', makefile: 'Makefile', markdown: 'Markdown', nginx: 'Nginx',
    objectivec: 'Objective-C', perl: 'Perl', php: 'PHP', plaintext: 'Text',
    powershell: 'PowerShell', python: 'Python', r: 'R', ruby: 'Ruby', rust: 'Rust',
    scala: 'Scala', scss: 'SCSS', sql: 'SQL', swift: 'Swift', typescript: 'TypeScript',
    xml: 'XML', yaml: 'YAML',
  }
  return labels[normalized] ?? (normalized ? normalized[0].toUpperCase() + normalized.slice(1) : 'Code')
}

export { hljs }
