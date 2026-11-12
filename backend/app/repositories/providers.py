from dataclasses import dataclass
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import AIModel, UserProviderCredential
from app.schemas.providers import ProviderModel
from app.services.ai.base_provider import ProviderError


@dataclass(frozen=True)
class CredentialVersion:
    id: UUID
    user_id: UUID
    revision: int

    @classmethod
    def of(cls, credential: UserProviderCredential) -> "CredentialVersion":
        return cls(credential.id, credential.user_id, credential.revision)


class ProviderRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.credentials = db.user_provider_credentials
        self.ai_models = db.ai_models

    async def get(self, user_id: UUID, provider: str) -> UserProviderCredential | None:
        doc = await self.credentials.find_one(
            {"user_id": user_id, "provider": provider}
        )
        if doc:
            return UserProviderCredential(**doc)
        return None

    async def count_models(self, credential_id: UUID) -> int:
        return await self.ai_models.count_documents({"credential_id": credential_id})

    async def models(self, user_id: UUID, provider: str) -> list[AIModel]:
        credential = await self.credentials.find_one(
            {"user_id": user_id, "provider": provider}
        )
        if not credential:
            return []
        cursor = self.ai_models.find({"credential_id": credential["_id"]}).sort("model_id")
        return [AIModel(**doc) async for doc in cursor]

    async def contains_model(self, credential_id: UUID, model_id: str) -> bool:
        doc = await self.ai_models.find_one(
            {"credential_id": credential_id, "model_id": model_id}
        )
        return doc is not None

    async def get_model(self, credential_id: UUID, model_id: str) -> AIModel | None:
        doc = await self.ai_models.find_one(
            {"credential_id": credential_id, "model_id": model_id}
        )
        return AIModel(**doc) if doc else None

    async def compare_update(
        self, version: CredentialVersion, values: dict
    ) -> UserProviderCredential | None:
        values["revision"] = version.revision + 1
        values["updated_at"] = __import__("app.models.base", fromlist=["utcnow"]).utcnow()
        result = await self.credentials.find_one_and_update(
            {
                "_id": version.id,
                "user_id": version.user_id,
                "revision": version.revision,
            },
            {"$set": values},
            return_document=True,
        )
        if not result:
            raise ProviderError("configuration_changed")
        return UserProviderCredential(**result)

    async def clear_models(self, credential_id: UUID) -> None:
        await self.ai_models.delete_many({"credential_id": credential_id})

    async def replace_models(
        self, credential_id: UUID, models: list[ProviderModel]
    ) -> None:
        await self.clear_models(credential_id)
        if models:
            now = __import__("app.models.base", fromlist=["utcnow"]).utcnow()
            model_docs = [
                {
                    "_id": AIModel.generate_id(),
                    "credential_id": credential_id,
                    "model_id": model.id,
                    "display_name": model.display_name,
                    "description": model.description,
                    "capabilities": model.capabilities.model_dump(),
                    "input_token_limit": model.input_token_limit,
                    "output_token_limit": model.output_token_limit,
                    "capability_source": model.capability_source,
                    "created_at": now,
                }
                for model in models
            ]
            await self.ai_models.insert_many(model_docs)

    async def delete(self, user_id: UUID, provider: str) -> None:
        credential = await self.credentials.find_one(
            {"user_id": user_id, "provider": provider}
        )
        if credential:
            await self.ai_models.delete_many({"credential_id": credential["_id"]})
            await self.credentials.delete_one(
                {"user_id": user_id, "provider": provider}
            )