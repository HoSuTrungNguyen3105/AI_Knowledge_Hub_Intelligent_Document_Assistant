"""Credential binding schemas.

A binding maps one n8n credential TYPE (e.g. ``gmailOAuth2``) to one of
the user's own credentials in their n8n (by id). Template installs then
rewrite every node that references that type to the user's credential,
so a key connected once is applied everywhere — the bulk behaviour the
user asked for. Only ids and names live here; secret values never leave
n8n.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class N8nCredentialOut(BaseModel):
    id: str
    name: str = ""
    type: str


class CredentialBindingOut(BaseModel):
    cred_type: str
    n8n_credential_id: str
    n8n_credential_name: str = ""
    updated_at: datetime


class RequiredCredentialTypeOut(BaseModel):
    cred_type: str
    template_count: int = 0
    bound: bool = False


class CredentialBindingsOut(BaseModel):
    bindings: list[CredentialBindingOut] = Field(default_factory=list)
    n8n_credentials: list[N8nCredentialOut] = Field(default_factory=list)
    required_types: list[RequiredCredentialTypeOut] = Field(default_factory=list)
    # ProviderError code when the credential list could not be read from
    # n8n (not configured / unreachable / unauthorized); bindings and
    # required types are still returned in that case.
    n8n_error: str | None = None


class CredentialBindingSetIn(BaseModel):
    cred_type: str = Field(min_length=1, max_length=120)
    n8n_credential_id: str = Field(min_length=1, max_length=200)


class ApplyInstalledItemOut(BaseModel):
    install_id: str
    template_name: str = ""
    n8n_workflow_id: str = ""
    status: str  # updated | unchanged | failed
    bound_types: list[str] = Field(default_factory=list)
    error: str | None = None


class ApplyInstalledOut(BaseModel):
    results: list[ApplyInstalledItemOut] = Field(default_factory=list)
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
