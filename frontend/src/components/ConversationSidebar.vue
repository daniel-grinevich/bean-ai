<script setup lang="ts">
import { Ellipsis, MessageSquare, SquarePen, Trash2 } from '@lucide/vue'
import { formatTimeAgo } from '@vueuse/core'
import { ref } from 'vue'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import type { ConversationSummary } from '@/api'
import { useConversationsQuery, useDeleteConversation } from '@/queries'
import { useChatStore } from '@/stores/chat'

defineProps<{ inSheet?: boolean }>()
const emit = defineEmits<{ navigate: []; newChat: [] }>()

const chat = useChatStore()
const conversations = useConversationsQuery()
const remove = useDeleteConversation()

const pendingDelete = ref<ConversationSummary | null>(null)
function confirmDelete() {
  if (pendingDelete.value) remove.mutate(pendingDelete.value.id)
  pendingDelete.value = null
}

const timeAgo = (iso: string) => formatTimeAgo(new Date(iso))
</script>

<template>
  <nav class="flex h-full min-h-0 flex-col" aria-label="Conversations">
    <div class="flex items-center gap-2 p-3" :class="{ 'pr-14': inSheet }">
      <Button variant="outline" class="flex-1 justify-start" @click="emit('newChat')">
        <SquarePen /> New chat
        <kbd v-if="!inSheet" class="ml-auto text-[10px] text-muted-foreground">⌘K</kbd>
      </Button>
    </div>
    <Separator />
    <ScrollArea class="min-h-0 flex-1">
      <div class="p-2">
        <p class="px-2 pt-2 pb-1 text-xs font-medium text-muted-foreground">Recent</p>

        <div
          v-if="conversations.isPending.value"
          class="space-y-2 p-2"
          aria-label="Loading conversations"
        >
          <Skeleton v-for="i in 5" :key="i" class="h-8 w-full" />
        </div>

        <div
          v-else-if="conversations.isError.value"
          class="space-y-2 px-2 py-3 text-sm text-muted-foreground"
        >
          <p>Couldn't load conversations.</p>
          <Button size="sm" variant="outline" @click="conversations.refetch()">Try again</Button>
        </div>

        <p
          v-else-if="!conversations.data.value?.length"
          class="px-2 py-3 text-sm text-muted-foreground"
        >
          No conversations yet.
        </p>

        <ul v-else class="space-y-0.5">
          <li v-for="c in conversations.data.value" :key="c.id" class="group/item relative">
            <RouterLink
              :to="`/c/${c.id}`"
              class="flex items-center gap-2 rounded-lg py-2 pr-9 pl-2 text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              :class="{ 'bg-muted font-medium': chat.currentConversationId === c.id }"
              :aria-current="chat.currentConversationId === c.id ? 'page' : undefined"
              @click="emit('navigate')"
            >
              <MessageSquare class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span class="min-w-0 flex-1">
                <span class="block truncate">{{ c.title || 'Untitled' }}</span>
                <span class="block text-xs font-normal text-muted-foreground">{{
                  timeAgo(c.updated_at)
                }}</span>
              </span>
            </RouterLink>
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button
                  size="icon-xs"
                  variant="ghost"
                  class="absolute top-1/2 right-1.5 -translate-y-1/2 opacity-100 group-hover/item:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 md:opacity-0"
                  :aria-label="`Options for ${c.title || 'conversation'}`"
                >
                  <Ellipsis />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem variant="destructive" @select="pendingDelete = c">
                  <Trash2 /> Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </li>
        </ul>
      </div>
    </ScrollArea>

    <AlertDialog :open="!!pendingDelete" @update:open="(open) => !open && (pendingDelete = null)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this conversation?</AlertDialogTitle>
          <AlertDialogDescription>
            “{{ pendingDelete?.title }}” will be removed for good.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="confirmDelete">Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </nav>
</template>
