import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from app.services.ai.base_provider import (
    ProviderError,
    classify_provider_error,
    describe_provider_error,
)
from app.services.ai.rate_limits import note_rate_limit

logger = logging.getLogger(__name__)

# Fixed official endpoints. Credentials never travel to a caller-supplied host.
CHAT_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "grok": "https://api.x.ai/v1/chat/completions",
    "ollama": "https://ollama.com/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent",
}


# Cap on a 4xx error body read for classification; real provider error
# objects are a few hundred bytes, and the cap bounds a hostile response.
_MAX_ERROR_BODY_BYTES = 8192


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
                        # Providers such as Groq report their real
                        # remaining quota only via x-ratelimit-*
                        # response headers; keep the newest snapshot
                        # for display. Providers without such headers
                        # simply never produce one.
                        note_rate_limit(
                            provider, payload.get("model") or model, response.headers
                        )
                        if status in (401, 403):
                            raise ProviderError("provider_authentication_failed")
                        if status == 429:
                            raise ProviderError("provider_rate_limited")
                        if status >= 500:
                            raise ProviderError("provider_unavailable")
                        if status != 200:  # Including redirects; never follow Location.
                            if 400 <= status < 500:
                                # A client-error rejection carries a structured
                                # provider error body; classify it into a fixed
                                # public code instead of masking it as a generic
                                # generation failure. The upstream reason is
                                # logged (secret-redacted) server-side only:
                                # without it, a generic rejection code is
                                # undiagnosable — the Ollama rejection that
                                # survived for weeks hid exactly here.
                                code, summary = await self._rejection_details(
                                    response
                                )
                                logger.warning(
                                    "provider request rejected: provider=%s "
                                    "model=%s status=%s code=%s upstream=%s",
                                    provider,
                                    payload.get("model"),
                                    status,
                                    code,
                                    summary.replace(secret, "***")
                                    if secret
                                    else summary,
                                )
                                raise ProviderError(code)
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

    @staticmethod
    async def _rejection_details(response: httpx.Response) -> tuple[str, str]:
        """Classify a 4xx rejection from its bounded provider error body.

        At most ``_MAX_ERROR_BODY_BYTES`` are read. Only the fixed code from
        :func:`classify_provider_error` crosses the API boundary; the short
        error summary (code/type/message fields only) is returned solely so
        the caller can log it server-side with the credential redacted —
        it is never stored on a record or raised to the client.
        """
        raw = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                raw.extend(chunk[: _MAX_ERROR_BODY_BYTES - len(raw)])
                if len(raw) >= _MAX_ERROR_BODY_BYTES:
                    break
        except (httpx.HTTPError, RuntimeError):
            return "provider_request_rejected", ""
        try:
            payload = json.loads(bytes(raw))
        except (ValueError, RecursionError):
            return "provider_request_rejected", ""
        if isinstance(payload, dict):
            error = payload.get("error")
            return classify_provider_error(error), describe_provider_error(error)
        return "provider_request_rejected", ""