<script setup lang="ts">
import { ArrowUp, Square } from '@lucide/vue'
import { useForm } from '@tanstack/vue-form'
import { useHotkey } from '@tanstack/vue-hotkeys'
import { useDebouncer } from '@tanstack/vue-pacer'
import { computed, nextTick, ref, watch } from 'vue'
import * as z from 'zod/mini'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useUiStore } from '@/stores/ui'

const MAX_LENGTH = 8000

const props = defineProps<{ draftKey: string; streaming: boolean; disabled?: boolean }>()
const emit = defineEmits<{ send: [text: string]; stop: [] }>()

const ui = useUiStore()
const textarea = ref<InstanceType<typeof Textarea> | null>(null)
const el = computed(() => (textarea.value?.$el as HTMLTextAreaElement | undefined) ?? null)

const tooLong = z
  .string()
  .check(z.maxLength(MAX_LENGTH, `Keep it under ${MAX_LENGTH.toLocaleString()} characters`))
const messageSchema = tooLong.check(z.refine((v) => v.trim().length > 0, 'Type a message first'))

const form = useForm({
  defaultValues: { message: ui.getDraft(props.draftKey) },
  onSubmit: ({ value, formApi }) => {
    emit('send', value.message.trim())
    formApi.reset({ message: '' })
    saveDraft.cancel()
    ui.setDraft(props.draftKey, '')
  },
})

const canSend = form.useStore(
  (s) => s.values.message.trim().length > 0 && s.values.message.length <= MAX_LENGTH,
)

// Persisting drafts on every keystroke would hammer localStorage; debounce it.
const saveDraft = useDebouncer((key: string, text: string) => ui.setDraft(key, text), { wait: 400 })

// Switching conversations swaps in that conversation's draft.
watch(
  () => props.draftKey,
  (key, oldKey) => {
    if (oldKey !== undefined) {
      saveDraft.flush()
      form.reset({ message: ui.getDraft(key) })
    }
  },
)

function submit() {
  if (props.streaming || props.disabled) return
  void form.handleSubmit()
}

// Enter sends (or ⌘/Ctrl+Enter, if the user turned that off); Shift+Enter is a newline.
useHotkey(
  () => (ui.enterToSend ? 'Enter' : 'Mod+Enter'),
  (event) => {
    if (event.isComposing) return
    submit()
  },
  () => ({ target: el.value, ignoreInputs: false }),
)

function focus() {
  el.value?.focus()
}
defineExpose({
  focus,
  setText: async (text: string) => {
    form.setFieldValue('message', text)
    await nextTick()
    focus()
  },
})
</script>

<template>
  <form class="mx-auto w-full max-w-3xl px-4 pb-4" novalidate @submit.prevent="submit">
    <form.Field name="message" :validators="{ onSubmit: messageSchema, onChange: tooLong }">
      <template #default="{ field }">
        <div
          class="relative rounded-2xl border bg-card shadow-sm transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30"
        >
          <label for="composer" class="sr-only">Message Bean</label>
          <Textarea
            id="composer"
            ref="textarea"
            :model-value="field.state.value"
            :disabled="disabled"
            :aria-invalid="field.state.meta.errors.length > 0 || undefined"
            aria-describedby="composer-hint composer-error"
            placeholder="Ask Bean about your machines…"
            rows="1"
            class="max-h-60 min-h-14 resize-none border-0 bg-transparent py-4 pr-14 pl-4 shadow-none focus-visible:ring-0 dark:bg-transparent"
            @update:model-value="
              (v) => {
                field.handleChange(String(v))
                saveDraft.maybeExecute(draftKey, String(v))
              }
            "
            @blur="field.handleBlur"
          />
          <div class="absolute right-2.5 bottom-2.5">
            <Tooltip v-if="streaming">
              <TooltipTrigger as-child>
                <Button
                  type="button"
                  size="icon"
                  class="rounded-full"
                  aria-label="Stop generating"
                  @click="emit('stop')"
                >
                  <Square class="fill-current" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Stop <kbd class="ml-1 opacity-70">Esc</kbd></TooltipContent>
            </Tooltip>
            <Tooltip v-else>
              <TooltipTrigger as-child>
                <Button
                  type="submit"
                  size="icon"
                  class="rounded-full"
                  aria-label="Send message"
                  :disabled="!canSend || disabled"
                >
                  <ArrowUp />
                </Button>
              </TooltipTrigger>
              <TooltipContent
                >Send
                <kbd class="ml-1 opacity-70">{{ ui.enterToSend ? '↵' : '⌘↵' }}</kbd></TooltipContent
              >
            </Tooltip>
          </div>
        </div>
        <div class="mt-1.5 flex min-h-5 justify-between gap-2 px-1 text-xs text-muted-foreground">
          <p id="composer-error" class="text-destructive" aria-live="polite">
            {{
              field.state.meta.errors
                .map((e) => (typeof e === 'string' ? e : e?.message))
                .join(', ')
            }}
          </p>
          <p id="composer-hint" class="hidden text-right sm:block">
            <template v-if="ui.enterToSend"><kbd>↵</kbd> send · <kbd>⇧↵</kbd> newline</template>
            <template v-else><kbd>⌘↵</kbd> send · <kbd>↵</kbd> newline</template>
            · <kbd>/</kbd> focus · <kbd>⌘K</kbd> new chat
          </p>
        </div>
      </template>
    </form.Field>
  </form>
</template>
