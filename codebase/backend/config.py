"""Runtime configuration, loaded from environment (.env supported)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent

# Look for a .env next to the backend first, then walk up to the repo root.
for candidate in (BASE_DIR / ".env", BASE_DIR.parent / ".env", REPO_ROOT / ".env"):
    if candidate.exists():
        load_dotenv(candidate, override=False)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Override this when a different OpenAI model better fits the deployment's
# quality, latency, or cost requirements.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-sol")

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage")))
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "40"))

# Total tries per model call, including the first. Only transient failures
# (rate limits, overloaded backends, timeouts, unusable output) are retried.
OPENAI_MAX_ATTEMPTS = int(os.getenv("OPENAI_MAX_ATTEMPTS", "3"))
OPENAI_RETRY_BASE_DELAY = float(os.getenv("OPENAI_RETRY_BASE_DELAY", "0.6"))

# If the whole document fits in this many characters we send all of it to the
# model, which gives the strongest grounding. Larger documents fall back to
# retrieval over the page chunks.
FULL_DOC_CHAR_BUDGET = int(os.getenv("FULL_DOC_CHAR_BUDGET", "120000"))

# Number of pages pulled by the retriever when the document is too large to
# send whole.
TOP_K_PAGES = int(os.getenv("TOP_K_PAGES", "6"))

# How many previous turns of a chat session are replayed to the model.
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "8"))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]


def openai_configured() -> bool:
    return bool(OPENAI_API_KEY)
