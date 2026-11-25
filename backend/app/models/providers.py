from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import BaseDocument


class UserProviderCredential(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    provider: str
    encrypted_api_key: str
    enabled: bool = True
    default_model: str | None = None
    connection_status: str = "untested"
    last_checked_at: datetime | None = None
    models_synced_at: datetime | None = None
    last_error_code: str | None = None
    revision: int = 1
    created_at: datetime
    updated_at: datetime


class AIModel(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    credential_id: UUID
    model_id: str
    display_name: str
    description: str | None = None
    capabilities: dict[str, bool | None]
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    capability_source: str
    input_price_per_token: float | None = None
    output_price_per_token: float | None = None
    health_status: str | None = None
    health_error_code: str | None = None
    health_checked_at: datetime | None = None
    created_at: datetime