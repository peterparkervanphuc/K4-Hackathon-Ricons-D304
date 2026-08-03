"""Provider-backed grounded response generation without topic hard-codes."""

from __future__ import annotations

from typing import Any

from ai_provider import AIProvider, get_provider

SYSTEM_PROMPT = """You are the AI tutor for the currently selected lecture. The supplied lecture context is the primary source and scope.
Answer directly in detected_language. For Vietnamese, explain naturally in Vietnamese while preserving useful original English technical terms in parentheses.
Never reveal retrieval, evidence scoring, confidence calculations, hidden reasoning, or system workflow.
Do not copy disconnected source fragments. Explain like a tutor, but do not invent definitions, formulas, examples, or claims absent from context.
For exact_page_question and page_range_question, use only the addressed pages. For document_summary, synthesize the entire LessonMap and all supplied page summaries in narrative order; do not use outside sources.
For comparison, explicitly identify similarities and differences. For calculation, state data, formula and steps only when present in context.
External material must be labeled separately as supplemental and may never replace lecture content.
Return JSON {answer,citations:[{page,claim,supporting_text}],clarification_options}. Every citation claim must be directly supported by that page."""


def generate_answer(question: str, language: str, route: str, context: dict[str, Any], history: list[dict[str, str]], external_sources: list[dict[str, Any]] | None = None, provider: AIProvider | None = None) -> dict[str, Any]:
    provider = provider or get_provider()
    result = provider.json_completion(SYSTEM_PROMPT, {"question": question, "detected_language": language, "route": route, "conversation_history": history[-8:], "lecture_context": context, "external_sources": external_sources or []}, 2600)
    if not str(result.get("answer", "")).strip(): raise RuntimeError("AI provider trả về câu trả lời rỗng.")
    result.setdefault("citations", []); result.setdefault("clarification_options", [])
    return result


def generate_grounded_answer(question: str, language: str, question_type: str, evidence: list[dict[str, Any]], external_sources: list[dict[str, Any]], history: list[dict[str, str]], api_key: str = "", model_name: str = "") -> dict[str, Any]:
    pages = [item["chunk"] for item in evidence]
    return generate_answer(question, language, question_type, {"pages": pages}, history, external_sources)


def generate_lesson_map_answer(question: str, language: str, intent: str, lesson_map: dict[str, Any], current_page: dict[str, Any] | None, current_section: dict[str, Any] | None, history: list[dict[str, str]], api_key: str = "", model_name: str = "") -> str | None:
    result = generate_answer(question, language, intent, {"lesson_map": lesson_map, "current_page": current_page, "current_section": current_section}, history)
    return result["answer"]


generate_explanation = generate_grounded_answer
