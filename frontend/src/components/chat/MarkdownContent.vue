<script setup lang="ts">
import { useThrottledValue } from '@tanstack/vue-pacer'
import { useClipboard } from '@vueuse/core'
import { computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import DataTable from '@/components/DataTable.vue'
import { highlighter, loadHighlighter, toSegments } from '@/lib/markdown'

const props = defineProps<{ text: string; streaming?: boolean }>()

// Re-parsing markdown on every token is wasteful; while streaming, render at most ~12 times a second.
const [throttledText] = useThrottledValue(() => props.text, { wait: 80 })
const source = computed(() => (props.streaming ? throttledText.value : props.text))

const segments = computed(() => {
  void highlighter.value // re-render once Shiki has loaded
  return toSegments(source.value)
})

onMounted(loadHighlighter)

const { copy } = useClipboard({ legacy: true })
async function onClick(e: MouseEvent) {
  const button = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-copy]')
  if (!button) return
  const code = button.closest('.code-block')?.querySelector('pre')?.textContent ?? ''
  await copy(code)
  button.textContent = 'Copied'
  toast.success('Copied to clipboard')
  setTimeout(() => (button.textContent = 'Copy'), 1500)
}
</script>

<template>
  <div class="prose-bean" @click="onClick">
    <template v-for="(seg, i) in segments" :key="i">
      <!-- markdown-it runs with html: false, so this is escaped markdown output, not raw HTML. -->
      <div v-if="seg.kind === 'html'" v-html="seg.html" />
      <div v-else>
        <DataTable :columns="seg.columns" :rows="seg.rows" :caption="`Table ${i + 1}`" />
        <details v-if="seg.raw" class="-mt-1 mb-3 text-xs text-muted-foreground">
          <summary class="cursor-pointer select-none">Raw JSON</summary>
          <pre class="mt-2 overflow-auto rounded-md bg-muted p-3">{{ seg.raw }}</pre>
        </details>
      </div>
    </template>
  </div>
</template>
