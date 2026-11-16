import { useQueryClient } from '@tanstack/vue-query'
import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { apiClient } from '@/lib/apiClient'
import { queryKeys } from '@/lib/queryKeys'
import { newId, type UiConversation } from '@/lib/types'
import { useChatStore } from '@/stores/chat'
import type { Conversation, ConversationSummary } from '@/types/conversation'
import { useApi, useApiMutation } from './useApi'

const conversationPath = (id: string) => `/api/conversations/${encodeURIComponent(id)}`

export function useConversations() {
  return useApi({
    queryKey: queryKeys.conversations,
    queryFn: () => apiClient<ConversationSummary[]>('/api/conversations'),
  })
}

export function useConversation(id: MaybeRefOrGetter<string | null>) {
  const chat = useChatStore()
  return useApi({
    queryKey: computed(() => queryKeys.conversation(toValue(id) ?? '')),
    queryFn: async (): Promise<UiConversation> => {
      const c = await apiClient<Conversation>(conversationPath(toValue(id)!))
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

  return useApiMutation({
    mutationFn: (id: string) => apiClient<void>(conversationPath(id), { method: 'DELETE' }),
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
