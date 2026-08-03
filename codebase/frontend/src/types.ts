export interface PageSummary {
  page: number
  char_count: number
}

export interface DocumentSummary {
  id: string
  filename: string
  page_count: number
  uploaded_at: string
  size_bytes: number
  scanned: boolean
}

export interface DocumentDetail extends DocumentSummary {
  pages: PageSummary[]
}

export interface Citation {
  page: number
  quote: string
  verified: boolean
}

export interface WebSource {
  title: string
  url: string
}

export interface ApiHighlight {
  page: number
  text: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  citations: Citation[]
  grounded: boolean
  highlights: ApiHighlight[]
  screenshot_count: number
  web_sources: WebSource[]
}

export interface AskResponse {
  session_id: string
  message: ChatMessage
  suggested_followups: string[]
}

export interface SessionSummary {
  id: string
  document_id: string
  created_at: string
  message_count: number
}

export interface QuizQuestion {
  question: string
  options: string[]
  correct_index: number
  explanation: string
  source_page: number
  evidence_quote: string
  verified: boolean
}

export interface QuizResponse {
  document_id: string
  questions: QuizQuestion[]
  dropped: number
}

/** A rectangle stored as fractions of the page box, so it survives zooming. */
export interface NormalizedRect {
  x: number
  y: number
  w: number
  h: number
}

export interface Highlight {
  id: string
  page: number
  text: string
  rects: NormalizedRect[]
}

export interface Screenshot {
  id: string
  page: number
  dataUrl: string
}
