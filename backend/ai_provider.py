"""OpenAI-first provider gateway with explicit Groq fallback and safe status."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any


def _parse_json_object(content: str | None) -> dict[str, Any]:
    """Parse provider JSON defensively without inventing an answer."""
    if not content or not content.strip():
        raise ValueError("AI provider returned an empty response.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        from json_repair import repair_json

        parsed = json.loads(repair_json(content))
    if not isinstance(parsed, dict):
        raise ValueError("AI provider response is not a JSON object.")
    return parsed


class AIConfigurationError(RuntimeError):
    pass


class AIProviderUnavailableError(RuntimeError):
    pass


class AIProvider:
    def __init__(self) -> None:
        requested = os.getenv("AI_PROVIDER", "openai").strip().lower()
        self.openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.groq_key = os.getenv("GROQ_API_KEY", "").strip()
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1")
        self.openai_vision_model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
        self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.groq_vision_model = os.getenv("GROQ_VISION_MODEL", self.groq_model)
        if requested == "openai" and self.openai_key:
            self.generation_provider = self.vision_provider = "openai"
        elif self.groq_key:
            self.generation_provider = self.vision_provider = "groq"
        elif self.openai_key:
            self.generation_provider = self.vision_provider = "openai"
        else:
            self.generation_provider = self.vision_provider = "unconfigured"
        self.embedding_provider = "openai" if self.openai_key else "unconfigured"

    def require_generation(self) -> None:
        if self.generation_provider == "unconfigured":
            raise AIConfigurationError("Chưa cấu hình OPENAI_API_KEY và cũng không có GROQ_API_KEY fallback.")

    def status(self) -> dict[str, Any]:
        configured = self.generation_provider != "unconfigured"
        return {
            "generation_provider": self.generation_provider,
            "generation_model": self.openai_model if self.generation_provider == "openai" else self.groq_model if configured else None,
            "vision_provider": self.vision_provider,
            "vision_model": self.openai_vision_model if self.vision_provider == "openai" else self.groq_vision_model if configured else None,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model if self.embedding_provider == "openai" else None,
            "research_provider": "tavily" if os.getenv("TAVILY_API_KEY", "").strip() else "unconfigured",
            "configured": configured,
            "openai_configured": bool(self.openai_key),
            "groq_fallback_configured": bool(self.groq_key),
        }

    def json_completion(self, system: str, payload: dict[str, Any], max_tokens: int = 1800) -> dict[str, Any]:
        self.require_generation()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        try:
            if self.generation_provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=self.openai_key)
                response = client.chat.completions.create(model=self.openai_model, messages=messages, temperature=0.1, max_tokens=max_tokens, response_format={"type": "json_object"})
                if response.choices[0].finish_reason == "length" and max_tokens < 5200:
                    retry_messages = [
                        {"role": "system", "content": system + "\nBe concise and finish the complete JSON object within the output budget."},
                        messages[1],
                    ]
                    response = client.chat.completions.create(model=self.openai_model, messages=retry_messages, temperature=0.1, max_tokens=5200, response_format={"type": "json_object"})
            else:
                from groq import Groq
                client = Groq(api_key=self.groq_key)
                response = client.chat.completions.create(model=self.groq_model, messages=messages, temperature=0.0, max_tokens=max_tokens, response_format={"type": "json_object"})
                if response.choices[0].finish_reason == "length" and max_tokens < 5200:
                    retry_messages = [
                        {"role": "system", "content": system + "\nBe concise and finish the complete JSON object within the output budget."},
                        messages[1],
                    ]
                    response = client.chat.completions.create(model=self.groq_model, messages=retry_messages, temperature=0.0, max_tokens=5200, response_format={"type": "json_object"})
            return _parse_json_object(response.choices[0].message.content)
        except Exception as exc:
            if self.generation_provider == "openai" and self.groq_key:
                try:
                    from groq import Groq

                    fallback = Groq(api_key=self.groq_key).chat.completions.create(
                        model=self.groq_model,
                        messages=messages,
                        temperature=0.0,
                        max_tokens=min(max(max_tokens, 2600), 5200),
                        response_format={"type": "json_object"},
                    )
                    return _parse_json_object(fallback.choices[0].message.content)
                except Exception as fallback_exc:
                    exc = fallback_exc
            failed = (getattr(exc, "body", {}) or {}).get("error", {}).get("failed_generation")
            if failed:
                from json_repair import repair_json
                return json.loads(repair_json(failed))
            status = getattr(exc, "status_code", None)
            if status == 429: raise AIProviderUnavailableError(f"{self.generation_provider} đang vượt giới hạn sử dụng; hãy thử lại sau hoặc cấu hình OPENAI_API_KEY.") from exc
            raise AIProviderUnavailableError(f"Không thể gọi {self.generation_provider} model: {type(exc).__name__}.") from exc

    def vision_json(self, image_path: Path, extracted: dict[str, Any]) -> dict[str, Any]:
        self.require_generation()
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        data_url = f"data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode('ascii')}"
        instruction = """Analyze the complete rendered lecture page, not isolated pictures. Return JSON with vision_description, main_message, concepts, definitions, formulas, examples, charts, bilingual_aliases, uncertain_content, confidence. Explain spatial relationships among title, text, arrows, diagrams, tables, axes and images. Preserve source language in quoted source content; aliases are separate."""
        content = [{"type": "text", "text": instruction + "\nEXTRACTED:\n" + json.dumps(extracted, ensure_ascii=False)}, {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}}]
        try:
            if self.vision_provider == "openai":
                from openai import OpenAI
                response = OpenAI(api_key=self.openai_key).chat.completions.create(model=self.openai_vision_model, messages=[{"role": "user", "content": content}], temperature=0.1, max_tokens=1400, response_format={"type": "json_object"})
            else:
                from groq import Groq
                response = Groq(api_key=self.groq_key).chat.completions.create(model=self.groq_vision_model, messages=[{"role": "user", "content": content}], temperature=0.1, max_tokens=1400, response_format={"type": "json_object"})
        except Exception as exc:
            if self.vision_provider != "openai" or not self.groq_key:
                raise AIProviderUnavailableError(f"Không thể gọi {self.vision_provider} vision model: {type(exc).__name__}.") from exc
            try:
                from groq import Groq

                response = Groq(api_key=self.groq_key).chat.completions.create(model=self.groq_vision_model, messages=[{"role": "user", "content": content}], temperature=0.1, max_tokens=1400, response_format={"type": "json_object"})
            except Exception as fallback_exc:
                raise AIProviderUnavailableError(f"OpenAI vision lỗi và Groq fallback cũng không khả dụng: {type(fallback_exc).__name__}.") from fallback_exc
        return _parse_json_object(response.choices[0].message.content)

    def embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self.openai_key:
            raise AIConfigurationError("Multilingual embedding cần OPENAI_API_KEY; hiện chỉ có thể dùng BM25 fallback.")
        from openai import OpenAI
        try:
            response = OpenAI(api_key=self.openai_key).embeddings.create(model=self.embedding_model, input=texts)
        except Exception as exc:
            raise AIProviderUnavailableError(f"Không thể gọi OpenAI embedding model: {type(exc).__name__}.") from exc
        return [item.embedding for item in response.data]


def get_provider() -> AIProvider:
    return AIProvider()
