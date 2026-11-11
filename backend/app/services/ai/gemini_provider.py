from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.providers import ModelCapabilities, ProviderModel
from app.services.ai.base_provider import BaseProvider, ProviderError
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
    def __init__(self, http: ModelListingHTTP | None = None):
        self.http = http or ModelListingHTTP()

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
