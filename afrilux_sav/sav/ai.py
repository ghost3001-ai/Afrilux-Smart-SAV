import json
import re
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


class OpenAIResponsesClient:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = settings.OPENAI_BASE_URL.rstrip("/")
        self.model = settings.OPENAI_MODEL
        self.reasoning_effort = settings.OPENAI_REASONING_EFFORT

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def complete_json(self, system_prompt: str, user_prompt: str, max_output_tokens: int = 1200) -> LLMCompletion:
        if not self.enabled:
            return LLMCompletion(
                ok=False,
                content="",
                raw={},
                provider="fallback",
                model="",
                request_id="",
                error_message="OPENAI_API_KEY is not configured.",
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
            error_message="OpenAI returned non-JSON output.",
        )

    def _post(self, path: str, payload: dict[str, Any]) -> LLMCompletion:
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
            with request.urlopen(req, timeout=60) as response:
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
