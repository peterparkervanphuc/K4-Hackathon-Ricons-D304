import type {
  AskResponse,
  DocumentDetail,
  DocumentSummary,
  QuizResponse,
  SessionSummary,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function json(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export const api = {
  health: () =>
    request<{ status: string; openai_configured: boolean; model: string; documents: number }>(
      '/api/health',
    ),

  listDocuments: () => request<DocumentSummary[]>('/api/documents'),

  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentDetail>('/api/documents', { method: 'POST', body: form })
  },

  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: 'DELETE' }),

  documentFileUrl: (id: string) => `${BASE}/api/documents/${id}/file`,

  createSession: (documentId: string) =>
    request<SessionSummary>('/api/chat/sessions', json({ document_id: documentId })),

  ask: (
    sessionId: string,
    payload: {
      question: string
      page: number | null
      highlights: { page: number; text: string }[]
      screenshots: { page: number; data_url: string }[]
      use_web: boolean
    },
  ) => request<AskResponse>(`/api/chat/sessions/${sessionId}/ask`, json(payload)),

  quiz: (payload: {
    document_id: string
    num_questions: number
    page_from: number | null
    page_to: number | null
    difficulty: 'easy' | 'medium' | 'hard'
  }) => request<QuizResponse>('/api/quiz', json(payload)),
}
