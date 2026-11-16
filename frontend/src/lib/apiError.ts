// Every failed request surfaces as an ApiError. `status` is the HTTP status, or 0 when the request
// never got a response (server down, offline, connection dropped mid-stream).
export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number, options?: ErrorOptions) {
    super(message, options)
    this.name = 'ApiError'
    this.status = status
  }
}
