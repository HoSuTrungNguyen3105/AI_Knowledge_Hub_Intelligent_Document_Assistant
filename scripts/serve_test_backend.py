"""Offline in-memory MongoDB HTTP harness. NOT a production database.

Run with backend/.venv Python (needs dev deps: mongomock-motor) and
--allow-test-database. Data lives in memory and is lost when the process stops.
This exercises the real FastAPI stack without a MongoDB server or network access;
it is NOT evidence of real MongoDB/Atlas integration (see README for that).
"""
import argparse
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-test-database", action="store_true", required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "backend"))

    import bson
    import mongomock.collection as _mongomock_collection
    import uvicorn
    from bson.codec_options import CodecOptions
    from cryptography.fernet import Fernet
    from mongomock_motor import AsyncMongoMockClient

    from app.core.config import Settings
    from app.core.database import get_database, init_indexes
    from app.main import create_app

    # mongomock validates inserts with bson's DEFAULT codec, which rejects native
    # UUIDs. Production uses uuidRepresentation="standard"; align the validator.
    standard_codec = CodecOptions(uuid_representation=bson.binary.UuidRepresentation.STANDARD)
    real_encode = bson.BSON.encode

    class _StandardBSON:
        @staticmethod
        def encode(data, check_keys=False, codec_options=None):
            return real_encode(data, check_keys=check_keys, codec_options=standard_codec)

    _mongomock_collection.BSON = _StandardBSON

    settings = Settings(
        _env_file=None,
        jwt_secret=secrets.token_urlsafe(48),
        credential_encryption_key=Fernet.generate_key().decode(),
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="mindflow_ai_harness",
        cookie_secure=False,
        auth_rate_limit=1000,
        api_rate_limit=5000,
    )
    client = AsyncMongoMockClient(tz_aware=True)
    database = get_database(client, settings)
    application = create_app(settings)

    @asynccontextmanager
    async def offline_lifespan(_app):
        await init_indexes(database)
        _app.state.mongo_client = client
        yield

    application.router.lifespan_context = offline_lifespan

    print("TEST HARNESS: in-memory MongoDB only; data is disposable; NOT a real database.")
    try:
        uvicorn.run(application, host="127.0.0.1", port=args.port, proxy_headers=False)
    finally:
        client.close()


if __name__ == "__main__":
    main()