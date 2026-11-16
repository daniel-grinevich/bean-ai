// Mirrors backend/src/bean_ai_backend/schemas/models.py.

export type ModelProvider = 'anthropic' | 'openrouter'

export interface ModelInfo {
  id: string
  label: string
  provider: ModelProvider
  // False when the server has no API key for the provider.
  available: boolean
}

export interface ModelList {
  default: string
  models: ModelInfo[]
}
