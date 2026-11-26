from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.providers import ProviderModel
from app.services.ai.base_provider import ProviderError
from app.services.ai.http import ListingSession
from app.services.ai.openai_provider import OpenAIProvider


class DeepSeekModel(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1, max_length=512, pattern=r"^[!-~]+$")
    object: Literal["model"]
    # DeepSeek's /models omits the `created` timestamp OpenAI returns, so
    # it (and owned_by) cannot be required here.
    owned_by: str | None = Field(default=None, max_length=1024)


class DeepSeekListing(BaseModel):
    model_config = ConfigDict(strict=True)

    object: Literal["list"]
    data: Annotated[list[DeepSeekModel], Field(max_length=5000)]


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek exposes an OpenAI-compatible API at api.deepseek.com.

    Chat reuses the OpenAI adapter unchanged (streaming, usage trailer via
    stream_options — DeepSeek accepts include_usage). Only the model
    listing differs: DeepSeek's /models payload has no `created` field,
    so the strict OpenAI listing schema would reject every sync; this
    subclass validates the same shape minus that field.
    """

    provider_id = "deepseek"

    def list_models(self, api_key: SecretStr) -> list[ProviderModel]:
        async def listing(session: ListingSession) -> list[ProviderModel]:
            payload = DeepSeekListing.model_validate(
                await session.get(self.provider_id)
            )
            if len(payload.data) > session.limits.max_models:
                raise ProviderError("invalid_provider_response")
            if len({model.id for model in payload.data}) != len(payload.data):
                raise ProviderError("invalid_provider_response")
            # /models proves no generation access; chat capability stays
            # unknown, exactly like the base OpenAI adapter.
            return [
                ProviderModel(id=model.id, display_name=model.id)
                for model in payload.data
            ]

        return self.http.run(listing, api_key)
