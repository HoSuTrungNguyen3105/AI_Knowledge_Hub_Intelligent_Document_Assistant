import asyncio
import time
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import Settings
from app.core.credential_vault import CredentialVault
from app.models import UserProviderCredential
from app.models.base import utcnow
from app.repositories.providers import CredentialVersion, ProviderRepository
from app.schemas.providers import (
    ModelCheckResult,
    ProviderCatalog,
    ProviderMetadata,
    ProviderModel,
    ProviderModels,
    ProviderPatch,
    ProviderTestResult,
)
from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.ai.chat_types import ChatRequest, ChatTurn
from app.services.ai.http import ModelListingHTTP
from app.services.ai.model_info import pricing_for
from app.services.ai.registry import PROVIDERS, get_provider


class ProviderService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        http: ModelListingHTTP | None = None,
        chat_http: ChatHTTP | None = None,
    ):
        self.db = db
        self.repo = ProviderRepository(db)
        self.vault = CredentialVault(settings.credential_encryption_key)
        self.http = http
        self.chat_http = chat_http

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
        result = []
        for model in models:
            item = ProviderModel(
                id=model.model_id,
                display_name=model.display_name,
                description=model.description,
                capabilities=model.capabilities,
                input_token_limit=model.input_token_limit,
                output_token_limit=model.output_token_limit,
                capability_source=model.capability_source,
                input_price_per_token=model.input_price_per_token,
                output_price_per_token=model.output_price_per_token,
                health_status=model.health_status,
                health_error_code=model.health_error_code,
                health_checked_at=model.health_checked_at,
            )
            item.pricing = pricing_for(provider, item)
            result.append(item)
        return ProviderModels(
            provider=provider,
            models=result,
            synced_at=credential.models_synced_at if credential else None,
        )

    async def check_model(
        self, user_id: UUID, provider: str, model_id: str
    ) -> ModelCheckResult:
        """One tiny real generation to learn whether a model truly answers.

        The listing test only proves the key can list models; this check
        sends a minimal "ping" generation and persists the outcome on
        the model record, so every picker can show whether the model
        actually works and, when not, the exact provider error code
        (e.g. provider_unavailable for an overloaded Gemini model).
        Always returns 200 with status ok/error for a synced model.
        """
        get_provider(provider, require_implemented=True)
        credential = await self.repo.get(user_id, provider)
        if credential is None:
            raise ProviderError("credentials_missing")
        if not credential.enabled:
            raise ProviderError("provider_disabled")
        model = await self.repo.get_model(credential.id, model_id)
        if model is None:
            raise ProviderError("model_not_synced")
        status = "ok"
        error_code: str | None = None
        started = time.monotonic()
        if model.capabilities.get("chat") is False:
            status, error_code = "error", "chat_not_supported"
        else:
            key = self.vault.decrypt(credential.encrypted_api_key, user_id, provider)
            adapter = create_provider(provider, chat_http=self.chat_http)
            request = ChatRequest(
                model=model_id,
                turns=(ChatTurn("user", "ping"),),
                max_output_tokens=16,
            )
            try:
                async for _event in adapter.stream_chat(key, request):
                    pass
            except ProviderError as error:
                status, error_code = "error", error.code
            except Exception:  # noqa: BLE001 - a check must report, not crash
                status, error_code = "error", "generation_failed"
        latency_ms = int((time.monotonic() - started) * 1000)
        checked_at = utcnow()
        await self.repo.set_model_health(
            credential.id,
            model_id,
            status=status,
            error_code=error_code,
            checked_at=checked_at,
        )
        return ModelCheckResult(
            provider=provider,
            model_id=model_id,
            status=status,
            error_code=error_code,
            latency_ms=latency_ms,
            checked_at=checked_at,
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