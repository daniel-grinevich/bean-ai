<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { streamChat } from './api'

interface Message {
  role: 'user' | 'assistant'
  text: string
  error?: boolean
}

const messages = ref<Message[]>([])
const input = ref('')
const busy = ref(false)
const conversationId = ref<string | null>(null)
const log = ref<HTMLElement | null>(null)

async function scrollToBottom() {
  await nextTick()
  log.value?.scrollTo({ top: log.value.scrollHeight })
}

async function send() {
  const text = input.value.trim()
  if (!text || busy.value) return
  input.value = ''
  busy.value = true
  messages.value.push({ role: 'user', text })
  messages.value.push({ role: 'assistant', text: '' })
  const reply = messages.value[messages.value.length - 1]!
  scrollToBottom()

  try {
    for await (const ev of streamChat(text, conversationId.value)) {
      if (ev.event === 'start') conversationId.value = ev.data.conversation_id
      else if (ev.event === 'delta') reply.text += ev.data.text
      else if (ev.event === 'error') {
        reply.text = ev.data.message
        reply.error = true
      }
      scrollToBottom()
    }
  } catch (err) {
    reply.text = err instanceof Error ? err.message : String(err)
    reply.error = true
  } finally {
    busy.value = false
  }
}

function newChat() {
  messages.value = []
  conversationId.value = null
}
</script>

<template>
  <main class="chat">
    <header>
      <h1>Bean</h1>
      <button class="ghost" :disabled="busy" @click="newChat">New chat</button>
    </header>

    <section ref="log" class="log">
      <p v-if="!messages.length" class="empty">Ask Bean anything.</p>
      <div
        v-for="(m, i) in messages"
        :key="i"
        class="msg"
        :class="[m.role, { error: m.error }]"
      >
        {{ m.text || '…' }}
      </div>
    </section>

    <form class="composer" @submit.prevent="send">
      <textarea
        v-model="input"
        rows="1"
        placeholder="Message Bean"
        @keydown.enter.exact.prevent="send"
      />
      <button type="submit" :disabled="busy || !input.trim()">Send</button>
    </form>
  </main>
</template>
