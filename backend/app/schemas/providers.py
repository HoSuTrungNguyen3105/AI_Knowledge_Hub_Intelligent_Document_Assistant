from datetime import datetime
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    field_validator,
    model_validator,
)


class ProviderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr | None = None
    enabled: StrictBool | None = None
    default_model: str | None = Field(default=None, min_length=1, max_length=512, strict=True)

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr | None) -> SecretStr:
        if value is None:
            raise ValueError("API key cannot be null")
        key = value.get_secret_value().strip()
        if not 8 <= len(key) <= 4096 or any(not 33 <= ord(char) <= 126 for char in key):
            raise ValueError("API key must be 8–4096 printable ASCII characters without whitespace")
        return SecretStr(key)

    @field_validator("enabled")
    @classmethod
    def validate_enabled(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("Enabled cannot be null")
        return value

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one configuration field is required")
        if self.api_key is not None and self.default_model is not None:
            raise ValueError("Sync the new key before selecting a default model")
        return self


class ModelCapabilities(BaseModel):
    chat: bool | None = None
    streaming: bool | None = None
    tools: bool | None = None
    embeddings: bool | None = None


class ProviderModel(BaseModel):
    id: str
    display_name: str
    description: str | None = None
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    capability_source: Literal["unknown", "provider_metadata"] = "unknown"
    # USD per token, only when the provider publishes pricing (Groq). Used for
    # ESTIMATED cost; never a provider-confirmed charge.
    input_price_per_token: float | None = None
    output_price_per_token: float | None = None


class ProviderMetadata(BaseModel):
    id: str
    name: str
    implemented: bool
    configured: bool = False
    enabled: bool = False
    connection_status: Literal["untested", "connected", "error"] = "untested"
    default_model: str | None = None
    model_count: int = 0
    last_checked_at: datetime | None = None
    models_synced_at: datetime | None = None
    last_error_code: str | None = None


class ProviderCatalog(BaseModel):
    encryption_ready: bool
    providers: list[ProviderMetadata]


class ProviderModels(BaseModel):
    provider: str
    models: list[ProviderModel]
    synced_at: datetime | None = None


class ProviderTestResult(BaseModel):
    provider: ProviderMetadata
    model_count: int
    scope: Literal["model_listing"] = "model_listing"
