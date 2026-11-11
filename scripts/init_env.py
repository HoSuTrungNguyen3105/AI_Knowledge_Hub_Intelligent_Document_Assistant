"""Create local secrets without printing them or overwriting existing config."""
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    destination = ROOT / ".env"
    if destination.exists():
        print(".env already exists; left unchanged.")
        return
    template = (ROOT / ".env.example").read_text(encoding="utf-8")
    template = template.replace("CHANGE_ME_DATABASE_PASSWORD", secrets.token_hex(24))
    template = template.replace("CHANGE_ME_GENERATE_A_RANDOM_SECRET", secrets.token_hex(48))
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(template)
    print("Created .env with random local secrets. Do not commit or share this file.")


if __name__ == "__main__":
    main()
