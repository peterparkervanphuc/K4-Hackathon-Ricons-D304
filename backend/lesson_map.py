"""LLM-based hierarchical lesson synthesis and persistent processing cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ai_provider import AIProvider, get_provider
from ingestion import PROCESSING_VERSION, page_to_chunk


RELATION_PROMPT = """Analyze ordered lecture PageRecords. Return JSON {relations:[{page,previous_page_relation,next_page_relation}]}. Each non-empty relation must be a complete, content-specific sentence naming the actual concept/formula/example on both pages and its pedagogical function. Never return category labels such as 'extends a definition', 'gives an example', 'changes topic', or generic 'continues from A to B'. Use empty string when the content-specific relationship is unsupported."""
SECTION_PROMPT = """Detect semantic lecture sections from every ordered page. Do not split by a fixed page count. Return JSON {title,source_language,main_topic,learning_objectives,narrative_flow,sections:[{title,pages,purpose,main_claims,relationships_to_other_sections}]}. Every page number must occur exactly once and in source order. Infer boundaries from titles, content and page relationships."""
SECTION_SYNTHESIS_PROMPT = """Synthesize one lecture section only from supplied PageRecords. Return JSON {title,pages,purpose,summary,main_claims,concepts,definitions,formulas,examples,relationships_to_other_sections}. Explain the section's question, development, examples/formulas and conclusion. Do not add outside knowledge."""
LESSON_PROMPT = """Synthesize the complete lecture from all page summaries and every section synthesis. Return JSON {title,source_language,main_topic,learning_objectives,narrative_flow,full_lesson_summary,key_takeaways}. The summary must explain how the lesson begins, develops its arguments, connects concepts, uses examples/formulas, and concludes. Cover beginning, middle and end. Do not merely list headings and do not add outside knowledge."""


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def _page_context(page: dict[str, Any], max_text: int = 1800) -> dict[str, Any]:
    return {key: page.get(key) for key in ("page", "title", "main_message", "concepts", "definitions", "formulas", "examples", "charts", "vision_description", "previous_page_relation", "next_page_relation", "source_language")} | {"source_text": page.get("source_text", "")[:max_text]}


def _list(value: Any) -> list[Any]:
    if value is None: return []
    if isinstance(value, list): return value
    if isinstance(value, dict): return [f"{key}: {item}" for key, item in value.items()]
    return [value]


def _specific_relation(value: Any) -> str:
    text = str(value or "").strip()
    generic = {"extends a definition", "gives an example", "applies a formula", "introduces a special case", "changes topic", "concludes", "extends"}
    return "" if text.lower() in generic or len(text.split()) < 7 else text


