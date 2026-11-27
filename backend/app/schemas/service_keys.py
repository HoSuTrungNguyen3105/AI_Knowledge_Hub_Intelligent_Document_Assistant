"""Service key vault schemas.

A service key entry holds the credentials of one external service (for
example a Zalo OA app) encrypted at rest. The API never returns a stored
value — only which fields have one — so list/read responses are safe to
render anywhere.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ServiceKind = Literal["zalo_oa", "telegram_bot", "http_header"]


class ServiceKeyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    service: ServiceKind
    credential_name: str | None = Field(default=None, max_length=160)
    fields: dict[str, str] = Field(default_factory=dict)


class ServiceKeyUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    credential_name: str | None = Field(default=None, max_length=160)
    fields: dict[str, str] | None = None


class ServiceKeyFieldOut(BaseModel):
    key: str
    label: str
    secret: bool
    required: bool
    has_value: bool


class ServiceKeyOut(BaseModel):
    id: str
    name: str
    service: ServiceKind
    credential_name: str
    n8n_credential_type: str
    n8n_credential_id: str | None
    fields: list[ServiceKeyFieldOut]
    last_pushed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ServiceKeyListOut(BaseModel):
    items: list[ServiceKeyOut]
    total: int


class ServiceKeyPushOut(BaseModel):
    n8n_credential_id: str
    n8n_credential_name: str
    n8n_credential_type: str
    pushed_at: datetime


class ServiceFieldPresetOut(BaseModel):
    key: str
    label: str
    secret: bool
    required: bool
    hint: str = ""


class ServicePresetOut(BaseModel):
    service: ServiceKind
    label: str
    description: str
    n8n_credential_type: str
    fields: list[ServiceFieldPresetOut]


class ServicePresetListOut(BaseModel):
    items: list[ServicePresetOut]
