<script setup lang="ts">
import { Coffee, Copy, RotateCcw, TriangleAlert } from '@lucide/vue'
import { useClipboard } from '@vueuse/core'
import { toast } from 'vue-sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { UiMessage } from '@/lib/types'
import MarkdownContent from './MarkdownContent.vue'

const props = defineProps<{ message: UiMessage; canRetry: boolean }>()
const emit = defineEmits<{ retry: [id: string] }>()

const { copy } = useClipboard({ legacy: true })
async function copyMessage() {
  await copy(props.message.content)
  toast.success('Copied to clipboard')
}
</script>

<template>
  <article v-if="message.role === 'user'" class="flex justify-end" aria-label="You said">
    <div
      class="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 whitespace-pre-wrap text-primary-foreground sm:max-w-[75%]"
    >
      {{ message.content }}
    </div>
  </article>

  <article v-else class="group flex gap-3" aria-label="Bean said">
    <div
      class="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border bg-card"
      aria-hidden="true"
    >
      <Coffee class="size-4 text-muted-foreground" />
    </div>
    <div class="min-w-0 flex-1">
      <div
        v-if="message.status === 'streaming' && !message.content"
        class="space-y-2 pt-1.5"
        aria-hidden="true"
      >
        <Skeleton class="h-3.5 w-3/4" />
        <Skeleton class="h-3.5 w-1/2" />
      </div>
      <MarkdownContent
        v-else-if="message.content"
        :text="message.content"
        :streaming="message.status === 'streaming'"
        :class="{ 'streaming-caret': message.status === 'streaming' }"
      />

      <div
        v-if="message.status === 'error'"
        class="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        role="alert"
      >
        <TriangleAlert class="size-4 shrink-0" aria-hidden="true" />
        <span class="min-w-0 flex-1">{{ message.error || 'Something went wrong.' }}</span>
        <Button v-if="canRetry" size="sm" variant="outline" @click="emit('retry', message.id)">
          <RotateCcw /> Retry
        </Button>
      </div>

      <div
        v-if="message.status !== 'streaming' && message.content"
        class="mt-1 flex items-center gap-1"
      >
        <Badge v-if="message.status === 'stopped'" variant="secondary" class="mr-1">Stopped</Badge>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              size="icon-xs"
              variant="ghost"
              aria-label="Copy message"
              class="transition-opacity sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100"
              @click="copyMessage"
            >
              <Copy />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Copy message</TooltipContent>
        </Tooltip>
      </div>
    </div>
  </article>
</template>
