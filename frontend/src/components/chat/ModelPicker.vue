<script setup lang="ts">
import { Check, ChevronDown } from '@lucide/vue'
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useModelsQuery, useSelectedModel } from '@/queries'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const models = useModelsQuery()
const selected = useSelectedModel()

const current = computed(() => models.data.value?.models.find((m) => m.id === selected.value))
</script>

<template>
  <DropdownMenu v-if="models.data.value">
    <DropdownMenuTrigger as-child>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        class="-ml-2 h-6 gap-1 px-2 text-xs font-normal text-muted-foreground"
        aria-label="Choose model"
      >
        {{ current?.label ?? 'Model' }}
        <ChevronDown class="size-3" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="min-w-52">
      <DropdownMenuLabel>Model</DropdownMenuLabel>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        v-for="m in models.data.value.models"
        :key="m.id"
        :disabled="!m.available"
        @select="ui.model = m.id"
      >
        <Check class="size-4" :class="m.id === selected ? 'opacity-100' : 'opacity-0'" />
        <span class="flex-1">{{ m.label }}</span>
        <span v-if="!m.available" class="text-xs text-muted-foreground">key not set</span>
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
