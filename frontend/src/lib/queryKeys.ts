// Every TanStack Query key in the app. Composables read and invalidate through these, never literals.
export const queryKeys = {
  health: ['health'] as const,
  models: ['models'] as const,
  conversations: ['conversations'] as const,
  conversation: (id: string) => ['conversation', id] as const,
}
