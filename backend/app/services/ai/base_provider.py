from abc import ABC, abstractmethod

from pydantic import SecretStr

from app.schemas.providers import ProviderModel

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
    """Implemented surface: read-only model listing / connection testing only.

    Generation, streaming and tool execution are intentionally not implemented.
    Model metadata describes upstream capabilities, not adapter functionality.
    """

    @abstractmethod
    def list_models(self, api_key: SecretStr) -> list[ProviderModel]:
        """Return a validated catalog or raise a sanitized ProviderError."""
