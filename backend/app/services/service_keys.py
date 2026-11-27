"""Service key vault: encrypted external-service credentials that the
user can push into their own n8n as credentials with one click.

Storage mirrors the AI provider vault: every field value is encrypted
with :class:`CredentialVault`, bound to (user, entry, field) so a
ciphertext cannot be replayed into another entry. Reads never decrypt —
they only report which fields have a value. Decryption happens exactly
once per push, server-side, and the plaintext goes only to the user's
own n8n over the configured API channel.

Push mapping (wave 1, token-style credentials only):
- ``zalo_oa``      -> n8n ``httpHeaderAuth`` carrying the OA access token
  (header ``access_token``), which is what Zalo OA API calls expect.
- ``telegram_bot`` -> n8n ``telegramApi`` with the bot token.
- ``http_header``  -> n8n ``httpHeaderAuth`` with a user-chosen header.

OAuth-style credentials cannot be created through the n8n API and stay
out of scope on purpose.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import SecretStr

from app.core.config import Settings
from app.core.credential_vault import CredentialVault
from app.schemas.service_keys import (
    ServiceFieldPresetOut,
    ServiceKeyOut,
    ServiceKeyFieldOut,
    ServiceKeyPushOut,
    ServicePresetOut,
)
from app.services.ai.base_provider import ProviderError
from app.services.n8n_platform import N8nApiHTTP

COLLECTION = "service_keys"

# Field presets are the single source of truth for the API and the UI
# (the frontend renders its forms from GET /presets).
PRESETS: dict[str, ServicePresetOut] = {
    "zalo_oa": ServicePresetOut(
        service="zalo_oa",
        label="Zalo Official Account",
        description=(
            "App ID + Secret Key lấy ở developers.zalo.me; Access Token và "
            "Refresh Token lấy lần đầu bằng công cụ API Explorer. Token đẩy "
            "sang n8n là Access Token (sống 25 giờ) — vòng refresh tự động "
            "là đợt nâng cấp riêng."
        ),
        n8n_credential_type="httpHeaderAuth",
        fields=[
            ServiceFieldPresetOut(key="app_id", label="App ID", secret=False, required=True),
            ServiceFieldPresetOut(key="secret_key", label="Secret Key", secret=True, required=True),
            ServiceFieldPresetOut(key="access_token", label="Access Token", secret=True, required=False),
            ServiceFieldPresetOut(key="refresh_token", label="Refresh Token", secret=True, required=False),
        ],
    ),
    "telegram_bot": ServicePresetOut(
        service="telegram_bot",
        label="Telegram Bot",
        description="Bot token do @BotFather cấp. Đẩy sang n8n thành credential Telegram để dùng trong node Telegram.",
        n8n_credential_type="telegramApi",
        fields=[
            ServiceFieldPresetOut(key="bot_token", label="Bot Token", secret=True, required=True),
        ],
    ),
    "http_header": ServicePresetOut(
        service="http_header",
        label="HTTP Header (tự do)",
        description="Một header chứa key bất kỳ (ví dụ Authorization, X-Api-Key) để dùng trong node HTTP Request của n8n.",
        n8n_credential_type="httpHeaderAuth",
        fields=[
            ServiceFieldPresetOut(key="header_name", label="Tên header", secret=False, required=True, hint="Ví dụ: Authorization"),
            ServiceFieldPresetOut(key="header_value", label="Giá trị header", secret=True, required=True, hint="Ví dụ: Bearer <token> — không dùng khoảng trắng đầu/cuối"),
        ],
    ),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _binding(entry_id: str, field_key: str) -> str:
    return f"service-keys:{entry_id}:{field_key}"


class ServiceKeysService:
    def __init__(self, db: AsyncIOMotorDatabase, settings: Settings, http: N8nApiHTTP):
        self.db = db
        self.settings = settings
        self.http = http
        self.vault = CredentialVault(settings.credential_encryption_key)

    @property
    def entries(self):
        return self.db[COLLECTION]

    # -- n8n connection helpers (mirror N8nPlatformService) ----------------
    @property
    def _n8n_base_url(self) -> str:
        return (self.settings.n8n_api_base_url or self.settings.n8n_webhook_base_url).rstrip("/")

    @property
    def _n8n_api_key(self) -> str:
        key = self.settings.n8n_api_key
        return key.get_secret_value() if key is not None else ""

    def _require_n8n_key(self) -> str:
        key = self._n8n_api_key
        if not key:
            raise ProviderError("n8n_api_not_configured")
        return key

    # -- validation ---------------------------------------------------------
    @staticmethod
    def _validate_values(service: str, values: dict[str, str], *, partial: bool) -> None:
        preset = PRESETS[service]
        known = {field.key for field in preset.fields}
        for key in values:
            if key not in known:
                raise ProviderError("service_key_invalid")
        for field in preset.fields:
            value = values.get(field.key)
            if not partial and field.required and not value:
                raise ProviderError("service_key_invalid")
            if value:
                # The vault only stores printable ASCII of 8..4096 chars;
                # reject here with the vault's public error instead of
                # leaking the encryption error code to the caller.
                if not 8 <= len(value) <= 4096 or any(
                    not 33 <= ord(char) <= 126 for char in value
                ):
                    raise ProviderError("service_key_invalid")

    # -- CRUD ---------------------------------------------------------------
    async def create(self, user_id: UUID, payload) -> ServiceKeyOut:
        self._validate_values(payload.service, payload.fields, partial=False)
        entry_id = str(uuid4())
        encrypted = {
            key: self.vault.encrypt(SecretStr(value), user_id, _binding(entry_id, key))
            for key, value in payload.fields.items()
            if value
        }
        now = _utcnow()
        doc = {
            "_id": entry_id,
            "user_id": str(user_id),
            "name": payload.name.strip(),
            "service": payload.service,
            "credential_name": (payload.credential_name or f"MindFlow — {payload.name.strip()}")[:160],
            "fields": encrypted,
            "n8n_credential_id": None,
            "last_pushed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.entries.insert_one(doc)
        return self._out(doc)

    async def list(self, user_id: UUID) -> list[ServiceKeyOut]:
        docs = (
            await self.entries.find({"user_id": str(user_id)})
            .sort("created_at", 1)
            .to_list(length=200)
        )
        return [self._out(doc) for doc in docs]

    async def _get_doc(self, user_id: UUID, entry_id: str) -> dict:
        doc = await self.entries.find_one({"_id": entry_id, "user_id": str(user_id)})
        if doc is None:
            raise ProviderError("service_key_not_found")
        return doc

    async def update(self, user_id: UUID, entry_id: str, payload) -> ServiceKeyOut:
        doc = await self._get_doc(user_id, entry_id)
        changes: dict = {"updated_at": _utcnow()}
        if payload.name is not None:
            changes["name"] = payload.name.strip()
        if payload.credential_name is not None:
            changes["credential_name"] = payload.credential_name[:160]
        if payload.fields is not None:
            self._validate_values(doc["service"], payload.fields, partial=True)
            fields = dict(doc.get("fields") or {})
            for key, value in payload.fields.items():
                if value:
                    fields[key] = self.vault.encrypt(
                        SecretStr(value), user_id, _binding(entry_id, key)
                    )
                else:
                    fields.pop(key, None)
            changes["fields"] = fields
        await self.entries.update_one({"_id": entry_id}, {"$set": changes})
        return self._out({**doc, **changes})

    async def delete(self, user_id: UUID, entry_id: str) -> None:
        result = await self.entries.delete_one(
            {"_id": entry_id, "user_id": str(user_id)}
        )
        if result.deleted_count == 0:
            raise ProviderError("service_key_not_found")

    # -- push to n8n ----------------------------------------------------------
    def _credential_payload(self, user_id: UUID, doc: dict) -> tuple[str, dict]:
        preset = PRESETS[doc["service"]]
        stored = doc.get("fields") or {}

        def value_of(key: str) -> str:
            ciphertext = stored.get(key)
            if not ciphertext:
                raise ProviderError("service_key_invalid")
            return self.vault.decrypt(
                ciphertext, user_id, _binding(doc["_id"], key)
            ).get_secret_value()

        if doc["service"] == "zalo_oa":
            data = {"name": "access_token", "value": value_of("access_token")}
        elif doc["service"] == "telegram_bot":
            data = {"accessToken": value_of("bot_token")}
        elif doc["service"] == "http_header":
            data = {"name": value_of("header_name"), "value": value_of("header_value")}
        else:  # pragma: no cover - service is a closed Literal
            raise ProviderError("service_key_invalid")
        return preset.n8n_credential_type, data

    async def push(self, user_id: UUID, entry_id: str) -> ServiceKeyPushOut:
        doc = await self._get_doc(user_id, entry_id)
        cred_type, data = self._credential_payload(user_id, doc)
        api_key = self._require_n8n_key()
        base = self._n8n_base_url
        timeout = self.settings.n8n_api_timeout_seconds
        body = {"name": doc["credential_name"], "type": cred_type, "data": data}

        credential_id = doc.get("n8n_credential_id")
        status_code = None
        response = None
        if credential_id:
            # The update endpoint (PUT /credentials/{id} — n8n has no
            # PATCH) takes {name, data} only — the credential type is
            # immutable in n8n, and sending it back is rejected.
            status_code, response = await self.http.put_json(
                f"{base}/api/v1/credentials/{credential_id}",
                api_key,
                {"name": body["name"], "data": body["data"]},
                timeout,
            )
            if status_code == 404:
                # Deleted inside n8n since the last push: recreate below.
                credential_id = None
        if not credential_id:
            status_code, response = await self.http.post_json_body(
                f"{base}/api/v1/credentials", api_key, body, timeout
            )
            if status_code in (200, 201) and isinstance(response, dict):
                credential_id = response.get("id") or credential_id
        if status_code in (401, 403):
            raise ProviderError("n8n_api_unauthorized")
        if status_code is None or status_code not in (200, 201) or not credential_id:
            raise ProviderError("n8n_api_failed")

        pushed_at = _utcnow()
        await self.entries.update_one(
            {"_id": entry_id},
            {
                "$set": {
                    "n8n_credential_id": str(credential_id),
                    "last_pushed_at": pushed_at,
                    "updated_at": pushed_at,
                }
            },
        )
        return ServiceKeyPushOut(
            n8n_credential_id=str(credential_id),
            n8n_credential_name=doc["credential_name"],
            n8n_credential_type=cred_type,
            pushed_at=pushed_at,
        )

    # -- output ---------------------------------------------------------------
    @staticmethod
    def _out(doc: dict) -> ServiceKeyOut:
        preset = PRESETS[doc["service"]]
        stored = doc.get("fields") or {}
        return ServiceKeyOut(
            id=doc["_id"],
            name=doc["name"],
            service=doc["service"],
            credential_name=doc["credential_name"],
            n8n_credential_type=preset.n8n_credential_type,
            n8n_credential_id=doc.get("n8n_credential_id"),
            fields=[
                ServiceKeyFieldOut(
                    key=field.key,
                    label=field.label,
                    secret=field.secret,
                    required=field.required,
                    has_value=bool(stored.get(field.key)),
                )
                for field in preset.fields
            ],
            last_pushed_at=doc.get("last_pushed_at"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )
