// Server-sent events from POST /api/chat (backend/src/bean_ai_backend/schemas/chat.py is the request).

export type StreamEvent =
  | { event: 'start'; data: { conversation_id: string; model: string } }
  | { event: 'delta'; data: { text: string } }
  | { event: 'done'; data: Record<string, never> }
  | { event: 'error'; data: { message: string } }
