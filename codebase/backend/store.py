"""Document and chat-session storage.

Documents live on disk under STORAGE_DIR so they survive a restart; the BM25
index and chat sessions are kept in memory, which is the right trade-off for a
prototype.
"""

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config import STORAGE_DIR
from pdf_utils import extract_pages, is_probably_scanned
from retrieval import PageIndex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Document:
    def __init__(self, meta: dict, pages: List[dict], directory: Path):
        self.id: str = meta["id"]
        self.filename: str = meta["filename"]
        self.uploaded_at: str = meta["uploaded_at"]
        self.size_bytes: int = meta["size_bytes"]
        self.scanned: bool = meta.get("scanned", False)
        self.pages = pages
        self.dir = directory
        self._index: Optional[PageIndex] = None

    @property
    def pdf_path(self) -> Path:
        return self.dir / "source.pdf"

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def total_chars(self) -> int:
        return sum(p["char_count"] for p in self.pages)

    @property
    def index(self) -> PageIndex:
        if self._index is None:
            self._index = PageIndex(self.pages)
        return self._index

    def page_text(self, page: int) -> str:
        if 1 <= page <= len(self.pages):
            return self.pages[page - 1]["text"]
        return ""

    def meta(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "uploaded_at": self.uploaded_at,
            "size_bytes": self.size_bytes,
            "scanned": self.scanned,
            "page_count": self.page_count,
        }


class DocumentStore:
    def __init__(self, root: Path = STORAGE_DIR):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._docs: Dict[str, Document] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        for directory in sorted(self.root.iterdir()):
            meta_file = directory / "meta.json"
            pages_file = directory / "pages.json"
            if not (directory.is_dir() and meta_file.exists() and pages_file.exists()):
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                pages = json.loads(pages_file.read_text(encoding="utf-8"))
                self._docs[meta["id"]] = Document(meta, pages, directory)
            except Exception as exc:  # corrupt folder should not block startup
                print(f"[store] skipping {directory.name}: {exc}")

    def add(self, filename: str, data: bytes) -> Document:
        doc_id = new_id("doc")
        directory = self.root / doc_id
        directory.mkdir(parents=True, exist_ok=True)
        pdf_path = directory / "source.pdf"
        pdf_path.write_bytes(data)

        pages = extract_pages(pdf_path)
        meta = {
            "id": doc_id,
            "filename": filename,
            "uploaded_at": _now(),
            "size_bytes": len(data),
            "scanned": is_probably_scanned(pages),
            "page_count": len(pages),
        }
        (directory / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (directory / "pages.json").write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")

        doc = Document(meta, pages, directory)
        self._docs[doc_id] = doc
        return doc

    def get(self, doc_id: str) -> Optional[Document]:
        return self._docs.get(doc_id)

    def list(self) -> List[Document]:
        return sorted(self._docs.values(), key=lambda d: d.uploaded_at, reverse=True)

    def delete(self, doc_id: str) -> bool:
        doc = self._docs.pop(doc_id, None)
        if not doc:
            return False
        shutil.rmtree(doc.dir, ignore_errors=True)
        return True


class ChatSession:
    def __init__(self, document_id: str):
        self.id = new_id("sess")
        self.document_id = document_id
        self.created_at = _now()
        self.messages: List[dict] = []

    def add(self, role: str, content: str, **extra) -> dict:
        message = {
            "id": new_id("msg"),
            "role": role,
            "content": content,
            "created_at": _now(),
            "citations": extra.get("citations", []),
            "grounded": extra.get("grounded", True),
            "highlights": extra.get("highlights", []),
            "screenshot_count": extra.get("screenshot_count", 0),
            "web_sources": extra.get("web_sources", []),
        }
        self.messages.append(message)
        return message


class SessionStore:
    def __init__(self):
        self._sessions: Dict[str, ChatSession] = {}

    def create(self, document_id: str) -> ChatSession:
        session = ChatSession(document_id)
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Optional[ChatSession]:
        return self._sessions.get(session_id)

    def list_for_document(self, document_id: str) -> List[ChatSession]:
        return [s for s in self._sessions.values() if s.document_id == document_id]

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def drop_document(self, document_id: str) -> None:
        for sid in [s.id for s in self.list_for_document(document_id)]:
            self._sessions.pop(sid, None)


documents = DocumentStore()
sessions = SessionStore()
