import { nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'

export function focusComposer() {
  document.getElementById('composer')?.focus()
}

export function useAppActions() {
  const router = useRouter()
  const chat = useChatStore()
  const ui = useUiStore()
  const isDesktop = useMediaQuery('(min-width: 768px)')

  async function newChat() {
    ui.mobileSidebarOpen = false
    if (!chat.isStreaming) chat.pendingMessages = []
    await router.push('/')
    await nextTick()
    focusComposer()
  }

  function toggleSidebar() {
    if (isDesktop.value) ui.sidebarOpen = !ui.sidebarOpen
    else ui.mobileSidebarOpen = !ui.mobileSidebarOpen
  }

  return { newChat, toggleSidebar, isDesktop }
}
