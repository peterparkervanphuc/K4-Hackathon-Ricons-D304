"""Deterministic page addressing that always runs before semantic retrieval."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass
class PageReference:
    route: str | None = None
    pages: list[int] | None = None
    error: str | None = None

    def to_dict(self) -> dict: return asdict(self)


NUMBER_WORDS = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "ten": 10}


def _number(value: str) -> int:
    return int(value) if value.isdigit() else NUMBER_WORDS.get(value.lower(), 0)


def parse_page_reference(question: str, current_page: int, total_pages: int) -> PageReference:
    q = question.lower().strip()
    # A conversational prefix such as "đang ở trang 10" describes viewer
    # state, not a second target page. The API's current_page is authoritative.
    target_q = re.sub(
        r"(?:đang|hiện)\s+ở\s+(?:trang|slide)(?:\s+số)?\s*\d+\s*[,;:]?\s*",
        "",
        q,
    )
    target_q = re.sub(
        r"currently\s+(?:on|at)\s+(?:page|slide)\s*\d+\s*[,;:]?\s*",
        "",
        target_q,
    )
    pages: list[int] = []
    range_match = re.search(r"(?:từ|from)\s+(?:trang|slide)?\s*(\d+)\s+(?:đến|tới|to|-)\s+(?:trang|slide)?\s*(\d+)", target_q)
    compare = re.search(r"(?:so sánh|compare).*?(?:trang|slide)\s*(\d+).*?(?:trang|slide)\s*(\d+)", target_q)
    relative = re.search(r"(?:trang|slide)\s*n\s*([+-])\s*(\d+)", target_q)
    next_count = re.search(r"(một|hai|ba|bốn|năm|\d+)\s+(?:trang|slide)\s+(?:tiếp theo|sau)", target_q)
    explicit = re.findall(r"(?:trang|slide)(?:\s+số)?\s*(\d+)", target_q)
    if range_match:
        start, end = map(int, range_match.groups()); pages = list(range(min(start, end), max(start, end) + 1)); route = "page_range_question"
    elif compare:
        pages = [int(compare.group(1)), int(compare.group(2))]; route = "comparison_question"
    elif relative:
        offset = int(relative.group(2)) * (1 if relative.group(1) == "+" else -1); pages = [current_page + offset]; route = "exact_page_question"
    elif next_count:
        count = _number(next_count.group(1)); pages = list(range(current_page + 1, current_page + count + 1)); route = "page_range_question"
    elif re.search(r"(?:trang|slide)\s+(?:tiếp theo|sau)|next (?:page|slide)", target_q): pages, route = [current_page + 1], "exact_page_question"
    elif re.search(r"(?:trang|slide)\s+trước|previous (?:page|slide)", target_q): pages, route = [current_page - 1], "exact_page_question"
    elif explicit:
        pages = [int(value) for value in explicit]; route = "comparison_question" if len(pages) > 1 else "exact_page_question"
    elif re.search(r"(?:trang|slide)\s+(?:này|hiện tại)|current (?:page|slide)", target_q): pages, route = [current_page], "current_page_question"
    else: return PageReference()
    invalid = [page for page in pages if page < 1 or page > total_pages]
    if invalid: return PageReference(route=route, pages=pages, error=f"Trang {invalid[0]} nằm ngoài phạm vi 1–{total_pages}.")
    return PageReference(route=route, pages=pages)
