import DOMPurify from 'dompurify'

/** Clean the complete tree, so nested raw HTML and Markdown stay balanced. */
export function sanitizeMarkdown(html: string): string {
  const fragment = DOMPurify.sanitize(html, {
    RETURN_DOM_FRAGMENT: true,
    FORBID_TAGS: ['style', 'iframe', 'object', 'embed', 'form', 'input', 'textarea', 'select', 'link', 'meta', 'base'],
  })
  for (const element of fragment.querySelectorAll<HTMLElement>('[style]')) {
    for (const property of Array.from(element.style)) {
      const value = element.style.getPropertyValue(property)
      // Do not allow authored CSS to fetch resources or cover app controls.
      if (/url\s*\(|expression\s*\(|@import|\\/iu.test(value) ||
          ['z-index', 'behavior', '-moz-binding'].includes(property) ||
          (property === 'position' && /fixed|sticky/iu.test(value))) {
        element.style.removeProperty(property)
      }
    }
  }
  for (const link of fragment.querySelectorAll('a')) link.setAttribute('rel', 'noopener noreferrer')
  const wrapper = document.createElement('div')
  wrapper.append(fragment)
  return wrapper.innerHTML
}
