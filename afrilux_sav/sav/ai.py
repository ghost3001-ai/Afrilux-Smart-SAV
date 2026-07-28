import json
import re
import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from django.conf import settings


@dataclass
class LLMCompletion:
    ok: bool
    content: str
    raw: dict[str, Any]
    provider: str
    model: str
    request_id: str
    error_message: str = ""


class _RateLimiter:
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._timestamps and self._timestamps[0] < now - self._window_seconds:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._max_requests:
                return False
            self._timestamps.append(now)
            return True

    @property
    def retry_after(self) -> float:
        if not self._timestamps:
            return 0.0
        return max(0.0, self._window_seconds - (time.monotonic() - self._timestamps[0]))


class OpenAIResponsesClient:
    PLACEHOLDER_KEYS = {"", "sk-...", "sk-xxx", "change-me", "votre-cle-openai"}
    _rate_limiter = _RateLimiter(
        max_requests=getattr(settings, "OPENAI_RATE_LIMIT_MAX_REQUESTS", 30),
        window_seconds=getattr(settings, "OPENAI_RATE_LIMIT_WINDOW_SECONDS", 60),
    )

    @property
    def api_key(self) -> str:
        return str(getattr(settings, "OPENAI_API_KEY", "") or "").strip()

    @property
    def base_url(self) -> str:
        return str(getattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1") or "").rstrip("/")

    @property
    def model(self) -> str:
        return str(getattr(settings, "OPENAI_MODEL", "gpt-5.1") or "gpt-5.1").strip()

    @property
    def reasoning_effort(self) -> str:
        return str(getattr(settings, "OPENAI_REASONING_EFFORT", "") or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.api_key.lower() not in self.PLACEHOLDER_KEYS)

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            reason = "OPENAI_API_KEY absente ou valeur placeholder."
            return {
                "enabled": False,
                "mode": "heuristique",
                "provider": "fallback",
                "model": "",
                "base_url": self.base_url,
                "reason": reason,
            }
        return {
            "enabled": True,
            "mode": "openai",
            "provider": "openai",
            "model": self.model,
            "base_url": self.base_url,
            "reason": "",
        }

    def complete_json(self, system_prompt: str, user_prompt: str, max_output_tokens: int = 1200) -> LLMCompletion:
        if not self.enabled:
            return LLMCompletion(
                ok=False,
                content="",
                raw={},
                provider="fallback",
                model="",
                request_id="",
                error_message="OPENAI_API_KEY absente ou valeur placeholder.",
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "max_output_tokens": max_output_tokens,
            "text": {"format": {"type": "json_object"}},
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}

        raw_response = self._post("/responses", payload)
        if not raw_response.ok:
            return raw_response

        text = raw_response.content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()

        try:
            json.loads(text)
            return raw_response
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                trimmed = match.group(0)
                try:
                    json.loads(trimmed)
                    raw_response.content = trimmed
                    return raw_response
                except json.JSONDecodeError:
                    pass

        return LLMCompletion(
            ok=False,
            content=text,
            raw=raw_response.raw,
            provider=raw_response.provider,
            model=raw_response.model,
            request_id=raw_response.request_id,
            error_message="OpenAI a renvoyé une réponse qui n’est pas au format JSON.",
        )

    def _post(self, path: str, payload: dict[str, Any]) -> LLMCompletion:
        if not self._rate_limiter.acquire():
            retry_after = self._rate_limiter.retry_after
            return LLMCompletion(
                ok=False,
                content="",
                raw={},
                provider="openai",
                model=self.model,
                request_id="",
                error_message=f"Rate limit OpenAI atteint. Reessayez dans {retry_after:.0f}s.",
            )

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            timeout_seconds = int(getattr(settings, "OPENAI_TIMEOUT_SECONDS", 60) or 60)
            with request.urlopen(req, timeout=timeout_seconds) as response:
                raw_payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            return LLMCompletion(
                ok=False,
                content="",
                raw={"status": exc.code, "body": response_body},
                provider="openai",
                model=self.model,
                request_id="",
                error_message=f"OpenAI HTTP {exc.code}: {response_body[:400]}",
            )
        except Exception as exc:  # noqa: BLE001
            return LLMCompletion(
                ok=False,
                content="",
                raw={},
                provider="openai",
                model=self.model,
                request_id="",
                error_message=str(exc),
            )

        output_text = raw_payload.get("output_text")
        if not output_text:
            chunks: list[str] = []
            for item in raw_payload.get("output", []):
                for content in item.get("content", []):
                    text = content.get("text")
                    if text:
                        chunks.append(text)
            output_text = "\n".join(chunks).strip()

        return LLMCompletion(
            ok=True,
            content=output_text,
            raw=raw_payload,
            provider="openai",
            model=raw_payload.get("model", self.model),
            request_id=raw_payload.get("id", ""),
        )
