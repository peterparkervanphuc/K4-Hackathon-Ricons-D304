import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { api } from '../api'
import type { ChatMessage, Highlight, Screenshot } from '../types'
import { Icon } from './Icon'
import { Markdown } from './Markdown'

interface AskPayload {
  question: string
  page: number
  highlights: { page: number; text: string }[]
  screenshots: { page: number; data_url: string }[]
  use_web: boolean
}

interface Props {
  documentId: string
  page: number
  highlights: Highlight[]
  screenshots: Screenshot[]
  onRemoveHighlight: (id: string) => void
  onRemoveScreenshot: (id: string) => void
  onClearTray: () => void
  onJumpToPage: (page: number) => void
}

export function ChatPanel({
  documentId,
  page,
  highlights,
  screenshots,
  onRemoveHighlight,
  onRemoveScreenshot,
  onClearTray,
  onJumpToPage,
}: Props) {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [followups, setFollowups] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  const [useWeb, setUseWeb] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The payload of the last failed request, kept so it can be resent without
  // the user retyping or re-selecting anything.
  const [failed, setFailed] = useState<AskPayload | null>(null)

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // One session per document; switching documents starts a fresh conversation.
  useEffect(() => {
    let disposed = false
    setMessages([])
    setFollowups([])
    setError(null)
    setSessionId(null)

    api
      .createSession(documentId)
      .then((session) => {
        if (!disposed) setSessionId(session.id)
      })
      .catch((err: Error) => {
        if (!disposed) setError(err.message)
      })
    return () => {
      disposed = true
    }
  }, [documentId])

  useLayoutEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, pending])

  const autoGrow = (element: HTMLTextAreaElement) => {
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 132)}px`
  }

  /** Sends a prepared payload. The user's turn is already on screen by now. */
  const deliver = async (payload: AskPayload) => {
    if (!sessionId) return
    setError(null)
    setFollowups([])
    setPending(true)
    try {
      const response = await api.ask(sessionId, payload)
      setMessages((prev) => [...prev, response.message])
      setFollowups(response.suggested_followups)
      setFailed(null)
    } catch (err) {
      setError((err as Error).message)
      setFailed(payload)
    } finally {
      setPending(false)
    }
  }

  const send = async (question: string) => {
    const trimmed = question.trim()
    if (!trimmed || !sessionId || pending) return

    const payload: AskPayload = {
      question: trimmed,
      page,
      highlights: highlights.map((h) => ({ page: h.page, text: h.text })),
      screenshots: screenshots.map((s) => ({ page: s.page, data_url: s.dataUrl })),
      use_web: useWeb,
    }

    setDraft('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    // Show the user's turn immediately; the server returns the stored copy.
    setMessages((prev) => [
      ...prev,
      {
        id: `local-${Date.now()}`,
        role: 'user',
        content: trimmed,
        created_at: new Date().toISOString(),
        citations: [],
        grounded: true,
        highlights: payload.highlights,
        screenshot_count: payload.screenshots.length,
        web_sources: [],
      },
    ])
    onClearTray()

    await deliver(payload)
  }

  const trayCount = highlights.length + screenshots.length
  const placeholder = trayCount
    ? 'Ask about the selected content…'
    : 'Ask anything about this document…'

  return (
    <>
      <div className="panel-body">
        {messages.length === 0 && !pending && (
          <div className="empty">
            <Icon name="sparkle" size={22} />
            <h3>Ask about this document</h3>
            <p>
              Select text on the page or use <strong>Capture area</strong> to attach a screenshot,
              then ask your question. Answers come only from this PDF.
            </p>
          </div>
        )}

        <div className="messages">
          {messages.map((message) =>
            message.role === 'user' ? (
              <div className="msg-user" key={message.id}>
                {(message.highlights.length > 0 || message.screenshot_count > 0) && (
                  <div className="msg-user-attachments">
                    {message.highlights.map((highlight, index) => (
                      <span key={index}>
                        p.{highlight.page} “{highlight.text.slice(0, 40)}
                        {highlight.text.length > 40 ? '…' : ''}”
                      </span>
                    ))}
                    {message.screenshot_count > 0 && (
                      <span>
                        {message.screenshot_count} screenshot
                        {message.screenshot_count > 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                )}
                {message.content}
              </div>
            ) : (
              <div
                className={`msg-assistant ${message.grounded ? '' : 'ungrounded'}`}
                key={message.id}
              >
                {!message.grounded && (
                  <div className="grounding-flag">
                    <Icon name="alert" size={12} />
                    Not covered by this document
                  </div>
                )}
                <Markdown text={message.content} />
                {message.citations.length > 0 && (
                  <div className="citations">
                    {message.citations.map((citation, index) => (
                      <button
                        key={index}
                        className={`citation ${citation.verified ? '' : 'unverified'}`}
                        onClick={() => onJumpToPage(citation.page)}
                        title={
                          citation.verified
                            ? `“${citation.quote}”`
                            : `Quote could not be matched on page ${citation.page}: “${citation.quote}”`
                        }
                      >
                        <span className="citation-page">p.{citation.page}</span>
                        <span className="citation-quote">{citation.quote}</span>
                      </button>
                    ))}
                  </div>
                )}
                {message.web_sources.length > 0 && (
                  <div className="web-sources">
                    <span>External sources</span>
                    {message.web_sources.map((source) => (
                      <a key={source.url} href={source.url} target="_blank" rel="noreferrer">
                        {source.title}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ),
          )}

          {pending && (
            <div className="thinking">
              <div className="spinner" />
              Reading the document…
            </div>
          )}

          {followups.length > 0 && !pending && (
            <div className="followups">
              {followups.map((followup, index) => (
                <button key={index} className="followup" onClick={() => send(followup)}>
                  {followup}
                </button>
              ))}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="banner banner-error">
            <div>{error}</div>
            {failed && (
              <button
                className="btn banner-retry"
                onClick={() => void deliver(failed)}
                disabled={pending}
              >
                <Icon name="refresh" size={13} />
                Thử lại
              </button>
            )}
          </div>
        )}
      </div>

      <div className="composer">
        {trayCount > 0 && (
          <div className="tray">
            {highlights.map((highlight) => (
              <span className="tray-chip" key={highlight.id}>
                <Icon name="quote" size={12} />
                <span className="tray-chip-text">
                  p.{highlight.page} · {highlight.text}
                </span>
                <button
                  className="tray-chip-remove"
                  onClick={() => onRemoveHighlight(highlight.id)}
                  title="Remove"
                >
                  ×
                </button>
              </span>
            ))}
            {screenshots.map((screenshot) => (
              <span className="tray-chip" key={screenshot.id}>
                <img src={screenshot.dataUrl} alt={`Capture from page ${screenshot.page}`} />
                <span className="tray-chip-text">p.{screenshot.page}</span>
                <button
                  className="tray-chip-remove"
                  onClick={() => onRemoveScreenshot(screenshot.id)}
                  title="Remove"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="composer-box">
          <textarea
            ref={textareaRef}
            rows={1}
            value={draft}
            placeholder={placeholder}
            disabled={!sessionId}
            onChange={(event) => {
              setDraft(event.target.value)
              autoGrow(event.target)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void send(draft)
              }
            }}
          />
          <button
            className="composer-send"
            onClick={() => void send(draft)}
            disabled={!draft.trim() || pending || !sessionId}
            title="Send"
          >
            <Icon name="send" size={14} />
          </button>
        </div>

        <label className="web-toggle">
          <input type="checkbox" checked={useWeb} onChange={(event) => setUseWeb(event.target.checked)} />
          Use cited web sources for deeper explanations and examples
        </label>

        <p className="composer-hint">
          {trayCount > 0
            ? `${highlights.length} highlight${highlights.length === 1 ? '' : 's'} · ${screenshots.length} capture${screenshots.length === 1 ? '' : 's'} attached`
            : 'Enter to send · Shift+Enter for a new line'}
        </p>
      </div>
    </>
  )
}
