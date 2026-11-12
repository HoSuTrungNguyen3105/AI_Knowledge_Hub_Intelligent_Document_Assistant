from collections.abc import AsyncIterator
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.providers import ModelCapabilities, ProviderModel
from app.services.ai.base_provider import BaseProvider, ProviderError
from app.services.ai.chat import ChatHTTP, SecretRedactor
from app.services.ai.chat_types import ChatEvent, ChatRequest, token_count
from app.services.ai.http import ListingSession, ModelListingHTTP


class GeminiModel(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=8, max_length=519, pattern=r"^models/[!-~]+$")
    displayName: str | None = Field(default=None, max_length=1024)
    description: str | None = Field(default=None, max_length=32768)
    supportedGenerationMethods: list[Annotated[str, Field(max_length=128)]] | None = Field(
        default=None, max_length=100
    )
    inputTokenLimit: int | None = Field(default=None, ge=0, le=2**31 - 1)
    outputTokenLimit: int | None = Field(default=None, ge=0, le=2**31 - 1)


class GeminiListing(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    # Google omits repeated fields when empty.
    models: list[GeminiModel] = Field(default_factory=list, max_length=1000)
    nextPageToken: str | None = Field(default=None, max_length=4096)


class GeminiProvider(BaseProvider):
    def __init__(
        self,
        http: ModelListingHTTP | None = None,
        chat_http: ChatHTTP | None = None,
    ):
        self.http = http or ModelListingHTTP()
        self.chat_http = chat_http or ChatHTTP()

    def list_models(self, api_key: SecretStr) -> list[ProviderModel]:
        async def listing(session: ListingSession) -> list[ProviderModel]:
            models: list[ProviderModel] = []
            seen_ids: set[str] = set()
            seen_tokens: set[str] = set()
            token = None
            for _ in range(session.limits.max_pages):
                params = {"pageSize": 1000}
                if token:
                    params["pageToken"] = token
                payload = GeminiListing.model_validate(await session.get("gemini", params))
                for model in payload.models:
                    model_id = model.name.removeprefix("models/")
                    if model_id in seen_ids or len(models) >= session.limits.max_models:
                        raise ProviderError("invalid_provider_response")
                    seen_ids.add(model_id)
                    methods = model.supportedGenerationMethods
                    capabilities = ModelCapabilities()
                    if methods is not None:
                        capabilities.chat = bool(
                            {"generateContent", "generateMessage"} & set(methods)
                        )
                        capabilities.embeddings = bool(
                            {"embedContent", "batchEmbedContents"} & set(methods)
                        )
                        # Absence of stream methods is not evidence of no streaming.
                        if {"streamGenerateContent", "streamGenerateMessage"} & set(methods):
                            capabilities.streaming = True
                    models.append(
                        ProviderModel(
                            id=model_id,
                            display_name=model.displayName or model_id,
                            description=model.description,
                            capabilities=capabilities,
                            input_token_limit=model.inputTokenLimit,
                            output_token_limit=model.outputTokenLimit,
                            capability_source="provider_metadata",
                        )
                    )
                token = payload.nextPageToken
                if not token:
                    return models
                if token in seen_tokens:
                    raise ProviderError("invalid_provider_response")
                seen_tokens.add(token)
            raise ProviderError("invalid_provider_response")

        return self.http.run(listing, api_key)

    async def stream_chat(
        self, api_key: SecretStr, request: ChatRequest
    ) -> AsyncIterator[ChatEvent]:
        contents = [
            {
                "role": "user" if turn.role == "user" else "model",
                "parts": [{"text": turn.content}],
            }
            for turn in request.turns
        ]
        payload: dict = {"contents": contents}
        if request.system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}
        generation: dict = {}
        if request.temperature is not None:
            generation["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            generation["maxOutputTokens"] = request.max_output_tokens
        if generation:
            payload["generationConfig"] = generation
        redactor = SecretRedactor(api_key.get_secret_value())
        async for event in self.chat_http.stream(
            "gemini", api_key, payload, params={"alt": "sse"}, model=request.model
        ):
            candidates = event.get("candidates")
            if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
                content = candidates[0].get("content")
                if isinstance(content, dict):
                    parts = content.get("parts")
                    if isinstance(parts, list):
                        for part in parts:
                            if isinstance(part, dict):
                                text = part.get("text")
                                if isinstance(text, str) and text:
                                    redactor.feed(text)
                                    yield ChatEvent("delta", text=text)
            usage = event.get("usageMetadata")
            if isinstance(usage, dict):
                yield ChatEvent(
                    "usage",
                    input_tokens=token_count(usage.get("promptTokenCount")),
                    output_tokens=token_count(usage.get("candidatesTokenCount")),
                )
