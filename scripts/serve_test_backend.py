"""Temporary SQLite HTTP harness. NOT a production database fallback.

Run with backend/.venv Python and --allow-test-database. Data is disposable.
Application Settings still requires PostgreSQL; only dependency injection uses SQLite.
"""
import argparse
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-test-database", action="store_true", required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "backend"))
    import uvicorn
    from cryptography.fernet import Fernet
    from app.core.config import Settings
    from app.core.database import build_engine, build_session_factory, get_db
    from app.main import create_app
    from app.models import Base

    with TemporaryDirectory(prefix="knowledge-hub-http-test-") as directory:
        engine = build_engine(f"sqlite+pysqlite:///{Path(directory) / 'test.sqlite'}")
        Base.metadata.create_all(engine)
        factory = build_session_factory(engine)
        app = create_app(Settings(
            _env_file=None,
            jwt_secret=secrets.token_urlsafe(48),
            credential_encryption_key=Fernet.generate_key().decode(),
            cookie_secure=False,
            auth_rate_limit=1000,
            api_rate_limit=5000,
        ))

        def test_db():
            with factory() as session:
                try:
                    yield session
                except Exception:
                    session.rollback()
                    raise

        app.dependency_overrides[get_db] = test_db
        print("TEST HARNESS: temporary SQLite only; data is disposable; NOT PostgreSQL verification.")
        try:
            uvicorn.run(app, host="127.0.0.1", port=args.port, proxy_headers=False)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
