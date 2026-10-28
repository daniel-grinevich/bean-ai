// A stand-in for the FastAPI backend that speaks the same API (SSE chat + conversations).
// Lets you work on the UI without a model key: `npm run mock`, then `VITE_API_TARGET=http://localhost:8010 npm run dev`.
import { randomUUID } from 'node:crypto'
import { createServer } from 'node:http'

const PORT = Number(process.env.MOCK_PORT ?? 8010)
const conversations = new Map()

const REPLIES = {
  offline: `Three machines are offline right now:

| Machine | Location | Offline since | Last error |
| --- | --- | --- | --- |
| NV-0142 | HQ Lobby | 2h 14m | Water pressure low |
| NV-0217 | Warehouse B | 47m | Lost network |
| NV-0031 | Riverside Café | 5h 02m | Grinder jam |

NV-0031 has been down longest. To pull the same list yourself:

\`\`\`sql
select machine_id, location, offline_since, last_error
from fleet.machine_status
where state = 'offline'
order by offline_since;
\`\`\``,
  default: `**HQ Lobby** had a solid week: **1,284 cups**, up 9% on last week.

| Day | Cups | Revenue | Top drink |
| --- | --- | --- | --- |
| Mon | 212 | $741.20 | Flat white |
| Tue | 198 | $689.50 | Latte |
| Wed | 231 | $802.75 | Flat white |
| Thu | 187 | $650.10 | Cappuccino |
| Fri | 256 | $889.40 | Latte |
| Sat | 104 | $361.00 | Espresso |
| Sun | 96 | $334.80 | Latte |

Friday peaked around 8:30am. Here's how you could chart it from crumb:

\`\`\`python
import pandas as pd

df = crumb.query("select day, cups from sales.daily where location = 'HQ Lobby'")
df.plot(x="day", y="cups", kind="bar", title="HQ Lobby: cups per day")
\`\`\`

The machine also reported two low-milk alerts, both cleared within 15 minutes.`,
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const json = (res, status, body) => {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(body === undefined ? '' : JSON.stringify(body))
}
const summary = (c) => ({
  id: c.id,
  title: c.title,
  updated_at: c.updated_at,
  message_count: c.messages.length,
})

async function readBody(req) {
  let raw = ''
  for await (const chunk of req) raw += chunk
  return JSON.parse(raw || '{}')
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`)
  const match = url.pathname.match(/^\/api\/conversations\/([^/]+)$/)

  if (req.method === 'GET' && url.pathname === '/api/health')
    return json(res, 200, { status: 'ok', model: 'mock (no LLM)' })
  if (req.method === 'GET' && url.pathname === '/api/conversations') {
    return json(
      res,
      200,
      [...conversations.values()]
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
        .map(summary),
    )
  }
  if (match && req.method === 'GET') {
    const c = conversations.get(match[1])
    return c ? json(res, 200, c) : json(res, 404, { detail: 'Conversation not found' })
  }
  if (match && req.method === 'DELETE') {
    return conversations.delete(match[1])
      ? json(res, 204)
      : json(res, 404, { detail: 'Conversation not found' })
  }
  if (req.method === 'POST' && url.pathname === '/api/chat') {
    const { message, conversation_id } = await readBody(req)
    if (!message?.trim()) return json(res, 422, { detail: 'message is required' })
    let c = conversation_id && conversations.get(conversation_id)
    if (conversation_id && !c) return json(res, 404, { detail: 'Conversation not found' })
    if (!c) {
      c = {
        id: randomUUID().replaceAll('-', ''),
        title: message.slice(0, 60),
        updated_at: '',
        messages: [],
      }
      conversations.set(c.id, c)
    }
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    })
    const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    let closed = false
    res.on('close', () => (closed = true))

    send('start', { conversation_id: c.id })
    if (/\berror\b/i.test(message)) {
      await sleep(400)
      send('error', { message: 'The model provider returned 503 (mock error).' })
      return res.end()
    }
    const reply = /offline/i.test(message) ? REPLIES.offline : REPLIES.default
    let text = ''
    for (const piece of reply.match(/[\s\S]{1,6}/g)) {
      if (closed) break
      text += piece
      send('delta', { text: piece })
      await sleep(18)
    }
    c.messages.push({ role: 'user', content: message }, { role: 'assistant', content: text })
    c.updated_at = new Date().toISOString()
    if (!closed) send('done', {})
    return res.end()
  }
  json(res, 404, { detail: 'Not found' })
}).listen(PORT, () => console.log(`mock bean API on http://localhost:${PORT}`))
