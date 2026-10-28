import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import type { UiMessage } from '@/lib/types'

// The conversation the user is looking at, plus the in-flight stream (if any).
export const useChatStore = defineStore('chat', () => {
  const currentConversationId = ref<string | null>(null)

  // Messages for a brand-new chat, before the server has told us its id.
  const pendingMessages = ref<UiMessage[]>([])

  const streamingConversationId = ref<string | null>(null)
  const isStreaming = ref(false)
  const controller = shallowRef<AbortController | null>(null)

  function stop() {
    controller.value?.abort()
  }

  return {
    currentConversationId,
    pendingMessages,
    streamingConversationId,
    isStreaming,
    controller,
    stop,
  }
})
