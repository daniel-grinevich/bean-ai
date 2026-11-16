// Mirrors backend/src/bean_ai_backend/schemas/conversations.py.

export type Role = 'user' | 'assistant'

export interface ChatMessage {
  role: Role
  content: string
  // Model id that answered (assistant messages from the server).
  model?: string | null
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
