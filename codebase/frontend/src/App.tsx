import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from './api'
import { ChatPanel } from './components/ChatPanel'
import { Icon } from './components/Icon'
import { PdfViewer } from './components/PdfViewer'
import { QuizPanel } from './components/QuizPanel'
import { Sidebar } from './components/Sidebar'
import type { DocumentSummary, Highlight, NormalizedRect, Screenshot } from './types'

type Tab = 'tutor' | 'quiz'

const newId = () => Math.random().toString(36).slice(2, 10)

export default function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [tab, setTab] = useState<Tab>('tutor')

  const [highlights, setHighlights] = useState<Highlight[]>([])
  const [screenshots, setScreenshots] = useState<Screenshot[]>([])

  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [keyMissing, setKeyMissing] = useState(false)

  const active = useMemo(
    () => documents.find((document) => document.id === activeId) ?? null,
    [documents, activeId],
  )

  useEffect(() => {
    api
      .health()
      .then((health) => setKeyMissing(!health.openai_configured))
      .catch(() => setError('Cannot reach the API. Is the backend running on port 8000?'))

    api
      .listDocuments()
      .then((list) => {
        setDocuments(list)
        if (list.length) setActiveId((current) => current ?? list[0].id)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  const openDocument = useCallback((id: string) => {
    setActiveId(id)
    setPage(1)
    setHighlights([])
    setScreenshots([])
  }, [])

  const upload = async (file: File) => {
    setUploading(true)
    setError(null)
    try {
      const uploaded = await api.uploadDocument(file)
      setDocuments((prev) => [uploaded, ...prev.filter((d) => d.id !== uploaded.id)])
      openDocument(uploaded.id)
      if (uploaded.scanned) {
        setError(
          `"${uploaded.filename}" has almost no selectable text — it looks like a scan. ` +
            'Use "Capture area" to ask about it; text answers and quizzes will be limited.',
        )
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  const remove = async (id: string) => {
    try {
      await api.deleteDocument(id)
      setDocuments((prev) => {
        const next = prev.filter((document) => document.id !== id)
        if (id === activeId) {
          const fallback = next[0]?.id ?? null
          if (fallback) openDocument(fallback)
          else setActiveId(null)
        }
        return next
      })
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const addHighlight = useCallback((targetPage: number, text: string, rects: NormalizedRect[]) => {
    setHighlights((prev) => {
      if (prev.some((h) => h.page === targetPage && h.text === text)) return prev
      return [...prev, { id: newId(), page: targetPage, text, rects }]
    })
  }, [])

  const addScreenshot = useCallback((targetPage: number, dataUrl: string) => {
    setScreenshots((prev) => [...prev, { id: newId(), page: targetPage, dataUrl }])
  }, [])

  const clearTray = useCallback(() => {
    setHighlights([])
    setScreenshots([])
  }, [])

  const jumpToPage = useCallback((target: number) => setPage(target), [])

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="brand-mark">PT</span>
          PDF Tutor
        </div>

        <div className="header-doc">
          {active ? (
            <>
              <strong title={active.filename}>{active.filename}</strong>
              <span>
                {active.page_count} pages · grounded in this document only
              </span>
            </>
          ) : (
            <span>No document open</span>
          )}
        </div>

        <div className="tabs">
          <button
            className={`tab ${tab === 'tutor' ? 'active' : ''}`}
            onClick={() => setTab('tutor')}
          >
            Tutor
          </button>
          <button className={`tab ${tab === 'quiz' ? 'active' : ''}`} onClick={() => setTab('quiz')}>
            Quiz
          </button>
        </div>
      </header>

      <div className="main">
        <Sidebar
          documents={documents}
          activeId={activeId}
          uploading={uploading}
          onUpload={(file) => void upload(file)}
          onSelect={openDocument}
          onDelete={(id) => void remove(id)}
        />

        {active ? (
          <PdfViewer
            key={active.id}
            fileUrl={api.documentFileUrl(active.id)}
            pageCount={active.page_count}
            page={page}
            onPageChange={setPage}
            highlights={highlights}
            onAddHighlight={addHighlight}
            onAddScreenshot={addScreenshot}
          />
        ) : (
          <section className="viewer">
            <div className="empty">
              <Icon name="upload" size={24} />
              <h3>Upload a PDF to begin</h3>
              <p>
                Highlight passages or capture a region of any page, then ask the tutor. Answers are
                drawn strictly from the document you upload.
              </p>
            </div>
          </section>
        )}

        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>{tab === 'tutor' ? 'AI Tutor' : 'Quiz'}</h2>
              <p>
                {tab === 'tutor'
                  ? 'Answers cite the page they came from'
                  : 'Four options, one correct, grounded in the PDF'}
              </p>
            </div>
          </div>

          {keyMissing && (
            <div className="banner banner-warn">
              <strong>OPENAI_API_KEY is not set.</strong> Add it to
              <code> codebase/backend/.env</code> and restart the backend — the tutor and quiz need
              it.
            </div>
          )}

          {error && (
            <div className="banner banner-warn">
              {error}
              <button
                className="btn-icon"
                style={{ float: 'right', marginTop: -2 }}
                onClick={() => setError(null)}
              >
                ×
              </button>
            </div>
          )}

          {active ? (
            tab === 'tutor' ? (
              <ChatPanel
                key={active.id}
                documentId={active.id}
                page={page}
                highlights={highlights}
                screenshots={screenshots}
                onRemoveHighlight={(id) =>
                  setHighlights((prev) => prev.filter((h) => h.id !== id))
                }
                onRemoveScreenshot={(id) =>
                  setScreenshots((prev) => prev.filter((s) => s.id !== id))
                }
                onClearTray={clearTray}
                onJumpToPage={jumpToPage}
              />
            ) : (
              <QuizPanel
                key={active.id}
                documentId={active.id}
                pageCount={active.page_count}
                onJumpToPage={jumpToPage}
              />
            )
          ) : (
            <div className="empty">
              <p>Open a document to start.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
