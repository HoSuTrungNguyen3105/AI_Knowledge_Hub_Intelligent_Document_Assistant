from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

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
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: UUID, provider: str) -> UserProviderCredential | None:
        return self.db.scalar(
            select(UserProviderCredential)
            .where(
                UserProviderCredential.user_id == user_id,
                UserProviderCredential.provider == provider,
            )
            .execution_options(populate_existing=True)
        )

    def count_models(self, credential_id: UUID) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(AIModel)
                .where(AIModel.credential_id == credential_id)
            )
            or 0
        )

    def models(self, user_id: UUID, provider: str) -> list[AIModel]:
        return list(
            self.db.scalars(
                select(AIModel)
                .join(UserProviderCredential)
                .where(
                    UserProviderCredential.user_id == user_id,
                    UserProviderCredential.provider == provider,
                )
                .order_by(AIModel.model_id)
            )
        )

    def contains_model(self, credential_id: UUID, model_id: str) -> bool:
        return (
            self.db.scalar(
                select(AIModel.id).where(
                    AIModel.credential_id == credential_id, AIModel.model_id == model_id
                )
            )
            is not None
        )

    def compare_update(self, version: CredentialVersion, values: dict) -> None:
        # This short write transaction serializes cache mutation with key changes
        # and deletes. No transaction/row lock is held across the upstream HTTP call.
        result = self.db.execute(
            update(UserProviderCredential)
            .where(
                UserProviderCredential.id == version.id,
                UserProviderCredential.user_id == version.user_id,
                UserProviderCredential.revision == version.revision,
            )
            .values(**values, revision=version.revision + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise ProviderError("configuration_changed")

    def clear_models(self, credential_id: UUID) -> None:
        self.db.execute(delete(AIModel).where(AIModel.credential_id == credential_id))

    def replace_models(self, credential_id: UUID, models: list[ProviderModel]) -> None:
        self.clear_models(credential_id)
        self.db.add_all(
            [
                AIModel(
                    credential_id=credential_id,
                    model_id=model.id,
                    display_name=model.display_name,
                    description=model.description,
                    capabilities=model.capabilities.model_dump(),
                    input_token_limit=model.input_token_limit,
                    output_token_limit=model.output_token_limit,
                    capability_source=model.capability_source,
                )
                for model in models
            ]
        )

    def delete(self, user_id: UUID, provider: str) -> None:
        self.db.execute(
            delete(UserProviderCredential).where(
                UserProviderCredential.user_id == user_id,
                UserProviderCredential.provider == provider,
            )
        )
