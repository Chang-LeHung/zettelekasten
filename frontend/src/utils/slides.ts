export type SlideDensity = 'normal' | 'compact' | 'dense'

const SECTION_SEPARATOR = /\r?\n---(?=\r?\n|$)/u
const VERTICAL_SLIDE_SEPARATOR = /\r?\n--(?=\r?\n|$)/u

/** Split Markdown into horizontal sections containing vertical slides. */
export function splitSlideSections(source: string): string[][] {
  const sections = source
    .trim()
    .split(SECTION_SEPARATOR)
    .map(section => section
      .trim()
      .split(VERTICAL_SLIDE_SEPARATOR)
      .map(slide => slide.trim())
      .filter(Boolean))
    .filter(section => section.length)
  return sections.length ? sections : [['']]
}

/** Ensure each horizontal section opens on a dedicated title page for presentation. */
export function presentationSections(source: string): string[][] {
  return splitSlideSections(source).map((section, index) => {
    const first = section[0] ?? ''
    const heading = /^(#{1,6})[\t ]+([^\n]+)(?:\n|$)/u.exec(first)
    const title = heading ? `# ${heading[2]!.replace(/[\t ]+#+[\t ]*$/u, '').trim()}` : `# Section ${index + 1}`
    // Reuse an authored title-only page; otherwise preserve all original content below it.
    if (heading && !first.slice(heading[0].length).trim()) return [title, ...section.slice(1)]
    return [title, ...section]
  })
}

/** Return every source slide in reading order, independent of its section. */
export function splitSlides(source: string): string[] {
  return splitSlideSections(source).flat()
}

/** Give every preview page a heading, including older pages without one. */
export function slideWithTitle(source: string, page: number): string {
  const content = source.trim()
  if (/^#{1,6}[\t ]+\S/u.test(content)) return content
  return `# Slide ${page}\n\n${content}`
}

/** Select a conservative type scale so dense content stays inside its slide. */
export function slideDensity(source: string): SlideDensity {
  const visibleCharacters = source.replace(/\s+/gu, ' ').trim().length
  const lines = source.split(/\r?\n/u).filter(line => line.trim()).length
  if (visibleCharacters > 900 || lines > 16) return 'dense'
  if (visibleCharacters > 520 || lines > 10) return 'compact'
  return 'normal'
}
