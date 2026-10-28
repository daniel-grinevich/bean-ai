<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '@/components/AppHeader.vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import EmptyState from '@/components/chat/EmptyState.vue'
import MessageList from '@/components/chat/MessageList.vue'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/api'
import { useConversationQuery, useDiscardFailedTurn, useSendMessage } from '@/queries'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{ conversationId?: string }>()

const chat = useChatStore()
const router = useRouter()
const id = computed(() => props.conversationId ?? null)

const conversation = useConversationQuery(id)
const send = useSendMessage()
const discardFailedTurn = useDiscardFailedTurn()

const messages = computed(() =>
  id.value ? (conversation.data.value?.messages ?? []) : chat.pendingMessages,
)
const notFound = computed(
  () => conversation.error.value instanceof ApiError && conversation.error.value.status === 404,
)
const showEmpty = computed(() => !id.value && !messages.value.length)
const streamingHere = computed(() => chat.isStreaming && chat.streamingConversationId === id.value)

function onSend(text: string) {
  if (chat.isStreaming) return
  send.mutate({ text, conversationId: id.value })
}

function onRetry(replyId: string) {
  const text = discardFailedTurn(id.value, replyId)
  if (text) onSend(text)
}

// Screen readers get one announcement per reply rather than every streamed token.
const announcement = ref('')
watch(
  () => chat.isStreaming,
  (streaming) => {
    if (streaming) announcement.value = 'Bean is replying…'
    else {
      const last = messages.value.at(-1)
      if (last?.role !== 'assistant') return
      announcement.value =
        last.status === 'error'
          ? `Error: ${last.error ?? 'something went wrong'}`
          : last.status === 'stopped'
            ? 'Reply stopped.'
            : `Bean replied: ${last.content}`
    }
  },
)
</script>

<template>
  <AppHeader :title="conversation.data.value?.title" />

  <div class="sr-only" aria-live="polite" aria-atomic="true">{{ announcement }}</div>

  <div
    v-if="id && conversation.isPending.value"
    class="mx-auto w-full max-w-3xl flex-1 space-y-6 px-4 py-6"
    aria-label="Loading conversation"
  >
    <Skeleton class="ml-auto h-10 w-1/2 rounded-2xl" />
    <div class="space-y-2">
      <Skeleton class="h-4 w-5/6" />
      <Skeleton class="h-4 w-2/3" />
      <Skeleton class="h-4 w-3/4" />
    </div>
  </div>

  <div
    v-else-if="id && conversation.isError.value"
    class="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center"
  >
    <p class="font-medium">
      {{ notFound ? 'Conversation not found' : "Couldn't load this conversation" }}
    </p>
    <p class="max-w-sm text-sm text-muted-foreground">
      {{
        notFound
          ? 'It may have been deleted, or the server restarted (history is kept in memory).'
          : conversation.error.value?.message
      }}
    </p>
    <div class="flex gap-2">
      <Button v-if="!notFound" variant="outline" @click="conversation.refetch()">Try again</Button>
      <Button @click="router.push('/')">New chat</Button>
    </div>
  </div>

  <EmptyState v-else-if="showEmpty" @pick="onSend" />

  <MessageList
    v-else
    :messages="messages"
    :streaming="streamingHere"
    :can-retry="!chat.isStreaming"
    @retry="onRetry"
  />

  <ChatComposer
    :draft-key="id ?? 'new'"
    :streaming="chat.isStreaming"
    :disabled="!!id && conversation.isError.value"
    @send="onSend"
    @stop="chat.stop()"
  />
</template>
