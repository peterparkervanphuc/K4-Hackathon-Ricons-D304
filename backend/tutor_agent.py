"""Route-specific tutor orchestration with deterministic page addressing."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from ai_provider import AIProvider, get_provider
from llm import generate_answer
from page_reference import parse_page_reference
from retriever import HybridRetriever, confidence_for


def detect_language(text: str) -> str:
    lower = text.lower()
    return "vi" if re.search(r"[ăâđêôơưáàảãạấầẩẫậếềểễệốồổỗộớờởỡợứừửữựíìỉĩịýỳỷỹỵ]", lower) or any(term in f" {lower} " for term in (" là ", " gì ", " trang ", " tóm tắt ", " bài này ")) else "en"


def _summary_route(question: str) -> str | None:
    q = question.lower()
    if re.search(r"tóm tắt toàn bộ|tóm tắt bài|bài này (nói|dạy) về gì|giải thích toàn bộ bài|summari[sz]e (the )?(whole|lecture|document)", q): return "document_summary"
    if re.search(r"ôn tập bài|đề cương ôn tập|study guide|review (this )?lesson", q): return "document_summary"
    if re.search(r"tóm tắt phần này|current section|section summary", q): return "section_summary"
    return None


def _question_route(question: str) -> str:
    q = question.lower()
    if re.search(r"so sánh|compare|khác nhau| versus | vs\.?", q): return "comparison_question"
    if re.search(r"tính|calculate|compute|giải bài|∫|đạo hàm", q): return "calculation_question"
    if re.search(r"liên hệ|xuyên suốt|giữa các phần|cross.?section", q): return "cross_section_question"
    return "concept_question"


QUERY_PROMPT = """Understand a lecture query for multilingual retrieval. Return JSON {translated_query,bilingual_terms,route}. route must be concept_question, cross_section_question, comparison_question, calculation_question, or outside_scope. Translate only the query for retrieval; never modify source content."""


def _page_context(page: dict[str, Any]) -> dict[str, Any]:
    return {key: page.get(key) for key in ("page", "title", "source_text", "main_message", "vision_description", "concepts", "definitions", "formulas", "examples", "tables", "charts", "notes", "previous_page_relation", "next_page_relation", "source_language", "bilingual_aliases", "uncertain_content")}


def _section_for_page(lesson: dict[str, Any], page: int) -> dict[str, Any] | None:
    return next((section for section in lesson.get("sections", []) if page in section.get("pages", [])), None)


def controlled_research(query: str) -> tuple[list[dict[str, Any]], str | None]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key: return [], None
    import httpx
    domains = [value.strip() for value in os.getenv("RESEARCH_DOMAINS", "ocw.mit.edu,edu,docs.python.org").split(",") if value.strip()]
    try:
        response = httpx.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "search_depth": "advanced", "max_results": 4, "include_domains": domains}, timeout=20)
        response.raise_for_status()
        return [{"title": item.get("title"), "url": item.get("url"), "snippet": item.get("content", "")[:900], "source_type": "external"} for item in response.json().get("results", [])], query
    except Exception: return [], query


def _citations(generated: dict[str, Any], allowed_pages: dict[int, dict[str, Any]], document_id: str) -> list[dict[str, Any]]:
    citations = []
    for item in generated.get("citations", []):
        try: page_number = int(item.get("page"))
        except (TypeError, ValueError): continue
        page = allowed_pages.get(page_number)
        if not page: continue
        support = str(item.get("supporting_text") or page.get("main_message") or page.get("source_text", "")[:420])
        source = f"{page.get('source_text','')} {page.get('vision_description','')} {page.get('main_message','')}"
        if support and support.lower() not in source.lower(): support = str(page.get("main_message") or page.get("source_text", "")[:420])
        citations.append({"document_id": document_id, "page": page_number, "label": f"Trang {page_number}", "chunkId": f"{document_id}-P{page_number}", "supporting_text": support[:500], "excerpt": support[:260], "claim": item.get("claim", "")})
    return list({item["page"]: item for item in citations}.values())


def _grounding_confidence(route: str, lesson: dict[str, Any], allowed_pages: dict[int, dict[str, Any]], citations: list[dict[str, Any]]) -> tuple[str, int]:
    """Score direct routes from evidence coverage and validated support, not similarity."""
    if not allowed_pages or not citations:
        return "low", 20
    cited_pages = {int(item["page"]) for item in citations}
    support_ratio = sum(bool(item.get("claim") and item.get("supporting_text")) for item in citations) / len(citations)
    if route == "document_summary":
        sections = [section for section in lesson.get("sections", []) if section.get("pages")]
        coverage = (
            sum(bool(cited_pages.intersection(map(int, section["pages"]))) for section in sections) / len(sections)
            if sections else len(cited_pages.intersection(allowed_pages)) / len(allowed_pages)
        )
    else:
        coverage = len(cited_pages.intersection(allowed_pages)) / len(allowed_pages)
    composite = 0.72 * coverage + 0.28 * support_ratio
    level = "high" if composite >= 0.8 else "medium" if composite >= 0.5 else "low"
    return level, round(composite * 100)


def answer_question(question: str, document_id: str, current_page: int, chunks: list[dict[str, Any]], history: list[dict[str, str]] | None = None, lesson_map: dict[str, Any] | None = None, page_summaries: list[dict[str, Any]] | None = None, conversation_state: dict[str, Any] | None = None) -> dict[str, Any]:
    history = history or []; pages = page_summaries or []; lesson = lesson_map or {}; provider = get_provider(); provider.require_generation()
    language = detect_language(question); page_by_number = {int(page["page"]): page for page in pages}; total_pages = len(pages)
    reference = parse_page_reference(question, current_page, total_pages)
    route = reference.route or _summary_route(question) or _question_route(question)
    external: list[dict[str, Any]] = []; web_query = None; retrieval_results: list[dict[str, Any]] = []
    if reference.error:
        return {"text": reference.error, "answer": reference.error, "language": language, "question_type": route, "confidence": 0, "confidenceLevel": "low", "confidenceLabel": "Trang không hợp lệ", "citations": [], "external_sources": [], "decision_to_search_web": False, "clarificationOptions": None, "conversation_state": {"current_document_id": document_id, "current_page": current_page}, "debug": None}
    if reference.pages:
        selected = [page_by_number[number] for number in reference.pages]
        context = {"addressed_pages": [_page_context(page) for page in selected], "instruction": "Use only addressed_pages. Page numbers are explicit and override current_page."}
        allowed = {page["page"]: page for page in selected}
    elif route == "document_summary":
        context = {"lesson_map": lesson, "all_pages": [_page_context(page) for page in pages], "coverage_requirement": {"first": 1, "middle": max(1, total_pages // 2), "last": total_pages}}
        allowed = page_by_number
    elif route == "section_summary":
        section = _section_for_page(lesson, current_page)
        selected = [page_by_number[number] for number in (section or {}).get("pages", [])]
        context = {"section": section, "pages": [_page_context(page) for page in selected]}; allowed = {page["page"]: page for page in selected}
    else:
        understanding = provider.json_completion(QUERY_PROMPT, {"question": question, "source_language": lesson.get("source_language"), "lesson_topic": lesson.get("main_topic")}, 700)
        route = understanding.get("route") if understanding.get("route") in {"concept_question", "cross_section_question", "comparison_question", "calculation_question", "outside_scope"} else route
        retrieval_query = " ".join(filter(None, [question, understanding.get("translated_query"), " ".join(map(str, understanding.get("bilingual_terms", []))) ]))
        current_section = (_section_for_page(lesson, current_page) or {}).get("title")
        retrieval_results = HybridRetriever(chunks, provider).search(retrieval_query, current_page, top_k=8 if route == "cross_section_question" else 5, section=current_section)
        selected_numbers = []
        for item in retrieval_results:
            number = int(item["chunk"]["page"]); selected_numbers.extend([number - 1, number, number + 1])
        selected_numbers = [number for number in dict.fromkeys(selected_numbers) if number in page_by_number]
        selected = [page_by_number[number] for number in selected_numbers]
        if not retrieval_results: route = "outside_scope"
        context = {"lesson_scope": {"title": lesson.get("title"), "main_topic": lesson.get("main_topic"), "sections": [{"title": section.get("title"), "pages": section.get("pages")} for section in lesson.get("sections", [])]}, "retrieved_pages_with_neighbors": [_page_context(page) for page in selected]}
        allowed = {page["page"]: page for page in selected}
        research_requested = bool(re.search(r"thực tế|mới nhất|cập nhật|nguồn ngoài|real.?world|latest|current", question.lower()))
        if route != "outside_scope" and research_requested: external, web_query = controlled_research(retrieval_query)
    generated = generate_answer(question, language, route, context, history, external, provider)
    citations = _citations(generated, allowed, document_id)
    confidence_level, confidence_score = confidence_for(retrieval_results) if retrieval_results else _grounding_confidence(route, lesson, allowed, citations)
    debug = {"route": route, "page_reference": reference.to_dict(), "current_document_id": document_id, "current_page": current_page, "retrieved_pages": [item["chunk"]["page"] for item in retrieval_results], "retrieval_scores": [{"page": item["chunk"]["page"], "bm25": round(item["bm25"], 4), "embedding": round(item["semantic"], 4), "rerank": round(item.get("rerank_score", 0), 4)} for item in retrieval_results], "decision_to_search_web": bool(external), "web_query": web_query, "citation_pages": [item["page"] for item in citations], "provider": provider.status()}
    if os.getenv("TUTOR_DEBUG", "").lower() in {"1", "true", "yes"}: print(json.dumps(debug, ensure_ascii=False))
    state = {"current_document_id": document_id, "current_page": current_page, "current_section": (_section_for_page(lesson, current_page) or {}).get("title"), "last_concept": lesson.get("main_topic"), "last_answer_type": route, "referenced_formula": next((formula for page in allowed.values() for formula in page.get("formulas", [])), None)}
    return {"text": generated["answer"], "answer": generated["answer"], "language": language, "question_type": route, "confidence": confidence_score, "confidenceLevel": confidence_level, "confidenceLabel": {"high": "Độ tin cậy cao", "medium": "Độ tin cậy trung bình", "low": "Độ tin cậy thấp"}[confidence_level] if language == "vi" else f"{confidence_level.title()} confidence", "citations": citations, "external_sources": external, "decision_to_search_web": bool(external), "clarificationOptions": generated.get("clarification_options") or None, "conversation_state": state, "debug": debug if os.getenv("TUTOR_DEBUG", "").lower() in {"1", "true", "yes"} else None}
