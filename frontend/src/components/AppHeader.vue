<script setup lang="ts">
import { Monitor, Moon, PanelLeft, Settings, Sun } from '@lucide/vue'
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useAppActions } from '@/composables/useAppActions'
import { useHealthQuery } from '@/queries'
import { type ThemePreference, useUiStore } from '@/stores/ui'

defineProps<{ title?: string }>()

const ui = useUiStore()
const { toggleSidebar } = useAppActions()
const health = useHealthQuery()

const status = computed(() => {
  if (health.isPending.value) return { label: 'Connecting…', dot: 'bg-muted-foreground' }
  if (health.isError.value) return { label: 'Backend offline', dot: 'bg-destructive' }
  return { label: health.data.value?.model ?? 'Online', dot: 'bg-emerald-500' }
})
</script>

<template>
  <header class="flex h-14 shrink-0 items-center gap-2 border-b px-3">
    <Tooltip>
      <TooltipTrigger as-child>
        <Button size="icon" variant="ghost" aria-label="Toggle sidebar" @click="toggleSidebar">
          <PanelLeft />
        </Button>
      </TooltipTrigger>
      <TooltipContent>Toggle sidebar <kbd class="ml-1 opacity-70">⌘B</kbd></TooltipContent>
    </Tooltip>

    <h1 class="min-w-0 flex-1 truncate text-sm font-medium">
      {{ title || 'Bean' }}
    </h1>

    <Badge variant="outline" class="hidden gap-1.5 font-normal sm:inline-flex" role="status">
      <span class="size-1.5 rounded-full" :class="status.dot" aria-hidden="true" />
      {{ status.label }}
    </Badge>

    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger as-child>
          <DropdownMenuTrigger as-child>
            <Button size="icon" variant="ghost" aria-label="Theme">
              <Sun class="dark:hidden" />
              <Moon class="hidden dark:block" />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>Theme</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup
          :model-value="ui.theme"
          @update:model-value="(v) => (ui.theme = v as ThemePreference)"
        >
          <DropdownMenuRadioItem value="light"><Sun /> Light</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark"><Moon /> Dark</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system"><Monitor /> System</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>

    <Tooltip>
      <TooltipTrigger as-child>
        <Button size="icon" variant="ghost" aria-label="Settings" @click="ui.settingsOpen = true">
          <Settings />
        </Button>
      </TooltipTrigger>
      <TooltipContent>Settings</TooltipContent>
    </Tooltip>
  </header>
</template>
