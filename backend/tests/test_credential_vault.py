"""Credential unit tests; all keys are generated test fixtures, never real credentials."""

from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.credential_vault import CredentialVault
from app.services.ai.base_provider import ProviderError


@pytest.fixture
def vault():
    return CredentialVault(SecretStr(Fernet.generate_key().decode()))


def test_vault_randomized_round_trip_nonplaintext_and_binding(vault):
    user_id = uuid4()
    secret = SecretStr("fixture-provider-key-only")
    ciphertext = vault.encrypt(secret, user_id, "openai")
    assert vault.ready
    assert secret.get_secret_value() not in ciphertext
    assert ciphertext != vault.encrypt(secret, user_id, "openai")
    assert vault.decrypt(ciphertext, user_id, "openai") == secret
    for owner, provider in [(uuid4(), "openai"), (user_id, "gemini")]:
        with pytest.raises(ProviderError) as error:
            vault.decrypt(ciphertext, owner, provider)
        assert error.value.code == "encryption_unavailable"
        assert ciphertext not in str(error.value)
        assert secret.get_secret_value() not in str(error.value)


def test_vault_missing_key_has_no_jwt_fallback():
    vault = CredentialVault(None)
    assert not vault.ready
    with pytest.raises(ProviderError, match="encryption"):
        vault.encrypt(SecretStr("fixture-key"), uuid4(), "openai")
    with pytest.raises(ProviderError, match="encryption"):
        vault.decrypt("unreadable-ciphertext", uuid4(), "openai")


def test_vault_wrong_server_key_and_corruption_are_safe(vault):
    user_id = uuid4()
    ciphertext = vault.encrypt(SecretStr("fixture-key"), user_id, "openai")
    other = CredentialVault(SecretStr(Fernet.generate_key().decode()))
    for target, value in [(other, ciphertext), (vault, "invalid"), (vault, "non-ascii-\u2603")]:
        with pytest.raises(ProviderError) as error:
            target.decrypt(value, user_id, "openai")
        assert error.value.code == "encryption_unavailable"


@pytest.mark.parametrize("value", ["not-fernet", "x" * 44, "\u2603" * 44])
def test_settings_validate_configured_encryption_key(settings, value):
    with pytest.raises(ValidationError, match="CREDENTIAL_ENCRYPTION_KEY"):
        Settings(_env_file=None, **(settings.model_dump() | {"credential_encryption_key": value}))


@pytest.mark.parametrize("value", [None, ""])
def test_settings_allow_absent_encryption_key(settings, value):
    result = Settings(
        _env_file=None, **(settings.model_dump() | {"credential_encryption_key": value})
    )
    assert result.credential_encryption_key is None
