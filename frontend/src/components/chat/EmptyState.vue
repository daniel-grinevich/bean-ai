<script setup lang="ts">
import { Activity, Coffee, MapPin, Wrench } from '@lucide/vue'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const emit = defineEmits<{ pick: [prompt: string] }>()

// Suggestions only for now; live data arrives once bean is wired to the Navi MCP server and crumb.
const examples = [
  { icon: Activity, title: 'Which machines are offline?', hint: 'Live fleet status' },
  { icon: MapPin, title: 'How did HQ Lobby do this week?', hint: 'Sales and cups by location' },
  { icon: Wrench, title: 'Which machines need descaling soon?', hint: 'Maintenance schedule' },
  {
    icon: Coffee,
    title: 'What were our top 5 drinks last month?',
    hint: 'Product mix across the fleet',
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-4 py-10">
    <div class="mb-8 text-center">
      <div
        class="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground"
      >
        <Coffee class="size-6" aria-hidden="true" />
      </div>
      <h2 class="font-heading text-2xl font-semibold tracking-tight">How can Bean help today?</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Your ops assistant for the Navi coffee-machine fleet.
      </p>
    </div>
    <ul class="grid gap-3 sm:grid-cols-2" aria-label="Example prompts">
      <li v-for="ex in examples" :key="ex.title">
        <button
          type="button"
          class="group block h-full w-full rounded-xl text-left focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          @click="emit('pick', ex.title)"
        >
          <Card class="h-full gap-1 py-4 transition-colors group-hover:bg-muted/60">
            <CardHeader class="px-4">
              <CardTitle class="flex items-start gap-2 text-sm font-medium">
                <component
                  :is="ex.icon"
                  class="mt-0.5 size-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                {{ ex.title }}
              </CardTitle>
              <CardDescription class="pl-6 text-xs">{{ ex.hint }}</CardDescription>
            </CardHeader>
          </Card>
        </button>
      </li>
    </ul>
  </div>
</template>
