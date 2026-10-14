/**
 * Where a character sits inside a textarea, in viewport pixels.
 *
 * A textarea does not expose the rectangle of its selection, and the selection
 * toolbar has to float above the words that are selected. The standard
 * workaround is to copy the textarea's text styling onto an invisible mirror
 * `<div>`, put the text before the index in it, and measure a marker span that
 * follows.
 */

const COPIED = [
  'direction', 'boxSizing', 'width', 'overflowX', 'overflowY',
  'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
  'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize', 'fontSizeAdjust',
  'lineHeight', 'fontFamily', 'textAlign', 'textTransform', 'textIndent', 'textDecoration',
  'letterSpacing', 'wordSpacing', 'tabSize',
] as const

export interface CaretRect {
  /** Viewport coordinates of the character's top-left corner. */
  left: number
  top: number
  /** Height of one line of text there. */
  height: number
}

export function caretRect(textarea: HTMLTextAreaElement, index: number): CaretRect {
  const style = window.getComputedStyle(textarea)
  const mirror = document.createElement('div')
  mirror.setAttribute('aria-hidden', 'true')
  const mirrorStyle = mirror.style
  mirrorStyle.position = 'absolute'
  mirrorStyle.visibility = 'hidden'
  mirrorStyle.top = '0'
  mirrorStyle.left = '-9999px'
  mirrorStyle.whiteSpace = 'pre-wrap'
  mirrorStyle.overflowWrap = 'break-word'
  for (const property of COPIED) mirrorStyle[property] = style[property]
  mirror.textContent = textarea.value.slice(0, index)
  const marker = document.createElement('span')
  // A zero-width space keeps the span on the line even at the end of the text.
  marker.textContent = textarea.value.slice(index, index + 1) || '\u200b'
  mirror.append(marker)
  document.body.append(mirror)

  const box = textarea.getBoundingClientRect()
  const lineHeight = Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.4
  const rect = {
    left: box.left + marker.offsetLeft - textarea.scrollLeft,
    top: box.top + marker.offsetTop - textarea.scrollTop,
    height: lineHeight,
  }
  mirror.remove()
  return rect
}
