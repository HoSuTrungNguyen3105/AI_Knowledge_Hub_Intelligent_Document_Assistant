from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import SecretStr

from app.schemas.providers import ProviderModel
from app.services.ai.chat_types import ChatEvent, ChatRequest

# Only fixed, public messages may cross the API boundary. Never include upstream text.
ERRORS = {
    "provider_not_found": (404, "Unknown provider."),
    "provider_not_implemented": (409, "This provider is not integrated yet."),
    "credentials_missing": (409, "Save an API key before using this provider."),
    "encryption_unavailable": (
        503,
        "Credential encryption is unavailable or the key cannot be read.",
    ),
    "provider_authentication_failed": (400, "The provider rejected the saved API key."),
    "provider_rate_limited": (429, "The provider rate limit was reached. Try again later."),
    "provider_timeout": (504, "The provider connection timed out."),
    "provider_unavailable": (502, "The provider is unavailable. Try again later."),
    "invalid_provider_response": (502, "The provider returned an invalid model listing."),
    "configuration_changed": (409, "Provider configuration changed. Reload and try again."),
    "invalid_default_model": (409, "Select a model from this provider's current synced catalog."),
    "invalid_provider_configuration": (422, "Invalid provider configuration."),
    "model_not_chat_capable": (409, "This model does not support chat generation."),
    "model_not_synced": (409, "Sync this provider's models before starting a chat."),
    "provider_disabled": (409, "This provider is disabled. Enable it in Settings."),
    "conversation_not_found": (404, "Conversation not found."),
    "empty_message": (422, "Message content cannot be empty."),
    "generation_failed": (502, "The provider returned an invalid generation response."),
}


class ProviderError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.status_code, self.message = ERRORS[code]
        super().__init__(self.message)

    @property
    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class BaseProvider(ABC):
    """Implemented surface: read-only model listing and chat generation/streaming.

    Tool execution is intentionally not implemented. Model metadata describes
    upstream capabilities, not adapter functionality. Generation never exposes
    upstream text or credentials in errors; only fixed public messages cross the
    API boundary.
    """

    @abstractmethod
    def list_models(self, api_key: SecretStr) -> list[ProviderModel]:
        """Return a validated catalog or raise a sanitized ProviderError."""

    @abstractmethod
    def stream_chat(
        self, api_key: SecretStr, request: ChatRequest
    ) -> AsyncIterator[ChatEvent]:
        """Yield sanitized generation events or raise a sanitized ProviderError."""
