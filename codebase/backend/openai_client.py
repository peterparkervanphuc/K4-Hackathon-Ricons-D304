"""OpenAI Responses API client for structured, grounded tutor answers."""

import logging
import random
import time
from typing import List, Optional, Sequence

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, Field

import config

log = logging.getLogger(__name__)


class OpenAIServiceError(RuntimeError):
    """Raised for unavailable credentials or failed model generations."""


class _Citation(BaseModel):
    page: int = Field(description="Page number the quote comes from")
    quote: str = Field(description="Short verbatim quote copied from that page")


class _ChatAnswer(BaseModel):
    answer: str
    grounded: bool = Field(description="False when the document does not contain the answer")
    citations: List[_Citation] = Field(default_factory=list)
    suggested_followups: List[str] = Field(default_factory=list)


class WebSource(BaseModel):
    title: str
    url: str


class ChatResult(BaseModel):
    answer: _ChatAnswer
    web_sources: List[WebSource] = Field(default_factory=list)


class _QuizItem(BaseModel):
    question: str
    options: List[str] = Field(description="Exactly four answer options")
    correct_index: int = Field(description="0-based index of the single correct option")
    explanation: str
    source_page: int
    evidence_quote: str


class _QuizSet(BaseModel):
    questions: List[_QuizItem]


_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if not config.OPENAI_API_KEY:
        raise OpenAIServiceError(
            "OPENAI_API_KEY is not set. Add it to codebase/.env and restart the server."
        )
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def _generate(*, instructions: str, input_messages, schema, tools=None):
    """Request Pydantic-validated structured output, retrying transient failures."""
    client = get_client()
    attempts_left = max(1, config.OPENAI_MAX_ATTEMPTS)
    delay = config.OPENAI_RETRY_BASE_DELAY
    last_error: Exception | None = None

    while attempts_left:
        try:
            response = client.responses.parse(
                model=config.OPENAI_MODEL,
                instructions=instructions,
                input=input_messages,
                text_format=schema,
                tools=tools or [],
            )
            if response.output_parsed is None:
                raise OpenAIServiceError("OpenAI returned no structured output.")
            return response.output_parsed, response
        except OpenAIServiceError:
            raise
        except Exception as exc:
            last_error = exc
            if not _is_retryable(exc):
                break

        attempts_left -= 1
        if not attempts_left:
            break
        pause = delay + random.uniform(0, delay * 0.25)
        log.warning("OpenAI call failed (%s). Retrying in %.1fs.", last_error, pause)
        time.sleep(pause)
        delay *= 2

    raise OpenAIServiceError(f"OpenAI request failed: {last_error}") from last_error


def _web_sources(response) -> List[WebSource]:
    sources: List[WebSource] = []
    seen: set[str] = set()
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                if getattr(annotation, "type", "") != "url_citation":
                    continue
                url = (getattr(annotation, "url", None) or "").strip()
                if url and url not in seen:
                    seen.add(url)
                    sources.append(WebSource(title=(getattr(annotation, "title", None) or url).strip(), url=url))
    return sources


def _serialize_history(history: Sequence[dict]) -> str:
    """Convert prior turns into a plain-text transcript for Responses API compatibility."""
    lines: List[str] = []
    for turn in history:
        role = str(turn.get("role", "user") or "user").strip().lower()
        text = str(turn.get("text", "") or "").strip()
        if not text:
            continue
        if role == "assistant":
            lines.append(f"Assistant: {text}")
        else:
            lines.append(f"User: {text}")
    return "\n".join(lines)


def ask(
    system_instruction: str,
    user_prompt: str,
    history: Sequence[dict],
    screenshots: Sequence[tuple[int, str]] = (),
    use_web: bool = False,
) -> ChatResult:
    transcript = _serialize_history(history)
    if transcript:
        input_text = f"{transcript}\n\nUser: {user_prompt}"
    else:
        input_text = user_prompt

    if screenshots:
        extra_parts = []
        for index, (page, data_url) in enumerate(screenshots, start=1):
            extra_parts.append(
                (
                    f"Crop {index} of {len(screenshots)} is from page {page}. "
                    f"The complete text of page {page} is included in the provided context."
                )
            )
        input_text = "\n\n".join([input_text, *extra_parts])

    answer, response = _generate(
        instructions=system_instruction,
        input_messages=input_text,
        schema=_ChatAnswer,
        tools=[{"type": "web_search"}] if use_web else None,
    )
    return ChatResult(answer=answer, web_sources=_web_sources(response))


def quiz(system_instruction: str, user_prompt: str) -> _QuizSet:
    result, _ = _generate(
        instructions=system_instruction,
        input_messages=user_prompt,
        schema=_QuizSet,
    )
    return result
