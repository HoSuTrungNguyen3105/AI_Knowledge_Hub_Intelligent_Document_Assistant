import json
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.services.ai.base_provider import ProviderError


class CredentialVault:
    """Independent server key; ciphertext is authenticated and owner/provider-bound."""

    def __init__(self, key: SecretStr | None):
        self._fernet = None
        if key is not None:
            try:
                self._fernet = Fernet(key.get_secret_value().encode("ascii"))
            except (ValueError, UnicodeError):
                raise ProviderError("encryption_unavailable") from None

    @property
    def ready(self) -> bool:
        return self._fernet is not None

    def encrypt(self, api_key: SecretStr, user_id: UUID, provider: str) -> str:
        if self._fernet is None:
            raise ProviderError("encryption_unavailable")
        payload = json.dumps(
            {
                "version": 1,
                "user_id": str(user_id),
                "provider": provider,
                "api_key": api_key.get_secret_value(),
            }
        ).encode("utf-8")
        return self._fernet.encrypt(payload).decode("ascii")

    def decrypt(self, ciphertext: str, user_id: UUID, provider: str) -> SecretStr:
        if self._fernet is None:
            raise ProviderError("encryption_unavailable")
        try:
            payload = json.loads(self._fernet.decrypt(ciphertext.encode("ascii")))
            if (
                not isinstance(payload, dict)
                or payload.get("version") != 1
                or payload.get("user_id") != str(user_id)
                or payload.get("provider") != provider
                or not isinstance(payload.get("api_key"), str)
                or not 8 <= len(payload["api_key"]) <= 4096
                or any(not 33 <= ord(char) <= 126 for char in payload["api_key"])
            ):
                raise ValueError("Invalid credential binding")
            return SecretStr(payload["api_key"])
        except (InvalidToken, ValueError, TypeError, UnicodeError):
            raise ProviderError("encryption_unavailable") from None
