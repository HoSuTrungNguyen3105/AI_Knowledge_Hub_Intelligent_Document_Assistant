from collections.abc import AsyncIterator
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.providers import ProviderModel
from app.services.ai.base_provider import BaseProvider, ProviderError
from app.services.ai.chat import ChatHTTP, SecretRedactor
from app.services.ai.chat_types import ChatEvent, ChatRequest, token_count
from app.services.ai.http import ListingSession, ModelListingHTTP


class OpenAIPricing(BaseModel):
    model_config = ConfigDict(strict=True)

    # Groq publishes USD-per-token as strings; OpenAI omits pricing entirely.
    prompt: str | None = None
    completion: str | None = None


class OpenAIModel(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1, max_length=512, pattern=r"^[!-~]+$")
    object: Literal["model"]
    created: int = Field(ge=0)
    owned_by: str = Field(max_length=1024)
    # Optional: OpenAI omits this; Groq includes it (e.g. ["text"], ["speech"],
    # ["transcription"]). Used only to rule out non-chat models, never to assert
    # generation access.
    output_modalities: list[str] | None = None
    pricing: OpenAIPricing | None = None


class OpenAIListing(BaseModel):
    model_config = ConfigDict(strict=True)

    object: Literal["list"]
    data: Annotated[list[OpenAIModel], Field(max_length=5000)]


def _token_count(value: object) -> int | None:
    return token_count(value)


class OpenAIProvider(BaseProvider):
    # Endpoint key shared by OpenAI-compatible listings and chat (e.g. Groq).
    provider_id = "openai"

    def __init__(
        self,
        http: ModelListingHTTP | None = None,
        chat_http: ChatHTTP | None = None,
    ):
        self.http = http or ModelListingHTTP()
        self.chat_http = chat_http or ChatHTTP()

    def list_models(self, api_key: SecretStr) -> list[ProviderModel]:
        async def listing(session: ListingSession) -> list[ProviderModel]:
            payload = OpenAIListing.model_validate(await session.get(self.provider_id))
            if len(payload.data) > session.limits.max_models:
                raise ProviderError("invalid_provider_response")
            if len({model.id for model in payload.data}) != len(payload.data):
                raise ProviderError("invalid_provider_response")
            # /models proves no generation access; subclasses may rule out non-chat
            # models from listing metadata, but never assert chat=True from it.
            return [self._provider_model(model) for model in payload.data]

        return self.http.run(listing, api_key)

    def _provider_model(self, model: OpenAIModel) -> ProviderModel:
        return ProviderModel(id=model.id, display_name=model.id)

    @staticmethod
    def _messages(request: ChatRequest) -> list[dict]:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend({"role": turn.role, "content": turn.content} for turn in request.turns)
        return messages

    async def stream_chat(
        self, api_key: SecretStr, request: ChatRequest
    ) -> AsyncIterator[ChatEvent]:
        payload: dict = {
            "model": request.model,
            "messages": self._messages(request),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        redactor = SecretRedactor(api_key.get_secret_value())
        async for event in self.chat_http.stream(self.provider_id, api_key, payload):
            choices = event.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                delta = choices[0].get("delta")
                if isinstance(delta, dict):
                    text = delta.get("content")
                    if isinstance(text, str) and text:
                        redactor.feed(text)
                        yield ChatEvent("delta", text=text)
            usage = event.get("usage")
            if isinstance(usage, dict):
                yield ChatEvent(
                    "usage",
                    input_tokens=_token_count(usage.get("prompt_tokens")),
                    output_tokens=_token_count(usage.get("completion_tokens")),
                )