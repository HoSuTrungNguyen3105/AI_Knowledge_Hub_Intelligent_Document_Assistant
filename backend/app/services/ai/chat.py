import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from app.services.ai.base_provider import ProviderError

# Fixed official endpoints. Credentials never travel to a caller-supplied host.
CHAT_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent",
}


@dataclass(frozen=True)
class ChatLimits:
    deadline_seconds: float = 120.0
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 60.0
    max_response_bytes: int = 8 * 1024 * 1024


class SecretRedactor:
    """Rolling-window guard over extracted delta text.

    Raw SSE scanning cannot catch a credential split across two delta content
    values (JSON syntax sits between them). Feeding the extracted text through a
    tail window catches that case before the text is yielded to the client.
    """

    def __init__(self, secret: str):
        self._secret = secret
        self._tail = ""
        self._keep = max(len(secret) - 1, 0)

    def feed(self, text: str) -> None:
        if self._secret and self._secret in (self._tail + text):
            raise ProviderError("generation_failed")
        if self._keep:
            self._tail = (self._tail + text)[-self._keep:]


async def _sse_events(
    chunks: AsyncIterator[str], secret: str, max_bytes: int
) -> AsyncIterator[dict]:
    """Parse Server-Sent Events into JSON objects, redacting any echoed credential.

    A rolling tail catches a key split across two events. Only ``data:`` lines are
    interpreted; comments/event/id fields are ignored. ``[DONE]`` ends the stream.
    """
    buffer = ""
    data_lines: list[str] = []
    bytes_read = 0
    tail = ""
    keep = max(len(secret) - 1, 0)

    def decode(data: str) -> dict | None:
        nonlocal tail
        if data == "[DONE]":
            return None
        if secret and secret in (tail + data):
            raise ProviderError("generation_failed")
        if keep:
            tail = (tail + data)[-keep:]
        try:
            obj = json.loads(data)
        except (ValueError, RecursionError):
            raise ProviderError("generation_failed") from None
        if not isinstance(obj, dict):
            raise ProviderError("generation_failed")
        return obj

    async for chunk in chunks:
        bytes_read += len(chunk)
        if bytes_read > max_bytes:
            raise ProviderError("generation_failed")
        buffer += chunk.replace("\r\n", "\n")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line == "" and data_lines:
                obj = decode("\n".join(data_lines))
                data_lines = []
                if obj is None:
                    return
                yield obj
    if data_lines:
        obj = decode("\n".join(data_lines))
        if obj is not None:
            yield obj


class ChatHTTP:
    """Async streaming facade running on the application event loop.

    Unlike the synchronous listing facade, generation is consumed directly by an
    async FastAPI StreamingResponse, so client disconnects cancel the in-flight
    request. Endpoints are fixed; redirects are never followed; environment
    proxies are ignored. Test transports must implement httpx.AsyncBaseTransport.
    """

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        limits: ChatLimits | None = None,
    ):
        self.transport = transport
        self.limits = limits or ChatLimits()

    async def stream(
        self,
        provider: str,
        api_key: SecretStr,
        payload: dict,
        *,
        params: dict | None = None,
        model: str | None = None,
    ) -> AsyncIterator[dict]:
        secret = api_key.get_secret_value()
        if provider == "gemini":
            url = CHAT_ENDPOINTS["gemini"].format(model=quote(model or "", safe=""))
            headers = {"x-goog-api-key": secret}
        else:
            url = CHAT_ENDPOINTS[provider]
            headers = {"Authorization": f"Bearer {secret}"}
        headers.update(
            {
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            }
        )
        try:
            async with asyncio.timeout(self.limits.deadline_seconds):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=httpx.Timeout(
                        self.limits.read_timeout_seconds,
                        connect=self.limits.connect_timeout_seconds,
                    ),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "POST", url, headers=headers, json=payload, params=params
                    ) as response:
                        status = response.status_code
                        if status in (401, 403):
                            raise ProviderError("provider_authentication_failed")
                        if status == 429:
                            raise ProviderError("provider_rate_limited")
                        if status >= 500:
                            raise ProviderError("provider_unavailable")
                        if status != 200:  # Including redirects; never follow Location.
                            raise ProviderError("generation_failed")
                        if (
                            response.headers.get("content-encoding", "identity").lower()
                            != "identity"
                        ):
                            raise ProviderError("generation_failed")
                        declared = response.headers.get("content-length")
                        if declared is not None and (
                            not declared.isdecimal()
                            or int(declared) > self.limits.max_response_bytes
                        ):
                            raise ProviderError("generation_failed")
                        async for obj in _sse_events(
                            response.aiter_text(), secret, self.limits.max_response_bytes
                        ):
                            yield obj
        except (TimeoutError, httpx.TimeoutException):
            raise ProviderError("provider_timeout") from None
        except httpx.RequestError:
            raise ProviderError("provider_unavailable") from None