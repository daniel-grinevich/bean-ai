import MarkdownIt, { type Token } from 'markdown-it'
import type { HighlighterCore } from 'shiki/core'
import { shallowRef } from 'vue'

export type TableRow = Record<string, string | number | boolean | null>

export type Segment =
  | { kind: 'html'; html: string }
  | {
      kind: 'table'
      columns: string[]
      rows: TableRow[]
      source: 'markdown' | 'json'
      raw?: string
    }

// Shiki is big, so load it after first paint (only the grammars we need) and re-render once ready.
export const highlighter = shallowRef<HighlighterCore | null>(null)
let loading: Promise<void> | null = null
export function loadHighlighter() {
  loading ??= (async () => {
    const [{ createHighlighterCore }, { createJavaScriptRegexEngine }] = await Promise.all([
      import('shiki/core'),
      import('shiki/engine/javascript'),
    ])
    highlighter.value = await createHighlighterCore({
      engine: createJavaScriptRegexEngine(),
      themes: [import('@shikijs/themes/github-light'), import('@shikijs/themes/github-dark')],
      langs: [
        import('@shikijs/langs/typescript'),
        import('@shikijs/langs/javascript'),
        import('@shikijs/langs/json'),
        import('@shikijs/langs/python'),
        import('@shikijs/langs/shellscript'),
        import('@shikijs/langs/sql'),
        import('@shikijs/langs/vue'),
        import('@shikijs/langs/yaml'),
        import('@shikijs/langs/diff'),
      ],
    })
  })().catch((err) => console.warn('Code highlighting unavailable', err))
  return loading
}

const md = new MarkdownIt({ html: false, linkify: true, breaks: false })

md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]!
  const lang = token.info.trim().split(/\s+/)[0]?.toLowerCase() ?? ''
  const code = token.content
  const h = highlighter.value
  const body =
    h && lang && h.getLoadedLanguages().includes(lang)
      ? h.codeToHtml(code, {
          lang,
          themes: { light: 'github-light', dark: 'github-dark' },
          defaultColor: false,
        })
      : `<pre class="shiki"><code>${md.utils.escapeHtml(code)}</code></pre>`
  const label = md.utils.escapeHtml(lang || 'text')
  return `<div class="code-block" data-lang="${label}"><div class="code-block-bar"><span>${label}</span><button type="button" class="code-copy" data-copy aria-label="Copy code">Copy</button></div>${body}</div>`
}

const defaultLinkOpen =
  md.renderer.rules.link_open ??
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx]!.attrSet('target', '_blank')
  tokens[idx]!.attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

// Splits a reply into HTML chunks and tables, so tables can render as interactive components.
export function toSegments(text: string): Segment[] {
  const tokens = md.parse(text, {})
  const segments: Segment[] = []
  let buffer: Token[] = []
  const flush = () => {
    if (buffer.length)
      segments.push({ kind: 'html', html: md.renderer.render(buffer, md.options, {}) })
    buffer = []
  }

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]!
    if (token.type === 'table_open' && token.level === 0) {
      const end = tokens.findIndex((t, j) => j > i && t.type === 'table_close' && t.level === 0)
      if (end === -1) break // table still streaming in; wait for the rest
      flush()
      segments.push(markdownTable(tokens.slice(i, end + 1)))
      i = end
      continue
    }
    if (token.type === 'fence' && token.level === 0) {
      const rows = jsonRows(token)
      if (rows) {
        flush()
        segments.push({ kind: 'table', ...rows, source: 'json', raw: token.content })
        continue
      }
    }
    buffer.push(token)
  }
  flush()
  return segments
}

function markdownTable(tokens: Token[]): Segment {
  const columns: string[] = []
  const rows: TableRow[] = []
  let inHead = false
  let row: string[] | null = null
  for (const t of tokens) {
    if (t.type === 'thead_open') inHead = true
    else if (t.type === 'thead_close') inHead = false
    else if (t.type === 'tr_open') row = []
    else if (t.type === 'inline' && row) row.push(plainText(t))
    else if (t.type === 'tr_close' && row) {
      if (inHead) columns.push(...row)
      else rows.push(Object.fromEntries(columns.map((c, i) => [c, row![i] ?? ''])))
      row = null
    }
  }
  return { kind: 'table', columns, rows, source: 'markdown' }
}

// A ```json block holding an array of flat objects becomes a table.
function jsonRows(token: Token): { columns: string[]; rows: TableRow[] } | null {
  const lang = token.info.trim().toLowerCase()
  if (lang !== 'json') return null
  try {
    const data: unknown = JSON.parse(token.content)
    if (!Array.isArray(data) || !data.length) return null
    if (!data.every((r) => r && typeof r === 'object' && !Array.isArray(r))) return null
    const columns = [...new Set(data.flatMap((r) => Object.keys(r)))]
    const rows = data.map((r) =>
      Object.fromEntries(
        columns.map((c) => {
          const v = (r as Record<string, unknown>)[c]
          return [
            c,
            v === undefined || v === null
              ? null
              : typeof v === 'object'
                ? JSON.stringify(v)
                : (v as TableRow[string]),
          ]
        }),
      ),
    )
    return { columns, rows }
  } catch {
    return null
  }
}

// Cell text without markdown syntax (**bold**, `code`, links), so it reads and sorts cleanly.
function plainText(inline: Token): string {
  const parts = inline.children?.map((c) =>
    c.type === 'text' || c.type === 'code_inline' ? c.content : c.type === 'softbreak' ? ' ' : '',
  )
  return (parts?.join('') ?? inline.content).trim()
}
