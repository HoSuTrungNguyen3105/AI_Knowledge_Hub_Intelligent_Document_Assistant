"""Deterministic concurrent DB/HTTP contract mocks for MongoDB backend."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.core.credential_vault import CredentialVault
from app.models import AIModel, User, UserProviderCredential
from app.repositories.providers import ProviderRepository
from app.schemas.providers import ProviderPatch
from app.services.ai.base_provider import ProviderError
from app.services.ai.http import ModelListingHTTP
from app.services.providers import ProviderService


@pytest.fixture
def configured_user(client, register, db, settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    register(client)
    user_doc = await db.users.find_one({})
    user_id = user_doc["_id"]
    await ProviderService(db, settings).patch(
        user_id, "openai", ProviderPatch(api_key="original-test-key")
    )
    return user_id


@pytest.mark.parametrize("mutation", ["replace", "delete", "recreate", "disable", "newer_sync"])
@pytest.mark.parametrize("failure", [False, True])
def test_stale_sync_never_overwrites_or_resurrects_configuration(
    configured_user,
    db,
    settings,
    mutation,
    failure,
):
    started, release = Event(), Event()

    def handle(_request):
        started.set()
        assert release.wait(5), "Test failed to release the mocked upstream"
        return (
            httpx.Response(401, text="upstream test-key echo")
            if failure
            else httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "stale-contract-model",
                            "object": "model",
                            "created": 1,
                            "owned_by": "fixture",
                        }
                    ],
                },
            )
        )

    def sync():
        http = ModelListingHTTP(transport=httpx.MockTransport(handle))
        return ProviderService(db, settings, http).test(configured_user, "openai")

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(sync)
        try:
            assert started.wait(5), "Sync never reached the mock transport"
            service = ProviderService(db, settings)
            if mutation in {"delete", "recreate"}:
                service.delete(configured_user, "openai")
            if mutation in {"replace", "recreate"}:
                service.patch(
                    configured_user, "openai", ProviderPatch(api_key="replacement-test-key")
                )
            elif mutation == "disable":
                service.patch(configured_user, "openai", ProviderPatch(enabled=False))
            elif mutation == "newer_sync":
                http = ModelListingHTTP(
                    transport=httpx.MockTransport(
                        lambda _: httpx.Response(200, json={"object": "list", "data": []})
                    )
                )
                ProviderService(db, settings, http).test(configured_user, "openai")
        finally:
            release.set()
        with pytest.raises(ProviderError) as error:
            pending.result(timeout=5)
        assert error.value.code == "configuration_changed"

    credential = await db.user_provider_credentials.find_one({})
    assert await db.ai_models.count_documents({}) == 0
    if mutation == "delete":
        assert credential is None
    else:
        assert credential["last_error_code"] is None
        if mutation == "newer_sync":
            assert credential["connection_status"] == "connected"
            assert credential["models_synced_at"] is not None
        else:
            assert credential["connection_status"] == "untested"
            assert credential["models_synced_at"] is None
        if mutation == "disable":
            assert not credential["enabled"]
        if mutation in {"replace", "recreate"}:
            assert (
                CredentialVault(settings.credential_encryption_key)
                .decrypt(credential["encrypted_api_key"], configured_user, "openai")
                .get_secret_value()
                == "replacement-test-key"
            )


def test_concurrent_initial_configuration_has_one_winner(
    client,
    register,
    db,
    settings,
    monkeypatch,
):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    register(client)
    user_doc = await db.users.find_one({})
    user_id = user_doc["_id"]
    barrier = Barrier(2)
    original = ProviderRepository.get

    async def simultaneous_read(repository, owner, provider):
        result = await original(repository, owner, provider)
        if result is None:
            barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(ProviderRepository, "get", simultaneous_read)

    def configure(key):
        try:
            ProviderService(db, settings).patch(
                user_id, "openai", ProviderPatch(api_key=key)
            )
            return key
        except ProviderError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(configure, ["first-contract-key", "second-contract-key"]))
    assert results.count("configuration_changed") == 1
    winner = next(result for result in results if result != "configuration_changed")
    credential = await db.user_provider_credentials.find_one({})
    assert credential is not None
    assert credential["revision"] == 1
    assert (
        CredentialVault(settings.credential_encryption_key)
        .decrypt(credential["encrypted_api_key"], user_id, "openai")
        .get_secret_value()
        == winner
    )