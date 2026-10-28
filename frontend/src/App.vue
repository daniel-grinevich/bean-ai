<script setup lang="ts">
import { useHotkey } from '@tanstack/vue-hotkeys'
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import ConversationSidebar from '@/components/ConversationSidebar.vue'
import SettingsDialog from '@/components/SettingsDialog.vue'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { focusComposer, useAppActions } from '@/composables/useAppActions'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const chat = useChatStore()
const route = useRoute()
const { newChat, toggleSidebar, isDesktop } = useAppActions()

watch(
  () => route.params.conversationId,
  (id) => (chat.currentConversationId = typeof id === 'string' ? id : null),
  { immediate: true },
)
watch(isDesktop, (desktop) => desktop && (ui.mobileSidebarOpen = false))

// Global shortcuts. Enter/Shift+Enter live on the composer itself.
useHotkey('Mod+K', () => void newChat())
useHotkey('Mod+B', toggleSidebar)
useHotkey('/', focusComposer)
useHotkey(
  'Escape',
  () => chat.stop(),
  () => ({ enabled: chat.isStreaming, preventDefault: false }),
)
</script>

<template>
  <TooltipProvider :delay-duration="300">
    <a
      href="#composer"
      class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:ring-2 focus:ring-ring"
    >
      Skip to message box
    </a>
    <div class="flex h-dvh overflow-hidden bg-background text-foreground">
      <aside
        v-if="isDesktop"
        class="shrink-0 overflow-hidden border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200"
        :class="ui.sidebarOpen ? 'w-72' : 'w-0 border-r-0'"
        :inert="!ui.sidebarOpen || undefined"
      >
        <div class="h-full w-72">
          <ConversationSidebar @new-chat="newChat" />
        </div>
      </aside>

      <Sheet v-else v-model:open="ui.mobileSidebarOpen">
        <SheetContent side="left" class="w-80 gap-0 bg-sidebar p-0">
          <SheetHeader class="sr-only">
            <SheetTitle>Conversations</SheetTitle>
            <SheetDescription>Switch, start or delete conversations.</SheetDescription>
          </SheetHeader>
          <ConversationSidebar @new-chat="newChat" @navigate="ui.mobileSidebarOpen = false" />
        </SheetContent>
      </Sheet>

      <main class="flex min-w-0 flex-1 flex-col">
        <RouterView />
      </main>
    </div>
    <SettingsDialog />
    <Toaster rich-colors close-button position="top-center" />
  </TooltipProvider>
</template>
