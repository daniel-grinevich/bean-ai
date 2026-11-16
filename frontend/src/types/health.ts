// GET /api/health (backend/src/bean_ai_backend/routers/health.py returns a plain dict).

export interface Health {
  status: string
  model?: string
}
