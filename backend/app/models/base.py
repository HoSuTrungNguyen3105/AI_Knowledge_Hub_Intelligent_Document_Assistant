from datetime import UTC, datetime
from uuid import UUID, uuid4


def utcnow() -> datetime:
    return datetime.now(UTC)


class BaseDocument:
    @classmethod
    def generate_id(cls) -> UUID:
        return uuid4()

    @staticmethod
    def now() -> datetime:
        return utcnow()