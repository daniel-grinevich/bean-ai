import { apiClient } from '@/lib/apiClient'
import { queryKeys } from '@/lib/queryKeys'
import type { Health } from '@/types/health'
import { useApi } from './useApi'

export function useHealth() {
  return useApi({
    queryKey: queryKeys.health,
    queryFn: () => apiClient<Health>('/api/health'),
    refetchInterval: 30_000,
    retry: false,
  })
}
