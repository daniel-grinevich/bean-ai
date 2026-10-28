<script setup lang="ts">
import { ArrowDown } from '@lucide/vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { useScroll } from '@vueuse/core'
import { computed, nextTick, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import type { UiMessage } from '@/lib/types'
import ChatMessage from './ChatMessage.vue'

const props = defineProps<{ messages: UiMessage[]; streaming: boolean; canRetry: boolean }>()
const emit = defineEmits<{ retry: [id: string] }>()

const scrollEl = ref<HTMLElement | null>(null)

// Only the messages in (and near) the viewport are mounted, so long conversations stay fast.
const virtualizer = useVirtualizer(
  computed(() => ({
    count: props.messages.length,
    getScrollElement: () => scrollEl.value,
    estimateSize: (i: number) => (props.messages[i]?.role === 'user' ? 64 : 160),
    getItemKey: (i: number) => props.messages[i]?.id ?? i,
    overscan: 6,
    paddingStart: 24,
    paddingEnd: 24,
  })),
)
const items = computed(() => virtualizer.value.getVirtualItems())

function measure(el: unknown) {
  if (el instanceof Element) virtualizer.value.measureElement(el)
}

// Follow the reply while the user is at the bottom; stop following if they scroll up.
const { arrivedState } = useScroll(scrollEl, { offset: { bottom: 80 } })
const pinned = ref(true)
watch(
  () => arrivedState.bottom,
  (atBottom) => (pinned.value = atBottom),
)

function scrollToBottom(behavior: ScrollBehavior = 'auto') {
  const el = scrollEl.value
  if (!el || !props.messages.length) return
  virtualizer.value.scrollToIndex(props.messages.length - 1, { align: 'end' })
  // Item sizes settle after measuring; finish with a native scroll to the true bottom.
  requestAnimationFrame(() => el.scrollTo({ top: el.scrollHeight, behavior }))
}

const lastContent = computed(() => props.messages.at(-1)?.content.length ?? 0)
watch(
  () => props.messages.length,
  async (n, old) => {
    await nextTick()
    // A new turn or a freshly opened conversation always jumps to the bottom.
    if (n > (old ?? 0)) {
      pinned.value = true
      scrollToBottom()
    }
  },
  { immediate: true },
)
watch(lastContent, async () => {
  if (!pinned.value) return
  await nextTick()
  scrollToBottom()
})

defineExpose({ scrollToBottom })
</script>

<template>
  <div class="relative min-h-0 flex-1">
    <div
      ref="scrollEl"
      class="h-full overflow-y-auto overscroll-contain [overflow-anchor:none] focus-visible:outline-none"
      role="log"
      aria-label="Conversation"
      aria-live="polite"
      :aria-busy="streaming"
      tabindex="0"
    >
      <div
        class="relative mx-auto w-full max-w-3xl px-4"
        :style="{ height: `${virtualizer.getTotalSize()}px` }"
      >
        <div
          v-for="item in items"
          :key="item.key as string"
          :ref="measure"
          :data-index="item.index"
          class="absolute inset-x-4 top-0 pb-6"
          :style="{ transform: `translateY(${item.start}px)` }"
        >
          <ChatMessage
            :message="messages[item.index]!"
            :can-retry="canRetry"
            @retry="emit('retry', $event)"
          />
        </div>
      </div>
    </div>

    <Transition
      enter-from-class="opacity-0 translate-y-2"
      leave-to-class="opacity-0 translate-y-2"
      enter-active-class="transition"
      leave-active-class="transition"
    >
      <Button
        v-if="!pinned"
        size="icon"
        variant="outline"
        class="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full shadow-md"
        aria-label="Scroll to latest message"
        @click="scrollToBottom('smooth')"
      >
        <ArrowDown />
      </Button>
    </Transition>
  </div>
</template>
