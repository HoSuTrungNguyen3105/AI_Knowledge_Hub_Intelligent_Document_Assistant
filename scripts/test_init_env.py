import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from init_env import initialize_env


def write_env(root: Path, content: str) -> Path:
    backend = root / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    destination = backend / ".env"
    destination.write_text(content, encoding="utf-8")
    return destination


class EnvironmentInitializationTests(unittest.TestCase):
    def test_adds_independent_key_without_replacing_existing_secrets(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = "JWT_SECRET=keep-original\nMONGODB_URI=mongodb://localhost:27017"
            destination = write_env(root, original)
            message = initialize_env(root)
            updated = destination.read_text(encoding="utf-8")
            self.assertTrue(updated.startswith(original + "\n"))
            key = updated.split("CREDENTIAL_ENCRYPTION_KEY=")[1].strip()
            self.assertEqual(len(base64.urlsafe_b64decode(key)), 32)
            self.assertNotIn(key, message)
            self.assertEqual(updated.count("CREDENTIAL_ENCRYPTION_KEY="), 1)

    def test_never_rotates_an_existing_encryption_key(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = "# local config\nCREDENTIAL_ENCRYPTION_KEY=existing-key\nJWT_SECRET=original\n"
            destination = write_env(root, original)
            initialize_env(root)
            self.assertEqual(destination.read_text(encoding="utf-8"), original)

    def test_new_config_replaces_all_secret_placeholders(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            template = (
                "MONGODB_URI=mongodb://localhost:27017\n"
                "MONGODB_DATABASE=mindflow_ai\n"
                "JWT_SECRET=CHANGE_ME_GENERATE_A_RANDOM_SECRET\n"
                "CREDENTIAL_ENCRYPTION_KEY=CHANGE_ME_FERNET_ENCRYPTION_KEY\n"
            )
            (root / ".env.example").write_text(template, encoding="utf-8")
            initialize_env(root)
            destination = root / "backend" / ".env"
            result = destination.read_text(encoding="utf-8")
            self.assertNotIn("CHANGE_ME", result)
            self.assertIn("CREDENTIAL_ENCRYPTION_KEY=", result)
            initialize_env(root)
            self.assertEqual(destination.read_text(encoding="utf-8"), result)


if __name__ == "__main__":
    unittest.main()