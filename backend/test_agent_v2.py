from __future__ import annotations

import os
import unittest

from ai_provider import AIConfigurationError, AIProvider
from page_reference import parse_page_reference
from tutor_agent import _grounding_confidence


class PageReferenceTests(unittest.TestCase):
    def test_exact_page_overrides_current(self):
        result = parse_page_reference("Trang 5 viết gì?", 4, 20)
        self.assertEqual((result.route, result.pages), ("exact_page_question", [5]))

    def test_viewer_state_prefix_is_not_a_comparison(self):
        result = parse_page_reference("Đang ở trang 10, slide 3 nói về gì?", 10, 20)
        self.assertEqual((result.route, result.pages), ("exact_page_question", [3]))

    def test_relative_page(self):
        self.assertEqual(parse_page_reference("Trang n-4", 8, 20).pages, [4])

    def test_range_and_comparison(self):
        self.assertEqual(parse_page_reference("Từ trang 5 đến trang 9", 1, 20).pages, [5, 6, 7, 8, 9])
        self.assertEqual(parse_page_reference("So sánh trang 3 và trang 9", 1, 20).pages, [3, 9])

    def test_bounds(self):
        self.assertIsNotNone(parse_page_reference("Trang trước", 1, 20).error)


class ProviderTests(unittest.TestCase):
    def test_missing_keys_is_explicit(self):
        old_openai, old_groq = os.environ.get("OPENAI_API_KEY"), os.environ.get("GROQ_API_KEY")
        try:
            os.environ["OPENAI_API_KEY"] = ""; os.environ["GROQ_API_KEY"] = ""
            with self.assertRaises(AIConfigurationError): AIProvider().require_generation()
        finally:
            if old_openai is None: os.environ.pop("OPENAI_API_KEY", None)
            else: os.environ["OPENAI_API_KEY"] = old_openai
            if old_groq is None: os.environ.pop("GROQ_API_KEY", None)
            else: os.environ["GROQ_API_KEY"] = old_groq


class ConfidenceTests(unittest.TestCase):
    def test_document_summary_uses_section_coverage(self):
        lesson = {"sections": [{"pages": [1, 2]}, {"pages": [3, 4]}, {"pages": [5, 6]}]}
        allowed = {page: {"page": page} for page in range(1, 7)}
        citations = [{"page": page, "claim": "claim", "supporting_text": "support"} for page in (1, 3, 5)]
        self.assertEqual(_grounding_confidence("document_summary", lesson, allowed, citations), ("high", 100))

    def test_missing_citations_is_low_confidence(self):
        self.assertEqual(_grounding_confidence("exact_page_question", {}, {4: {"page": 4}}, []), ("low", 20))


if __name__ == "__main__": unittest.main()
