// Client for the bean backend: the only place the app calls fetch(). Every request goes through the
// Vite dev proxy at /api. Failures always reject with ApiError, so callers can rely on `status`.
import { ApiError } from '@/lib/apiError'

// Sends a request and returns the raw response for callers that read the body themselves (streams).
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch (err) {
    throw toNetworkError(err)
  }
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status)
  return res
}

// Sends a request and parses the JSON body; 204 resolves to undefined.
export async function apiClient<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init)
  if (res.status === 204) return undefined as T
  try {
    return (await res.json()) as T
  } catch (err) {
    if (err instanceof SyntaxError) throw new ApiError(err.message, res.status, { cause: err })
    throw toNetworkError(err)
  }
}

// fetch() and body reads reject with a TypeError when the network fails. An abort rejects with an
// AbortError instead; that passes through unchanged because callers check their own signal.
export function toNetworkError(err: unknown): unknown {
  return err instanceof TypeError ? new ApiError(err.message, 0, { cause: err }) : err
}

// FastAPI errors look like {"detail": "..."}; fall back to the status line.
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // not JSON
  }
  return `Request failed: ${res.status} ${res.statusText}`.trim()
}
