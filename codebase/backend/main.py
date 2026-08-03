"""PDF Tutor — FastAPI backend.

Run from this directory:
    uvicorn main:app --reload --port 8000
Swagger UI: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from routers import chat, documents, quiz
from schemas import HealthResponse
from store import documents as document_store

TAGS_METADATA = [
    {"name": "documents", "description": "Upload PDFs and read their page-by-page text chunks."},
    {
        "name": "chat",
        "description": "Grounded Q&A over one document. Sessions keep conversation context; "
        "answers may only use content from the uploaded PDF.",
    },
    {"name": "quiz", "description": "Generate 4-option multiple-choice questions from the document."},
    {"name": "system", "description": "Health and configuration."},
]

app = FastAPI(
    title="PDF Tutor API",
    version="1.0.0",
    description=(
        "Upload a PDF, highlight passages or crop screenshots, and ask a **strictly grounded** "
        "tutor about them.\n\n"
        "**Grounding contract:** the model is given only the pages of the uploaded document. "
        "Every citation quote is re-checked against the extracted page text before the answer "
        "is returned, and quiz questions whose evidence cannot be located are discarded."
    ),
    openapi_tags=TAGS_METADATA,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(quiz.router)


@app.get("/api/health", response_model=HealthResponse, tags=["system"], summary="Service health")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        openai_configured=config.openai_configured(),
        model=config.OPENAI_MODEL,
        documents=len(document_store.list()),
    )
