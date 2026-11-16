import { computed } from 'vue'
import { apiClient } from '@/lib/apiClient'
import { queryKeys } from '@/lib/queryKeys'
import { useUiStore } from '@/stores/ui'
import type { ModelList } from '@/types/model'
import { useApi } from './useApi'

export function useModels() {
  return useApi({
    queryKey: queryKeys.models,
    queryFn: () => apiClient<ModelList>('/api/models'),
    staleTime: 5 * 60_000,
  })
}

// The model to send with: the saved choice if the server still offers it and has its key, else the
// server default. Null until the list loads, which lets the server pick its default.
export function useSelectedModel() {
  const ui = useUiStore()
  const models = useModels()
  return computed(() => {
    const list = models.data.value
    if (!list) return null
    const saved = list.models.find((m) => m.id === ui.model)
    return saved?.available ? saved.id : list.default
  })
}
