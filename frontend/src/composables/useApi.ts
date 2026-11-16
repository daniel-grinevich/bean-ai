// The one way the app talks to TanStack Query. Same options and same full result as useQuery and
// useMutation; the wrapper only sets app-wide defaults. Today that is the error type: apiClient
// rejects with ApiError, so TError defaults to it.
import {
  type QueryClient,
  type QueryKey,
  useMutation,
  type UseMutationOptions,
  type UseMutationReturnType,
  useQuery,
  type UseQueryOptions,
  type UseQueryReturnType,
} from '@tanstack/vue-query'
import type { MaybeRefOrGetter } from 'vue'
import type { ApiError } from '@/lib/apiError'

export function useApi<
  TQueryFnData = unknown,
  TError = ApiError,
  TData = TQueryFnData,
  TQueryKey extends QueryKey = QueryKey,
>(
  options: MaybeRefOrGetter<UseQueryOptions<TQueryFnData, TError, TData, TQueryFnData, TQueryKey>>,
  queryClient?: QueryClient,
): UseQueryReturnType<TData, TError> {
  return useQuery(options, queryClient)
}

export function useApiMutation<
  TData = unknown,
  TError = ApiError,
  TVariables = void,
  TOnMutateResult = unknown,
>(
  options: UseMutationOptions<TData, TError, TVariables, TOnMutateResult>,
  queryClient?: QueryClient,
): UseMutationReturnType<TData, TError, TVariables, TOnMutateResult> {
  return useMutation(options, queryClient)
}
