"""Quiz generation: 4-option multiple choice, exactly one correct answer."""

from typing import List

from fastapi import APIRouter, HTTPException

import config
import openai_client
import prompts
from grounding import build_context, quote_is_grounded
from schemas import QuizQuestion, QuizRequest, QuizResponse
from store import documents

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


def _pages_for_quiz(doc, page_from: int | None, page_to: int | None) -> List[int]:
    start = max(1, page_from or 1)
    end = min(doc.page_count, page_to or doc.page_count)
    if start > end:
        raise HTTPException(status_code=400, detail="page_from must be <= page_to")

    candidates = [p for p in range(start, end + 1) if doc.page_text(p).strip()]
    if not candidates:
        raise HTTPException(
            status_code=422,
            detail="No extractable text in that page range — a quiz cannot be grounded in it.",
        )

    # Keep the prompt inside the context budget by thinning out evenly, so the
    # quiz still spans the whole requested range instead of just the front.
    total = sum(len(doc.page_text(p)) for p in candidates)
    if total <= config.FULL_DOC_CHAR_BUDGET:
        return candidates

    keep = max(1, int(len(candidates) * config.FULL_DOC_CHAR_BUDGET / total))
    step = len(candidates) / keep
    return [candidates[int(i * step)] for i in range(keep)]


@router.post(
    "",
    response_model=QuizResponse,
    summary="Generate a multiple-choice quiz from the document",
    description=(
        "Every question carries the page and a verbatim evidence quote. Questions whose "
        "evidence cannot be found on the cited page are discarded, not returned."
    ),
)
def generate_quiz(body: QuizRequest) -> QuizResponse:
    doc = documents.get(body.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = _pages_for_quiz(doc, body.page_from, body.page_to)
    context = build_context(doc, pages)
    # Ask for a couple extra so grounding rejections still leave a full set.
    requested = min(body.num_questions + 2, 15)

    try:
        result = openai_client.quiz(
            system_instruction=prompts.QUIZ_SYSTEM,
            user_prompt=prompts.quiz_user_prompt(
                context=context,
                num_questions=requested,
                difficulty=body.difficulty,
                language=body.language,
            ),
        )
    except openai_client.OpenAIServiceError as exc:
        status = 503 if "OPENAI_API_KEY" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    questions: List[QuizQuestion] = []
    dropped = 0
    allowed = set(pages)

    for item in result.questions:
        options = [o.strip() for o in item.options if o and o.strip()]
        if len(options) != 4 or len(set(options)) != 4:
            dropped += 1
            continue
        if not 0 <= item.correct_index < 4:
            dropped += 1
            continue
        if item.source_page not in allowed:
            dropped += 1
            continue

        page_text = doc.page_text(item.source_page)
        verified = quote_is_grounded(item.evidence_quote, page_text)
        if not verified and page_text.strip():
            dropped += 1  # cited a page that has text, but the quote is not on it
            continue

        questions.append(
            QuizQuestion(
                question=item.question.strip(),
                options=options,
                correct_index=item.correct_index,
                explanation=item.explanation.strip(),
                source_page=item.source_page,
                evidence_quote=item.evidence_quote.strip(),
                verified=verified,
            )
        )
        if len(questions) >= body.num_questions:
            break

    if not questions:
        raise HTTPException(
            status_code=422,
            detail="Could not generate any question that verifiably comes from the document. "
            "Try a different page range.",
        )

    return QuizResponse(document_id=doc.id, questions=questions, dropped=dropped)