def build_lesson_map(document_id: str, original_name: str, pages: list[dict[str, Any]], provider: AIProvider | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    provider = provider or get_provider(); provider.require_generation()
    outlines = [_page_context(page, 900) for page in pages]
    relations = provider.json_completion(RELATION_PROMPT, {"pages": outlines}, 2200).get("relations", [])
    relation_by_page = {int(item["page"]): item for item in relations if str(item.get("page", "")).isdigit()}
    for page in pages:
        relation = relation_by_page.get(page["page"], {})
        page["previous_page_relation"] = _specific_relation(relation.get("previous_page_relation"))
        page["next_page_relation"] = _specific_relation(relation.get("next_page_relation"))
    structure = provider.json_completion(SECTION_PROMPT, {"document_title": Path(original_name).stem, "pages": [_page_context(page, 1100) for page in pages]}, 3000)
    sections = structure.get("sections", [])
    expected = [page["page"] for page in pages]
    actual = [int(value) for section in sections for value in section.get("pages", [])]
    if actual != expected:
        raise RuntimeError(f"Section detection không bao phủ đúng tài liệu: expected={expected}, actual={actual}")
    page_by_number = {page["page"]: page for page in pages}
    synthesized = []
    for section in sections:
        section_pages = [_page_context(page_by_number[int(number)], 1600) for number in section["pages"]]
        result = provider.json_completion(SECTION_SYNTHESIS_PROMPT, {"section_hint": section, "pages": section_pages}, 2400)
        result["pages"] = [int(value) for value in section["pages"]]
        result["title"] = result.get("title") or section.get("title")
        for field in ("main_claims", "concepts", "definitions", "formulas", "examples", "relationships_to_other_sections"): result[field] = _list(result.get(field))
        synthesized.append(result)
        for number in result["pages"]: page_by_number[number]["section"] = result["title"]
    whole = provider.json_completion(LESSON_PROMPT, {"document_title": Path(original_name).stem, "pages": [_page_context(page, 800) for page in pages], "sections": synthesized}, 3500)
    lesson = {
        "document_id": document_id, "title": whole.get("title") or structure.get("title") or Path(original_name).stem,
        "source_language": whole.get("source_language") or structure.get("source_language") or (pages[0].get("source_language") if pages else "unknown"),
        "main_topic": whole.get("main_topic") or structure.get("main_topic"),
        "learning_objectives": _list(whole.get("learning_objectives") or structure.get("learning_objectives")),
        "narrative_flow": _list(whole.get("narrative_flow") or structure.get("narrative_flow")),
        "sections": synthesized, "full_lesson_summary": whole.get("full_lesson_summary", ""),
        "key_takeaways": _list(whole.get("key_takeaways")),
        "page_index": {str(page["page"]): {"title": page.get("title"), "main_message": page.get("main_message"), "section": page.get("section")} for page in pages},
        "coverage": {"total_pages": len(pages), "summarized_pages": len(pages), "section_count": len(synthesized), "first_page": expected[0] if expected else None, "last_page": expected[-1] if expected else None, "pages_with_vision": sum(bool(page.get("vision_description")) for page in pages), "pages_with_vision_errors": sum(bool(page.get("vision_error")) for page in pages)},
        "processing_version": PROCESSING_VERSION,
    }
    return lesson, pages


def _embedding_text(page: dict[str, Any]) -> str:
    return "\n".join(filter(None, [page.get("title"), page.get("source_text"), page.get("main_message"), page.get("vision_description"), " ".join(map(str, page.get("bilingual_aliases", []))) ]))


def lesson_assets_current(processed_root: Path, document_id: str, source: Path) -> bool:
    target = processed_root / document_id; manifest_path = target / "manifest.json"
    required = [target / name for name in ("lesson_map.json", "pages.json", "chunks.json", "embeddings.json", "manifest.json")]
    if not all(path.is_file() for path in required): return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")); provider = get_provider()
        status = provider.status(); previous = manifest.get("provider_status", {})
        generation_provider = manifest.get("generation_provider", previous.get("generation_provider"))
        vision_model = manifest.get("vision_model", previous.get("vision_model"))
        embedding_provider = manifest.get("embedding_provider", previous.get("embedding_provider"))
        return manifest.get("source_sha256") == _hash(source) and manifest.get("processing_version") == PROCESSING_VERSION and manifest.get("embedding_model") == provider.embedding_model and generation_provider == status["generation_provider"] and vision_model == status["vision_model"] and embedding_provider == status["embedding_provider"]
    except (OSError, ValueError, json.JSONDecodeError): return False


def save_lesson_assets(processed_root: Path, document_id: str, source: Path, original_name: str, pages: list[dict[str, Any]], force: bool = False, provider: AIProvider | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
    provider = provider or get_provider(); target = processed_root / document_id
    lesson_path, pages_path, chunks_path, embeddings_path, manifest_path = [target / name for name in ("lesson_map.json", "pages.json", "chunks.json", "embeddings.json", "manifest.json")]
    if not force and lesson_assets_current(processed_root, document_id, source):
        lesson, stored_pages, _ = load_lesson_assets(processed_root, document_id); return lesson, stored_pages, chunks_path
    target.mkdir(parents=True, exist_ok=True)
    lesson, pages = build_lesson_map(document_id, original_name, pages, provider)
    embedding_error = None; vectors: list[list[float]] = []
    try: vectors = provider.embeddings([_embedding_text(page) for page in pages])
    except Exception as exc: embedding_error = f"{type(exc).__name__}: {exc}"
    for page, vector in zip(pages, vectors): page["embedding"] = vector
    chunks = [page_to_chunk(page) for page in pages]
    lesson_path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")
    pages_path.write_text(json.dumps({"processing_version": PROCESSING_VERSION, "pages": pages}, ensure_ascii=False, indent=2), encoding="utf-8")
    chunks_path.write_text(json.dumps({"processing_version": PROCESSING_VERSION, "chunks": chunks}, ensure_ascii=False, indent=2), encoding="utf-8")
    embeddings_path.write_text(json.dumps({"processing_version": PROCESSING_VERSION, "provider": provider.embedding_provider, "model": provider.embedding_model, "error": embedding_error, "items": [{"page": page["page"], "embedding": page.get("embedding", [])} for page in pages]}, ensure_ascii=False), encoding="utf-8")
    status = provider.status()
    manifest_path.write_text(json.dumps({"source_sha256": _hash(source), "original_name": original_name, "processing_version": PROCESSING_VERSION, "generation_provider": status["generation_provider"], "vision_model": status["vision_model"], "embedding_provider": status["embedding_provider"], "embedding_model": provider.embedding_model, "provider_status": status}, ensure_ascii=False, indent=2), encoding="utf-8")
    return lesson, pages, chunks_path


def load_lesson_assets(processed_root: Path, document_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    target = processed_root / document_id
    lesson = json.loads((target / "lesson_map.json").read_text(encoding="utf-8"))
    pages = json.loads((target / "pages.json").read_text(encoding="utf-8"))["pages"]
    chunks = json.loads((target / "chunks.json").read_text(encoding="utf-8"))["chunks"]
    for page in pages:
        page["previous_page_relation"] = _specific_relation(page.get("previous_page_relation"))
        page["next_page_relation"] = _specific_relation(page.get("next_page_relation"))
    lesson["learning_objectives"] = _list(lesson.get("learning_objectives")); lesson["narrative_flow"] = _list(lesson.get("narrative_flow")); lesson["key_takeaways"] = _list(lesson.get("key_takeaways"))
    for section in lesson.get("sections", []):
        for field in ("main_claims", "concepts", "definitions", "formulas", "examples", "relationships_to_other_sections"): section[field] = _list(section.get(field))
    return lesson, pages, chunks
