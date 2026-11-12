"""Create local secrets in backend/.env; preserve existing keys, never print values.

The backend reads backend/.env (see app/core/config.py). The template lives at the
project root (.env.example). Existing secrets are never overwritten or rotated.
"""
import base64
from pathlib import Path
import re
import secrets

ROOT = Path(__file__).resolve().parents[1]


def new_encryption_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def initialize_env(root: Path = ROOT) -> str:
    backend = root / "backend"
    destination = backend / ".env"
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        if re.search(r"^\s*CREDENTIAL_ENCRYPTION_KEY\s*=", existing, re.MULTILINE):
            return "backend/.env already has an encryption-key entry; all existing values left unchanged."
        with destination.open("a", encoding="utf-8", newline="\n") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(f"CREDENTIAL_ENCRYPTION_KEY={new_encryption_key()}\n")
        return "Added CREDENTIAL_ENCRYPTION_KEY to backend/.env. Existing secrets preserved. Restart backend."
    template = (root / ".env.example").read_text(encoding="utf-8")
    template = template.replace("CHANGE_ME_GENERATE_A_RANDOM_SECRET", secrets.token_hex(48))
    template = template.replace("CHANGE_ME_FERNET_ENCRYPTION_KEY", new_encryption_key())
    backend.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(template)
    return "Created backend/.env with random local secrets. Do not commit or share this file."


def main() -> None:
    print(initialize_env())


if __name__ == "__main__":
    main()