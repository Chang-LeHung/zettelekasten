/** One readable line for a tool call: what it is and what it acts on. */
export interface ToolSummary {
  /** Human name, e.g. "Read" or "Edit". */
  label: string
  /** The thing acted on (file name, command, query); empty when the arguments say nothing useful. */
  target: string
  /** A leading directory shown muted beside a file name. */
  context: string
  /** How to draw the target: a path or command is monospaced, prose is not. */
  kind: 'file' | 'command' | 'text' | 'none'
  /** Extra short facts such as a line range or the number of edits. */
  meta: string
}

const FILE_KEYS = ['file_path', 'path', 'filepath', 'filename', 'file']
const TEXT_KEYS = ['query', 'pattern', 'name', 'title', 'url', 'description', 'prompt', 'artifact_id']
const COMMAND_KEYS = ['command', 'cmd']

const LABELS: Readonly<Record<string, string>> = {
  read: 'Read',
  write_file: 'Write',
  write: 'Write',
  edit: 'Edit',
  bash: 'Bash',
  read_skill: 'Skill',
  tool_search: 'Tool search',
  glob: 'Find files',
  grep: 'Search',
  task: 'Subagent',
}

function text(args: Record<string, unknown> | undefined, keys: readonly string[]): string {
  if (!args) return ''
  for (const key of keys) {
    const value = args[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

/** Split a path into its file name and a short, muted parent such as "src/utils". */
export function splitPath(path: string): { name: string; context: string } {
  const parts = path.replace(/\\/g, '/').replace(/\/+$/, '').split('/').filter(Boolean)
  const name = parts.pop() ?? path
  return { name, context: parts.slice(-2).join('/') }
}

function firstLine(value: string): string {
  return value.split('\n').find((line) => line.trim())?.trim() ?? ''
}

function readMeta(args: Record<string, unknown> | undefined): string {
  if (!args) return ''
  const offset = typeof args.offset === 'number' ? args.offset : null
  const limit = typeof args.limit === 'number' ? args.limit : null
  if (offset !== null && limit !== null) return `L${offset}–${offset + limit - 1}`
  if (offset !== null) return `from L${offset}`
  if (limit !== null) return `${limit} lines`
  return ''
}

export function toolSummary(name: string, args: Record<string, unknown> | undefined): ToolSummary {
  const label = LABELS[name] ?? name.replaceAll('_', ' ')
  const none: ToolSummary = { label, target: '', context: '', kind: 'none', meta: '' }

  const file = text(args, FILE_KEYS)
  if (file) {
    const { name: fileName, context } = splitPath(file)
    const meta = name === 'read' ? readMeta(args) : name === 'edit' && args?.replace_all === true ? 'all matches' : ''
    return { label, target: fileName, context, kind: 'file', meta }
  }
  const command = text(args, COMMAND_KEYS)
  if (command) return { ...none, target: firstLine(command), kind: 'command' }
  const other = text(args, TEXT_KEYS)
  if (other) return { ...none, target: firstLine(other), kind: 'text' }
  return none
}
