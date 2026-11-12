from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.providers import ProviderModel
from app.services.ai.base_provider import BaseProvider, ProviderError
from app.services.ai.http import ListingSession, ModelListingHTTP


class OpenAIModel(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1, max_length=512, pattern=r"^[!-~]+$")
    object: Literal["model"]
    created: int = Field(ge=0)
    owned_by: str = Field(max_length=1024)


class OpenAIListing(BaseModel):
    model_config = ConfigDict(strict=True)

    object: Literal["list"]
    data: Annotated[list[OpenAIModel], Field(max_length=5000)]


class OpenAIProvider(BaseProvider):
    # Endpoint key shared by OpenAI-compatible listings (e.g. Groq).
    provider_id = "openai"

    def __init__(self, http: ModelListingHTTP | None = None):
        self.http = http or ModelListingHTTP()

    def list_models(self, api_key: SecretStr) -> list[ProviderModel]:
        async def listing(session: ListingSession) -> list[ProviderModel]:
            payload = OpenAIListing.model_validate(await session.get(self.provider_id))
            if len(payload.data) > session.limits.max_models:
                raise ProviderError("invalid_provider_response")
            if len({model.id for model in payload.data}) != len(payload.data):
                raise ProviderError("invalid_provider_response")
            # /models provides no capability flags and proves no generation access.
            return [ProviderModel(id=model.id, display_name=model.id) for model in payload.data]

        return self.http.run(listing, api_key)
