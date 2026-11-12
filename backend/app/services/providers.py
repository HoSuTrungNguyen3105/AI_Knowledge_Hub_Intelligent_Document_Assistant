import asyncio
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import Settings
from app.core.credential_vault import CredentialVault
from app.models import UserProviderCredential
from app.models.base import utcnow
from app.repositories.providers import CredentialVersion, ProviderRepository
from app.schemas.providers import (
    ProviderCatalog,
    ProviderMetadata,
    ProviderModel,
    ProviderModels,
    ProviderPatch,
    ProviderTestResult,
)
from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ProviderError
from app.services.ai.http import ModelListingHTTP
from app.services.ai.registry import PROVIDERS, get_provider


class ProviderService:
    def __init__(
        self, db: AsyncIOMotorDatabase, settings: Settings, http: ModelListingHTTP | None = None
    ):
        self.db = db
        self.repo = ProviderRepository(db)
        self.vault = CredentialVault(settings.credential_encryption_key)
        self.http = http

    async def metadata(self, user_id: UUID, provider: str) -> ProviderMetadata:
        definition = get_provider(provider)
        result = ProviderMetadata(
            id=definition.id, name=definition.name, implemented=definition.implemented
        )
        credential = await self.repo.get(user_id, provider)
        if credential is not None:
            result.configured = True
            result.enabled = credential.enabled
            result.connection_status = credential.connection_status
            result.default_model = credential.default_model
            result.model_count = await self.repo.count_models(credential.id)
            result.last_checked_at = credential.last_checked_at
            result.models_synced_at = credential.models_synced_at
            result.last_error_code = credential.last_error_code
        return result

    async def catalog(self, user_id: UUID) -> ProviderCatalog:
        return ProviderCatalog(
            encryption_ready=self.vault.ready,
            providers=[await self.metadata(user_id, slug) for slug in PROVIDERS],
        )

    async def patch(self, user_id: UUID, provider: str, patch: ProviderPatch) -> ProviderMetadata:
        get_provider(provider, require_implemented=True)
        credential = await self.repo.get(user_id, provider)
        if credential is None and patch.api_key is None:
            raise ProviderError("credentials_missing")
        if patch.default_model is not None and (
            credential is None
            or not await self.repo.contains_model(credential.id, patch.default_model)
        ):
            raise ProviderError("invalid_default_model")
        values = {}
        if "enabled" in patch.model_fields_set:
            values["enabled"] = patch.enabled
        if "default_model" in patch.model_fields_set:
            values["default_model"] = patch.default_model
        if patch.api_key is not None:
            values.update(
                encrypted_api_key=self.vault.encrypt(patch.api_key, user_id, provider),
                default_model=None,
                connection_status="untested",
                last_checked_at=None,
                models_synced_at=None,
                last_error_code=None,
            )
        if credential is None:
            now = utcnow()
            try:
                await self.db.user_provider_credentials.insert_one(
                    {
                        "_id": UserProviderCredential.generate_id(),
                        "user_id": user_id,
                        "provider": provider,
                        "enabled": True,
                        "revision": 1,
                        "created_at": now,
                        "updated_at": now,
                        **values,
                    }
                )
            except DuplicateKeyError:
                # A concurrent initial save must not overwrite the winner's key.
                raise ProviderError("configuration_changed") from None
        else:
            try:
                await self.repo.compare_update(CredentialVersion.of(credential), values)
            except ProviderError:
                raise
            if patch.api_key is not None:
                await self.repo.clear_models(credential.id)
        return await self.metadata(user_id, provider)

    async def models(self, user_id: UUID, provider: str) -> ProviderModels:
        get_provider(provider)
        credential = await self.repo.get(user_id, provider)
        models = await self.repo.models(user_id, provider)
        return ProviderModels(
            provider=provider,
            models=[
                ProviderModel(
                    id=model.model_id,
                    display_name=model.display_name,
                    description=model.description,
                    capabilities=model.capabilities,
                    input_token_limit=model.input_token_limit,
                    output_token_limit=model.output_token_limit,
                    capability_source=model.capability_source,
                    input_price_per_token=model.input_price_per_token,
                    output_price_per_token=model.output_price_per_token,
                )
                for model in models
            ],
            synced_at=credential.models_synced_at if credential else None,
        )

    async def test(self, user_id: UUID, provider: str) -> ProviderTestResult:
        adapter = create_provider(provider, self.http)
        credential = await self.repo.get(user_id, provider)
        if credential is None:
            raise ProviderError("credentials_missing")
        version = CredentialVersion.of(credential)
        ciphertext = credential.encrypted_api_key
        default_model = credential.default_model
        # Release read transactions/connections before I/O
        try:
            key = self.vault.decrypt(ciphertext, user_id, provider)
            # The listing facade is synchronous and manages its own event loop;
            # run it off the application loop so pagination cannot block it.
            models = await asyncio.to_thread(adapter.list_models, key)
        except ProviderError as error:
            await self.repo.compare_update(
                version,
                {
                    "connection_status": "error",
                    "last_checked_at": utcnow(),
                    "last_error_code": error.code,
                },
            )
            raise
        now = utcnow()
        await self.repo.compare_update(
            version,
            {
                "connection_status": "connected",
                "last_checked_at": now,
                "models_synced_at": now,
                "last_error_code": None,
                "default_model": default_model
                if default_model in {m.id for m in models}
                else None,
            },
        )
        await self.repo.replace_models(version.id, models)
        return ProviderTestResult(
            provider=await self.metadata(user_id, provider), model_count=len(models)
        )

    async def delete(self, user_id: UUID, provider: str) -> None:
        get_provider(provider)
        await self.repo.delete(user_id, provider)