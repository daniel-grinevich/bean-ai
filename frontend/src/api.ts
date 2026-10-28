// Client for the bean backend. Every request goes through the Vite dev proxy at /api.

export type Role = 'user' | 'assistant'

export interface ChatMessage {
  role: Role
  content: string
}

export interface ConversationSummary {
  id: string
  title: string
  updated_at: string
  message_count: number
}

export interface Conversation {
  id: string
  title: string
  updated_at: string
  messages: ChatMessage[]
}

export interface Health {
  status: string
  model?: string
}

export type StreamEvent =
  | { event: 'start'; data: { conversation_id: string } }
  | { event: 'delta'; data: { text: string } }
  | { event: 'done'; data: Record<string, never> }
  | { event: 'error'; data: { message: string } }

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// FastAPI errors look like {"detail": "..."}; fall back to the status line.
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // not JSON
  }
  return `Request failed: ${res.status} ${res.statusText}`.trim()
}

export const getHealth = () => request<Health>('/api/health')

export const listConversations = () => request<ConversationSummary[]>('/api/conversations')

export const getConversation = (id: string) =>
  request<Conversation>(`/api/conversations/${encodeURIComponent(id)}`)

export const deleteConversation = (id: string) =>
  request<void>(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })

// POST a message and yield the server-sent events from the response body.
export async function* streamChat(
  message: string,
  conversationId: string | null,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  })
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status)
  if (!res.body) throw new ApiError('The server sent an empty response', res.status)

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value.replace(/\r\n/g, '\n')
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const parsed = parseEvent(chunk)
      if (parsed) yield parsed
    }
  }
}

function parseEvent(chunk: string): StreamEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of chunk.split('\n')) {
    if (line.startsWith(':')) continue // SSE comment / keep-alive
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  if (!data.length) return null
  return { event, data: JSON.parse(data.join('\n')) } as StreamEvent
}
