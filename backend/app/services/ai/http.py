import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import SecretStr, ValidationError

from app.services.ai.base_provider import ProviderError

T = TypeVar("T")
# Endpoints are not caller-configurable. Credentials never travel to another host.
ENDPOINTS = {
    "openai": "https://api.openai.com/v1/models",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "groq": "https://api.groq.com/openai/v1/models",
    "ollama": "https://ollama.com/v1/models",
}


@dataclass(frozen=True)
class HTTPLimits:
    deadline_seconds: float = 30.0
    timeout_seconds: float = 8.0
    max_pages: int = 20
    max_models: int = 5000
    max_response_bytes: int = 4 * 1024 * 1024  # Total across all pages.


class ModelListingHTTP:
    """Synchronous service facade over cancellable I/O with a whole-sync deadline.

    Per-operation httpx timeouts alone cannot bound pagination or a trickling body.
    asyncio.timeout covers connection, headers, all pages and streaming body reads.
    Run from synchronous API/service threads, never from the application event loop.
    Test transports must implement AsyncBaseTransport (httpx.MockTransport does).
    """

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        limits: HTTPLimits | None = None,
    ):
        self.transport = transport
        self.limits = limits or HTTPLimits()

    def run(self, operation: Callable[["ListingSession"], Awaitable[T]], api_key: SecretStr) -> T:
        async def execute() -> T:
            async with asyncio.timeout(self.limits.deadline_seconds):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=httpx.Timeout(self.limits.timeout_seconds),
                    follow_redirects=False,
                    trust_env=False,
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                ) as client:
                    return await operation(ListingSession(client, api_key, self.limits))

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(execute())
        except (TimeoutError, httpx.TimeoutException):
            raise ProviderError("provider_timeout") from None
        except httpx.RequestError:
            raise ProviderError("provider_unavailable") from None
        except (ValidationError, ValueError, UnicodeError, RecursionError):
            raise ProviderError("invalid_provider_response") from None
        finally:
            async def close_streams():
                async with asyncio.timeout(1):
                    await loop.shutdown_asyncgens()

            try:
                loop.run_until_complete(close_streams())
            except TimeoutError:
                pass
            finally:
                # Unlike asyncio.run(), close does not wait for an uncancellable
                # OS DNS lookup after the deadline. Late results are discarded.
                loop.close()


class ListingSession:
    def __init__(self, client: httpx.AsyncClient, api_key: SecretStr, limits: HTTPLimits):
        self.client = client
        self.api_key = api_key
        self.limits = limits
        self.bytes_read = 0

    async def get(self, provider: str, params: dict | None = None) -> dict:
        secret = self.api_key.get_secret_value()
        headers = (
            {"x-goog-api-key": secret}
            if provider == "gemini"
            else {"Authorization": f"Bearer {secret}"}
        )
        async with self.client.stream(
            "GET", ENDPOINTS[provider], headers=headers, params=params
        ) as response:
            status = response.status_code
            if status in (401, 403):
                raise ProviderError("provider_authentication_failed")
            if status == 429:
                raise ProviderError("provider_rate_limited")
            if status >= 500:
                raise ProviderError("provider_unavailable")
            if status != 200:  # Including all redirects; never follow Location.
                raise ProviderError("invalid_provider_response")
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                # Avoid decompression bombs. Both official endpoints support identity.
                raise ProviderError("invalid_provider_response")
            declared = response.headers.get("content-length")
            if declared is not None and (
                not declared.isdecimal()
                or int(declared) > self.limits.max_response_bytes - self.bytes_read
            ):
                raise ProviderError("invalid_provider_response")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                self.bytes_read += len(chunk)
                if self.bytes_read > self.limits.max_response_bytes:
                    raise ProviderError("invalid_provider_response")
                body.extend(chunk)
            payload = json.loads(body)
            if not isinstance(payload, dict) or "error" in payload:
                raise ProviderError("invalid_provider_response")
            # Even nominal metadata is untrusted: reject any echoed credential,
            # including JSON-escaped keys, descriptions and pagination tokens.
            pending = [payload]
            while pending:
                value = pending.pop()
                if isinstance(value, str) and secret in value:
                    raise ProviderError("invalid_provider_response")
                if isinstance(value, dict):
                    pending.extend(value.keys())
                    pending.extend(value.values())
                elif isinstance(value, list):
                    pending.extend(value)
            return payload
