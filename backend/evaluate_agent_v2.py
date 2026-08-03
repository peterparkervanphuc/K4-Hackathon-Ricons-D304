"""Architecture and live semantic evaluation for the page-aware tutor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from ai_provider import AIConfigurationError, AIProvider
from page_reference import parse_page_reference


ROOT = Path(__file__).resolve().parent.parent
PPTX_ID = "7cc439f5-19c8-471c-bbe3-f122c6050f2e"
PDF_ID = "5e1a4c40-2cb5-4499-a825-37b1fdfd7ac7"


def check(name: str, passed: bool, detail: Any = None, skipped: bool = False) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "skipped": skipped, "detail": detail}


def architecture_checks() -> list[dict[str, Any]]:
    cases = [
        ("Trang 5 viết gì?", 4, [5], "exact_page_question"), ("Trang n-4 nói về gì?", 8, [4], "exact_page_question"),
        ("Trang tiếp theo có ví dụ nào?", 4, [5], "exact_page_question"), ("Ba trang tiếp theo", 4, [5, 6, 7], "page_range_question"),
        ("Từ trang 5 đến trang 9", 1, [5, 6, 7, 8, 9], "page_range_question"), ("So sánh trang 3 và trang 9", 1, [3, 9], "comparison_question"),
    ]
    results = []
    for question, current, pages, route in cases:
        parsed = parse_page_reference(question, current, 20)
        results.append(check(f"page parser: {question}", parsed.pages == pages and parsed.route == route, parsed.to_dict()))
    old = {key: os.environ.get(key) for key in ("OPENAI_API_KEY", "GROQ_API_KEY", "AI_PROVIDER")}
    try:
        os.environ.update({"OPENAI_API_KEY": "", "GROQ_API_KEY": "fallback-placeholder", "AI_PROVIDER": "openai"})
        results.append(check("OpenAI missing -> Groq fallback", AIProvider().generation_provider == "groq"))
        os.environ.update({"OPENAI_API_KEY": "", "GROQ_API_KEY": ""})
        provider = AIProvider(); clear = False
        try: provider.require_generation()
        except AIConfigurationError as exc: clear = "OPENAI_API_KEY" in str(exc) and "GROQ_API_KEY" in str(exc)
        results.append(check("Both keys missing -> clear configuration error", clear))
    finally:
        for key, value in old.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value
    processed = ROOT / "storage" / "processed" / PPTX_ID
    if (processed / "pages.json").is_file():
        from lesson_map import load_lesson_assets
        lesson, pages, _ = load_lesson_assets(ROOT / "storage" / "processed", PPTX_ID)
        results.append(check("PPTX PageRecord coverage", len(pages) == 10, len(pages)))
        required = {"page", "source_text", "title", "vision_description", "main_message", "concepts", "definitions", "formulas", "examples", "tables", "charts", "notes", "previous_page_relation", "next_page_relation", "confidence", "source_language", "bilingual_aliases", "embedding"}
        results.append(check("PageRecord schema", all(required <= set(page) for page in pages)))
        generic = {"extends a definition", "gives an example", "applies a formula", "introduces a special case", "changes topic", "concludes", "extends"}
        results.append(check("No fake generic relations", not any(str(page.get(field, "")).lower() in generic or "Tiếp nối từ" in str(page.get(field, "")) for page in pages for field in ("previous_page_relation", "next_page_relation"))))
        covered = [number for section in lesson["sections"] for number in section["pages"]]
        results.append(check("LessonMap covers all pages once", covered == list(range(1, 11)), covered))
        results.append(check("Embedding cache exists", (processed / "embeddings.json").is_file()))
        source = ROOT / "storage" / "uploads" / f"{PPTX_ID}.pptx"
        manifest = json.loads((processed / "manifest.json").read_text(encoding="utf-8"))
        results.append(check("Original source hash unchanged", hashlib.sha256(source.read_bytes()).hexdigest() == manifest["source_sha256"]))
    else: results.append(check("PPTX processed assets", False, "missing"))
    return results


def live_checks(base_url: str) -> list[dict[str, Any]]:
    import httpx
    results = []
    def provider_unavailable(response: httpx.Response) -> bool:
        return response.status_code == 503 and "ai_provider_unavailable" in response.text
    cases = [
        ("Trang 5 viết gì?", 4, [5], ["bánh", "thặng dư"]),
        ("Trang n-4 nói về gì?", 8, [4], ["mu", "mc"]),
        ("Trang tiếp theo có ví dụ nào?", 4, [5], ["bánh"]),
        ("So sánh trang 3 và trang 9.", 1, [3, 9], ["thặng dư", "lợi ích"]),
        ("Tóm tắt từ trang 5 đến trang 10.", 1, list(range(5, 11)), ["ví dụ", "kết luận"]),
        ("Đang ở trang 10, slide 3 nói về gì?", 10, [3], ["thặng dư"]),
    ]
    with httpx.Client(base_url=base_url, timeout=120) as client:
        for question, current, expected_pages, claims in cases:
            response = client.post("/api/tutor/ask", json={"question": question, "documentId": PPTX_ID, "page": current, "history": []})
            if response.status_code != 200:
                unavailable = provider_unavailable(response)
                results.append(check(f"live: {question}", False, {"status": response.status_code, "body": response.text[:500]}, skipped=unavailable)); continue
            data = response.json(); answer = data["answer"].lower(); cited = [item["page"] for item in data["citations"]]
            passed = all(claim in answer for claim in claims) and all(page in expected_pages for page in cited) and bool(cited)
            results.append(check(f"live: {question}", passed, {"route": data["question_type"], "citations": cited, "answer": data["answer"]}))

        pdf_cases = [
            ("Trang 5 viết gì?", 4, [5], ["hệ thống", "đầu vào", "đầu ra"]),
            ("Trang n-4 nói về gì?", 8, [4], ["tín hiệu", "thông tin"]),
            ("Trang tiếp theo có ví dụ nào?", 3, [4], ["ecg", "tín hiệu"]),
            ("Trang 8 giải thích công thức nào?", 20, [8], ["năng lượng", "công suất"]),
        ]
        for question, current, expected_pages, claims in pdf_cases:
            response = client.post("/api/tutor/ask", json={"question": question, "documentId": PDF_ID, "page": current, "history": []})
            if response.status_code != 200:
                results.append(check(f"live PDF: {question}", False, {"status": response.status_code, "body": response.text[:500]}, skipped=provider_unavailable(response))); continue
            data = response.json(); answer = data["answer"].lower(); cited = [item["page"] for item in data["citations"]]
            results.append(check(f"live PDF: {question}", all(claim in answer for claim in claims) and cited == expected_pages, {"route": data["question_type"], "citations": cited, "answer": data["answer"]}))

        summary_response = client.post("/api/tutor/ask", json={"question": "Tóm tắt toàn bộ bài giảng này bằng tiếng Việt.", "documentId": PDF_ID, "page": 1, "history": []})
        if summary_response.status_code == 200:
            data = summary_response.json(); answer = data["answer"].lower(); cited = [item["page"] for item in data["citations"]]
            spans_document = any(page <= 5 for page in cited) and any(8 <= page <= 16 for page in cited) and any(page >= 17 for page in cited)
            claims = ["tín hiệu", "hệ thống", "năng lượng", "thao tác"]
            results.append(check("live PDF: whole-document hierarchical summary", data["question_type"] == "document_summary" and spans_document and all(claim in answer for claim in claims), {"citations": cited, "answer": data["answer"]}))
        else:
            results.append(check("live PDF: whole-document hierarchical summary", False, {"status": summary_response.status_code, "body": summary_response.text[:500]}, skipped=provider_unavailable(summary_response)))

        answers = []; answer_responses = []
        for document_id in (PDF_ID, PPTX_ID):
            response = client.post("/api/tutor/ask", json={"question": "Trang 4 nói về gì?", "documentId": document_id, "page": 1, "history": []})
            answer_responses.append(response)
            answers.append(response.json() if response.status_code == 200 else {})
        source_specific = (
            "tín hiệu" in str(answers[0].get("answer", "")).lower()
            and all(term in str(answers[1].get("answer", "")).lower() for term in ("mu", "mc"))
            and answers[0].get("answer") != answers[1].get("answer")
        )
        source_check_skipped = any(provider_unavailable(response) for response in answer_responses)
        results.append(check("same question is grounded differently per document", source_specific, {"pdf": answers[0].get("answer"), "pptx": answers[1].get("answer")}, skipped=source_check_skipped))

        page_range = client.get(f"/api/documents/{PDF_ID}/pages", params={"from": 5, "to": 9})
        range_data = page_range.json() if page_range.status_code == 200 else []
        results.append(check("page range endpoint returns exact ordered PageRecords", [item.get("page") for item in range_data] == [5, 6, 7, 8, 9], range_data))
        status = client.get("/api/system/ai-status").json()
        exact_openai_status = (
            status.get("generation_provider") == "openai"
            and status.get("generation_model") == "gpt-4.1"
            and status.get("vision_model") == "gpt-4o"
            and status.get("embedding_model") == "text-embedding-3-small"
        )
        results.append(check("safe provider status", "OPENAI_API_KEY" not in json.dumps(status) and exact_openai_status, status))
    return results


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(); parser.add_argument("--live", action="store_true"); parser.add_argument("--base-url", default="http://172.20.113.206:8000")
    args = parser.parse_args(); results = architecture_checks()
    if args.live: results.extend(live_checks(args.base_url))
    report = {"passed": sum(item["passed"] for item in results), "failed": sum(not item["passed"] and not item["skipped"] for item in results), "skipped": sum(item["skipped"] for item in results), "total": len(results), "results": results}
    output_name = "agent_v2_live_evaluation.json" if args.live else "agent_v2_evaluation.json"
    Path(__file__).with_name(output_name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)); return 0 if report["failed"] == 0 else 1


if __name__ == "__main__": raise SystemExit(main())
