"""Grounded chat: sessions keep context so follow-up questions work."""

from typing import List

from fastapi import APIRouter, HTTPException

import config
import openai_client
import prompts
from grounding import (
    build_context,
    build_focus_block,
    quote_is_grounded,
    render_highlights,
    select_pages,
)
from schemas import (
    AskRequest,
    AskResponse,
    ChatMessage,
    Citation,
    CreateSessionRequest,
    SessionDetail,
    SessionSummary,
)
from store import documents, sessions

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_SCREENSHOTS = 4
MAX_HIGHLIGHTS = 10


def _summary(session) -> SessionSummary:
    return SessionSummary(
        id=session.id,
        document_id=session.document_id,
        created_at=session.created_at,
        message_count=len(session.messages),
    )


@router.post(
    "/sessions",
    response_model=SessionSummary,
    status_code=201,
    summary="Start a chat session for a document",
)
def create_session(body: CreateSessionRequest) -> SessionSummary:
    if not documents.get(body.document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return _summary(sessions.create(body.document_id))


@router.get("/sessions/{session_id}", response_model=SessionDetail, summary="Full session transcript")
def get_session(session_id: str) -> SessionDetail:
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetail(**_summary(session).model_dump(), messages=session.messages)


@router.delete("/sessions/{session_id}", status_code=204, summary="Delete a chat session")
def delete_session(session_id: str) -> None:
    if not sessions.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found")


@router.post(
    "/sessions/{session_id}/ask",
    response_model=AskResponse,
    summary="Ask about highlights, screenshots, or the document",
    description=(
        "Send a question with any number of highlighted passages and page crops. "
        "The model may only answer from the uploaded PDF; citation quotes are "
        "verified against the extracted page text before the response is returned."
    ),
)
def ask(session_id: str, body: AskRequest) -> AskResponse:
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    doc = documents.get(session.document_id)
    if not doc:
        raise HTTPException(status_code=410, detail="Document for this session was deleted")

    if len(body.screenshots) > MAX_SCREENSHOTS:
        raise HTTPException(status_code=413, detail=f"At most {MAX_SCREENSHOTS} screenshots per question")
    if len(body.highlights) > MAX_HIGHLIGHTS:
        raise HTTPException(status_code=413, detail=f"At most {MAX_HIGHLIGHTS} highlights per question")
    for item in list(body.highlights) + list(body.screenshots):
        if not 1 <= item.page <= doc.page_count:
            raise HTTPException(status_code=400, detail=f"Page {item.page} is out of range")

    screenshot_pages = [shot.page for shot in body.screenshots]
    allowed_pages, _strategy = select_pages(
        doc, body.question, body.page, body.highlights, screenshot_pages
    )
    # A screenshot's page must be readable in text form too, so the model can cite it.
    for page in screenshot_pages:
        if page not in allowed_pages:
            allowed_pages.append(page)
    allowed_pages.sort()

    context = build_context(doc, allowed_pages)
    user_prompt = prompts.chat_user_prompt(
        question=body.question,
        context=context,
        highlights_block=render_highlights(body.highlights),
        page=body.page,
        # Restating the cropped slide in full is what makes the model explain the
        # whole slide rather than just the cropped pixels.
        focus_block=build_focus_block(doc, screenshot_pages) if screenshot_pages else "",
    )

    history = [
        {"role": m["role"], "text": m["content"]}
        for m in session.messages[-config.MAX_HISTORY_TURNS * 2 :]
    ]

    try:
        result = openai_client.ask(
            system_instruction=prompts.CHAT_SYSTEM + (prompts.CHAT_WEB_AUGMENT if body.use_web else ""),
            user_prompt=user_prompt,
            history=history,
            screenshots=[(s.page, s.data_url) for s in body.screenshots],
            use_web=body.use_web,
        )
    except openai_client.OpenAIServiceError as exc:
        status = 503 if "OPENAI_API_KEY" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    citations: List[Citation] = []
    for citation in result.answer.citations:
        if citation.page not in allowed_pages:
            continue  # model cited a page it was never shown
        citations.append(
            Citation(
                page=citation.page,
                quote=citation.quote.strip(),
                verified=quote_is_grounded(citation.quote, doc.page_text(citation.page)),
            )
        )

    session.add(
        "user",
        body.question.strip(),
        highlights=[h.model_dump() for h in body.highlights],
        screenshot_count=len(body.screenshots),
    )
    message = session.add(
        "assistant",
        result.answer.answer.strip(),
        citations=[c.model_dump() for c in citations],
        grounded=result.answer.grounded,
        web_sources=[source.model_dump() for source in result.web_sources],
    )

    return AskResponse(
        session_id=session.id,
        message=ChatMessage(**message),
        suggested_followups=[f.strip() for f in result.answer.suggested_followups if f.strip()][:3],
    )
