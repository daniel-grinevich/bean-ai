import { useLocalStorage, usePreferredDark } from '@vueuse/core'
import { defineStore } from 'pinia'
import { computed, ref, watchEffect } from 'vue'

export type ThemePreference = 'system' | 'light' | 'dark'

// Client-only UI state. Server data (conversations, messages) lives in TanStack Query.
export const useUiStore = defineStore('ui', () => {
  const sidebarOpen = useLocalStorage('bean:sidebar-open', true)
  const mobileSidebarOpen = ref(false)
  const theme = useLocalStorage<ThemePreference>('bean:theme', 'system')
  const enterToSend = useLocalStorage('bean:enter-to-send', true)
  const settingsOpen = ref(false)

  const prefersDark = usePreferredDark()
  const isDark = computed(
    () => theme.value === 'dark' || (theme.value === 'system' && prefersDark.value),
  )
  watchEffect(() => document.documentElement.classList.toggle('dark', isDark.value))

  // Unsent composer text per conversation ("new" for a chat that has no id yet).
  const drafts = useLocalStorage<Record<string, string>>('bean:drafts', {})
  function getDraft(key: string) {
    return drafts.value[key] ?? ''
  }
  function setDraft(key: string, text: string) {
    if (text) drafts.value = { ...drafts.value, [key]: text }
    else if (key in drafts.value) {
      const { [key]: _removed, ...rest } = drafts.value
      drafts.value = rest
    }
  }

  return {
    sidebarOpen,
    mobileSidebarOpen,
    theme,
    isDark,
    enterToSend,
    settingsOpen,
    getDraft,
    setDraft,
  }
})
