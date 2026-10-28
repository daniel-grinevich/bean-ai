<script setup lang="ts">
import { useForm } from '@tanstack/vue-form'
import { watch } from 'vue'
import { toast } from 'vue-sonner'
import * as z from 'zod/mini'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Switch } from '@/components/ui/switch'
import { type ThemePreference, useUiStore } from '@/stores/ui'

const ui = useUiStore()

const settingsSchema = z.object({
  theme: z.enum(['system', 'light', 'dark']),
  enterToSend: z.boolean(),
})

const form = useForm({
  defaultValues: { theme: ui.theme as ThemePreference, enterToSend: ui.enterToSend },
  validators: { onSubmit: settingsSchema },
  onSubmit: ({ value }) => {
    ui.theme = value.theme
    ui.enterToSend = value.enterToSend
    ui.settingsOpen = false
    toast.success('Settings saved')
  },
})

// Start from the saved values every time the dialog opens.
watch(
  () => ui.settingsOpen,
  (open) => open && form.reset({ theme: ui.theme, enterToSend: ui.enterToSend }),
)

const themes: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]
</script>

<template>
  <Dialog v-model:open="ui.settingsOpen">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Settings</DialogTitle>
        <DialogDescription>Saved in this browser.</DialogDescription>
      </DialogHeader>
      <form id="settings-form" class="space-y-6" @submit.prevent="form.handleSubmit()">
        <form.Field name="theme">
          <template #default="{ field }">
            <fieldset class="space-y-3">
              <legend class="mb-3 text-sm font-medium">Theme</legend>
              <RadioGroup
                :model-value="field.state.value"
                class="grid grid-cols-3 gap-2"
                @update:model-value="(v) => field.handleChange(v as ThemePreference)"
              >
                <Label
                  v-for="t in themes"
                  :key="t.value"
                  class="flex cursor-pointer items-center gap-2 rounded-lg border p-3 has-data-[state=checked]:border-primary"
                >
                  <RadioGroupItem :value="t.value" />
                  {{ t.label }}
                </Label>
              </RadioGroup>
            </fieldset>
          </template>
        </form.Field>
        <form.Field name="enterToSend">
          <template #default="{ field }">
            <div class="flex items-center justify-between gap-4">
              <Label for="enter-to-send" class="flex-col items-start gap-1">
                <span>Enter sends the message</span>
                <span class="text-xs font-normal text-muted-foreground">
                  Off: use ⌘/Ctrl+Enter to send and Enter for a new line.
                </span>
              </Label>
              <Switch
                id="enter-to-send"
                :model-value="field.state.value"
                @update:model-value="(v) => field.handleChange(v)"
              />
            </div>
          </template>
        </form.Field>
      </form>
      <DialogFooter>
        <Button variant="outline" @click="ui.settingsOpen = false">Cancel</Button>
        <Button type="submit" form="settings-form">Save</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
