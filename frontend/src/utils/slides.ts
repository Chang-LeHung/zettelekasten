export type SlideDensity = 'normal' | 'compact' | 'dense'

const SLIDE_SEPARATOR = /\r?\n---(?=\r?\n|$)/u

/** Split deck Markdown only on a standalone horizontal slide separator. */
export function splitSlides(source: string): string[] {
  const slides = source
    .trim()
    .split(SLIDE_SEPARATOR)
    .map(slide => slide.trim())
    .filter(Boolean)
  return slides.length ? slides : ['']
}

/** Select a conservative type scale so dense content stays inside its slide. */
export function slideDensity(source: string): SlideDensity {
  const visibleCharacters = source.replace(/\s+/gu, ' ').trim().length
  const lines = source.split(/\r?\n/u).filter(line => line.trim()).length
  if (visibleCharacters > 900 || lines > 16) return 'dense'
  if (visibleCharacters > 520 || lines > 10) return 'compact'
  return 'normal'
}
