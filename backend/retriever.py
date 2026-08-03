"""Document-scoped BM25 + OpenAI multilingual embeddings + LLM reranking."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from ai_provider import AIProvider, get_provider

STOPWORDS = {"là", "gì", "hãy", "cho", "tôi", "một", "và", "của", "như", "thế", "nào", "tại", "sao", "the", "what", "is", "a", "an", "of", "how", "why"}


def tokens(text: str) -> list[str]:
    return [term for term in re.findall(r"[\wÀ-ỹ]+", (text or "").lower(), re.UNICODE) if term not in STOPWORDS and (len(term) > 1 or term.isdigit())]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right: return 0.0
    norm = math.sqrt(sum(value * value for value in left) * sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / norm if norm else 0.0


RERANK_PROMPT = """Rerank lecture pages for the user's query. Judge direct support, not keyword overlap. Return JSON {ranked:[{page,relevance,reason}]}, relevance 0..1. A page must directly help answer the query. Preserve document scope."""


class HybridRetriever:
    def __init__(self, chunks: list[dict[str, Any]], provider: AIProvider | None = None):
        self.chunks = chunks; self.provider = provider or get_provider()
        self.docs = [tokens(f"{item.get('title','')} {item.get('text','')}") for item in chunks]
        self.avg_len = sum(map(len, self.docs)) / max(1, len(self.docs)); self.df = Counter(token for doc in self.docs for token in set(doc))

    def _bm25(self, query: list[str], index: int) -> float:
        counts, score, size = Counter(self.docs[index]), 0.0, len(self.docs)
        for term in query:
            frequency = counts[term]
            if not frequency: continue
            inverse = math.log(1 + (size - self.df[term] + 0.5) / (self.df[term] + 0.5))
            score += inverse * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(self.docs[index]) / max(1, self.avg_len)))
        return score

    def search(self, query: str, current_page: int = 1, top_k: int = 5, explicit_page_target: bool = False, section: str | None = None) -> list[dict[str, Any]]:
        query_terms = tokens(query)
        query_embedding: list[float] = []
        if self.provider.embedding_provider == "openai":
            query_embedding = self.provider.embeddings([query])[0]
        bm25_values = [self._bm25(query_terms, index) for index in range(len(self.chunks))]; max_bm25 = max(bm25_values or [1]) or 1
        candidates = []
        for index, chunk in enumerate(self.chunks):
            bm25 = bm25_values[index] / max_bm25
            semantic = cosine(query_embedding, chunk.get("embedding", []))
            section_bonus = 0.08 if section and chunk.get("section") == section else 0.0
            proximity = 0.0 if explicit_page_target else max(0.0, 1 - abs(int(chunk.get("page", 1)) - current_page) / 4) * 0.05
            score = 0.48 * bm25 + 0.44 * semantic + section_bonus + proximity
            candidates.append({"chunk": chunk, "score": score, "bm25": bm25, "semantic": semantic, "proximity": proximity})
        shortlist = sorted(candidates, key=lambda item: item["score"], reverse=True)[: min(10, len(candidates))]
        if not shortlist: return []
        reranked = self.provider.json_completion(RERANK_PROMPT, {"query": query, "candidates": [{"page": item["chunk"]["page"], "title": item["chunk"].get("title"), "text": item["chunk"].get("text", "")[:1400], "hybrid_score": item["score"]} for item in shortlist]}, 1400).get("ranked", [])
        rank_by_page = {int(item["page"]): item for item in reranked if str(item.get("page", "")).isdigit()}
        for item in shortlist:
            rank = rank_by_page.get(int(item["chunk"]["page"]), {})
            item["rerank_score"] = float(rank.get("relevance", 0)); item["rerank_reason"] = rank.get("reason", "")
            item["score"] = 0.25 * item["score"] + 0.75 * item["rerank_score"]
        return [item for item in sorted(shortlist, key=lambda value: value["score"], reverse=True) if item["rerank_score"] >= 0.2][:top_k]


def confidence_for(results: list[dict[str, Any]]) -> tuple[str, int]:
    if not results: return "low", 15
    top = results[0].get("rerank_score", results[0]["score"])
    direct = sum(item.get("rerank_score", 0) >= 0.7 for item in results)
    if top >= 0.78 and direct: return "high", min(95, round(65 + top * 30))
    if top >= 0.45: return "medium", min(79, round(40 + top * 40))
    return "low", min(49, round(15 + top * 40))


TranscriptRetriever = HybridRetriever
