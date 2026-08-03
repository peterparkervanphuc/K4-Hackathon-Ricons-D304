"""Request/response models. These drive the Swagger UI at /docs."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------
class PageSummary(BaseModel):
    page: int = Field(..., description="1-based page number")
    char_count: int = Field(..., description="Characters of extractable text on the page")


class DocumentSummary(BaseModel):
    id: str
    filename: str
    page_count: int
    uploaded_at: str
    size_bytes: int
    scanned: bool = Field(
        False,
        description="True when the PDF has almost no extractable text (image-only scan). "
        "Text answers will be weak; screenshot questions still work.",
    )


class DocumentDetail(DocumentSummary):
    pages: List[PageSummary]


class PageText(BaseModel):
    page: int
    text: str


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------
class Highlight(BaseModel):
    page: int = Field(..., description="Page the text was highlighted on")
    text: str = Field(..., description="Verbatim highlighted text")


class Screenshot(BaseModel):
    page: int = Field(..., description="Page the crop was taken from")
    data_url: str = Field(
        ...,
        description="`data:image/jpeg;base64,...` crop of the rendered page",
        json_schema_extra={"example": "data:image/jpeg;base64,/9j/4AAQ..."},
    )


class Citation(BaseModel):
    page: int
    quote: str
    verified: bool = Field(
        True,
        description="True when the quote was found verbatim in the extracted page text",
    )


class WebSource(BaseModel):
    title: str
    url: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The learner's question")
    page: Optional[int] = Field(None, description="Page currently open in the viewer")
    highlights: List[Highlight] = Field(default_factory=list, description="Zero or more highlighted passages")
    screenshots: List[Screenshot] = Field(default_factory=list, description="Zero or more page crops")
    use_web: bool = Field(
        False,
        description="Allow Google Search to find supplementary, cited explanations beyond the PDF",
    )


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str
    citations: List[Citation] = Field(default_factory=list)
    grounded: bool = True
    highlights: List[Highlight] = Field(default_factory=list)
    screenshot_count: int = 0
    web_sources: List[WebSource] = Field(default_factory=list)


class SessionSummary(BaseModel):
    id: str
    document_id: str
    created_at: str
    message_count: int


class SessionDetail(SessionSummary):
    messages: List[ChatMessage]


class CreateSessionRequest(BaseModel):
    document_id: str


class AskResponse(BaseModel):
    session_id: str
    message: ChatMessage
    suggested_followups: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Quiz
# --------------------------------------------------------------------------
class QuizRequest(BaseModel):
    document_id: str
    num_questions: int = Field(5, ge=1, le=15)
    page_from: Optional[int] = Field(None, description="First page to draw from (inclusive)")
    page_to: Optional[int] = Field(None, description="Last page to draw from (inclusive)")
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    language: Optional[str] = Field(
        None,
        description="Language for the quiz. Defaults to the language of the document.",
    )


class QuizQuestion(BaseModel):
    question: str
    options: List[str] = Field(..., min_length=4, max_length=4)
    correct_index: int = Field(..., ge=0, le=3)
    explanation: str
    source_page: int
    evidence_quote: str
    verified: bool = Field(
        True, description="True when the evidence quote was found verbatim on the cited page"
    )


class QuizResponse(BaseModel):
    document_id: str
    questions: List[QuizQuestion]
    dropped: int = Field(0, description="Questions discarded because they failed grounding checks")


class HealthResponse(BaseModel):
    status: str
    openai_configured: bool
    model: str
    documents: int
