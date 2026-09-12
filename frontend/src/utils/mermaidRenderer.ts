export interface MermaidRenderResult {
  svg: string
  bindFunctions?: (element: Element) => void
}

let diagramSequence = 0
let renderQueue: Promise<void> = Promise.resolve()
let mermaidModule: Promise<(typeof import('mermaid'))['default']> | null = null

async function loadMermaid(): Promise<(typeof import('mermaid'))['default']> {
  if (mermaidModule === null) {
    mermaidModule = import('mermaid').then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'base',
        flowchart: { htmlLabels: false, useMaxWidth: true },
        themeVariables: {
          primaryColor: '#edf4ef',
          primaryBorderColor: '#6f927f',
          primaryTextColor: '#27352e',
          lineColor: '#688072',
          secondaryColor: '#f6f8f7',
          tertiaryColor: '#ffffff',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        },
      })
      return mermaid
    })
  }
  return mermaidModule
}

export function renderMermaid(source: string): Promise<MermaidRenderResult> {
  const render = renderQueue.then(async () => {
    const mermaid = await loadMermaid()
    return mermaid.render(`zett-mermaid-${++diagramSequence}`, source)
  })
  renderQueue = render.then(
    () => undefined,
    () => undefined,
  )
  return render
}
