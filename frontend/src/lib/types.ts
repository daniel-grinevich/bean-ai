import type { Role } from '@/api'

export type MessageStatus = 'done' | 'streaming' | 'stopped' | 'error'

// A message as the UI sees it: server messages plus client-only status for the live reply.
export interface UiMessage {
  id: string
  role: Role
  content: string
  status: MessageStatus
  error?: string
}

export interface UiConversation {
  id: string
  title: string
  updated_at: string
  messages: UiMessage[]
}

export const newId = () => crypto.randomUUID()
