import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import {
  type ConversationSummary,
  deleteConversation,
  getConversation,
  getHealth,
  listConversations,
  streamChat,
} from '@/api'
import { newId, type UiConversation, type UiMessage } from '@/lib/types'
import { useChatStore } from '@/stores/chat'

export const queryKeys = {
  health: ['health'] as const,
  conversations: ['conversations'] as const,
  conversation: (id: string) => ['conversation', id] as const,
}

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    refetchInterval: 30_000,
    retry: false,
  })
}

export function useConversationsQuery() {
  return useQuery({ queryKey: queryKeys.conversations, queryFn: listConversations })
}

export function useConversationQuery(id: MaybeRefOrGetter<string | null>) {
  const chat = useChatStore()
  return useQuery({
    queryKey: computed(() => queryKeys.conversation(toValue(id) ?? '')),
    queryFn: async (): Promise<UiConversation> => {
      const c = await getConversation(toValue(id)!)
      return {
        ...c,
        messages: c.messages.map((m) => ({ ...m, id: newId(), status: 'done' as const })),
      }
    },
    // While a reply streams into this conversation the cache is the source of truth.
    enabled: computed(() => !!toValue(id) && chat.streamingConversationId !== toValue(id)),
    // This client is the only writer while it's open, so local updates stay authoritative.
    staleTime: Infinity,
    structuralSharing: false,
  })
}

export function useDeleteConversation() {
  const queryClient = useQueryClient()
  const chat = useChatStore()
  const router = useRouter()

  return useMutation({
    mutationFn: deleteConversation,
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.conversations })
      const previous = queryClient.getQueryData<ConversationSummary[]>(queryKeys.conversations)
      queryClient.setQueryData<ConversationSummary[]>(queryKeys.conversations, (list) =>
        list?.filter((c) => c.id !== id),
      )
      if (chat.currentConversationId === id) router.push('/')
      return { previous }
    },
    onError: (err, _id, ctx) => {
      queryClient.setQueryData(queryKeys.conversations, ctx?.previous)
      toast.error('Could not delete the conversation', { description: err.message })
    },
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: queryKeys.conversation(id) })
      toast.success('Conversation deleted')
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.conversations }),
  })
}

interface SendVariables {
  text: string
  conversationId: string | null
}

class StreamError extends Error {}

const titleFrom = (text: string) => (text.length > 60 ? `${text.slice(0, 57)}…` : text)

// Sends a message and streams the reply straight into the query cache.
export function useSendMessage() {
  const queryClient = useQueryClient()
  const chat = useChatStore()
  const router = useRouter()

  function patchMessage(
    conversationId: string | null,
    messageId: string,
    patch: (m: UiMessage) => Partial<UiMessage>,
  ) {
    if (!conversationId) {
      chat.pendingMessages = chat.pendingMessages.map((m) =>
        m.id === messageId ? { ...m, ...patch(m) } : m,
      )
      return
    }
    queryClient.setQueryData<UiConversation>(
      queryKeys.conversation(conversationId),
      (c) =>
        c && {
          ...c,
          messages: c.messages.map((m) => (m.id === messageId ? { ...m, ...patch(m) } : m)),
        },
    )
  }

  function appendMessages(conversationId: string, messages: UiMessage[]) {
    queryClient.setQueryData<UiConversation>(queryKeys.conversation(conversationId), (c) =>
      c
        ? { ...c, messages: [...c.messages, ...messages], updated_at: new Date().toISOString() }
        : {
            id: conversationId,
            title: titleFrom(messages[0]!.content),
            updated_at: new Date().toISOString(),
            messages,
          },
    )
  }

  return useMutation({
    mutationFn: async ({ text, conversationId }: SendVariables) => {
      const controller = new AbortController()
      chat.controller = controller
      chat.isStreaming = true

      const user: UiMessage = { id: newId(), role: 'user', content: text, status: 'done' }
      const reply: UiMessage = { id: newId(), role: 'assistant', content: '', status: 'streaming' }
      let id = conversationId
      if (id) appendMessages(id, [user, reply])
      else chat.pendingMessages = [user, reply]
      chat.streamingConversationId = id

      try {
        for await (const ev of streamChat(text, id, controller.signal)) {
          if (ev.event === 'start' && !id) {
            id = ev.data.conversation_id
            chat.streamingConversationId = id
            appendMessages(id, chat.pendingMessages)
            chat.pendingMessages = []
            queryClient.setQueryData<ConversationSummary[]>(queryKeys.conversations, (list) => [
              {
                id: id!,
                title: titleFrom(text),
                updated_at: new Date().toISOString(),
                message_count: 1,
              },
              ...(list ?? []),
            ])
            if (chat.currentConversationId === null) router.replace(`/c/${id}`)
          } else if (ev.event === 'delta') {
            const delta = ev.data.text
            patchMessage(id, reply.id, (m) => ({ content: m.content + delta }))
          } else if (ev.event === 'error') {
            throw new StreamError(ev.data.message)
          } else if (ev.event === 'done') {
            break
          }
        }
        patchMessage(id, reply.id, () => ({ status: 'done' }))
        return { conversationId: id }
      } catch (err) {
        if (controller.signal.aborted) {
          patchMessage(id, reply.id, () => ({ status: 'stopped' }))
          return { conversationId: id }
        }
        const message = err instanceof Error ? err.message : String(err)
        patchMessage(id, reply.id, () => ({ status: 'error', error: message }))
        throw err
      } finally {
        chat.controller = null
        chat.isStreaming = false
        chat.streamingConversationId = null
      }
    },
    onError: (err) => {
      const offline = err instanceof TypeError
      toast.error(offline ? 'Could not reach the server' : 'Bean hit an error', {
        description: offline ? 'Check that the backend is running.' : err.message,
      })
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.conversations }),
  })
}

// Removes a failed reply and the user message before it, returning that message's text.
export function useDiscardFailedTurn() {
  const queryClient = useQueryClient()
  const chat = useChatStore()

  return (conversationId: string | null, replyId: string): string | null => {
    const messages = conversationId
      ? queryClient.getQueryData<UiConversation>(queryKeys.conversation(conversationId))?.messages
      : chat.pendingMessages
    if (!messages) return null
    const index = messages.findIndex((m) => m.id === replyId)
    const user = messages[index - 1]
    if (index < 1 || user?.role !== 'user') return null
    const rest = messages.filter((_, i) => i !== index && i !== index - 1)
    if (conversationId) {
      queryClient.setQueryData<UiConversation>(
        queryKeys.conversation(conversationId),
        (c) => c && { ...c, messages: rest },
      )
    } else {
      chat.pendingMessages = rest
    }
    return user.content
  }
}
