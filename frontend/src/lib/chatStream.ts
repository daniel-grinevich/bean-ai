import { apiFetch, toNetworkError } from '@/lib/apiClient'
import { ApiError } from '@/lib/apiError'
import type { StreamEvent } from '@/types/chat'

// POST a message and yield the server-sent events from the response body.
export async function* streamChat(
  message: string,
  conversationId: string | null,
  model: string | null,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await apiFetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message, conversation_id: conversationId, model }),
    signal,
  })
  if (!res.body) throw new ApiError('The server sent an empty response', res.status)

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  while (true) {
    let result: ReadableStreamReadResult<string>
    try {
      result = await reader.read()
    } catch (err) {
      throw toNetworkError(err)
    }
    const { value, done } = result
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
