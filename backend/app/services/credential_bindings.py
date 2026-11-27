"""Per-user credential bindings: template credential type -> the user's
own n8n credential.

Templates ship with credential references from the original author's
machine, so an installed copy cannot run until every node is re-pointed
at the installing user's credentials. A binding records that mapping
once per credential type; the template install/update path rewrites
node credentials through :func:`apply_bindings_to_nodes`, and
``apply_to_installed`` re-applies the mapping in bulk to workflows that
were installed before the binding existed — fetching each workflow live
from n8n so edits the user made there are preserved.
"""

import copy
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.credential_bindings import (
    ApplyInstalledItemOut,
    ApplyInstalledOut,
    CredentialBindingOut,
    CredentialBindingsOut,
    N8nCredentialOut,
    RequiredCredentialTypeOut,
)
from app.schemas.n8n_platform import N8nWorkflowCreateIn
from app.services.ai.base_provider import ProviderError
from app.services.n8n_platform import N8nPlatformService

BINDINGS_COLLECTION = "user_credential_bindings"
TEMPLATES_COLLECTION = "shared_workflows"
USER_WORKFLOWS_COLLECTION = "user_workflows"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def apply_bindings_to_nodes(nodes, bindings: dict) -> tuple[list, list[str]]:
    """Return ``(nodes, applied_types)``: a deep copy of ``nodes`` where
    every ``credentials`` entry whose type is bound now points at the
    bound credential ``{"id", "name"}``. Unbound types, nodes without
    credentials and non-dict entries pass through untouched; the input
    is never mutated."""
    applied: list[str] = []
    out = copy.deepcopy(nodes) if isinstance(nodes, list) else []
    for node in out:
        if not isinstance(node, dict):
            continue
        credentials = node.get("credentials")
        if not isinstance(credentials, dict):
            continue
        for cred_type in list(credentials.keys()):
            binding = bindings.get(cred_type)
            if binding:
                credentials[cred_type] = {"id": binding["id"], "name": binding["name"]}
                if cred_type not in applied:
                    applied.append(cred_type)
    return out, applied


def credential_coverage(nodes, bindings: dict) -> tuple[list[str], list[str]]:
    """Return ``(rewritten_types, missing_types)`` for a definition.

    ``rewritten`` are the credential types whose ids the user's
    bindings would replace (the same types apply_bindings_to_nodes
    reports as applied); ``missing`` are the types the definition
    references but the user has NOT bound — those nodes keep the
    template author's credential ids, which do not exist in the user's
    n8n, so the workflow cannot run until the user binds or picks a
    credential in n8n. Pure inspection: nothing is mutated and nothing
    raises, so install flows can report coverage without changing
    install behaviour (installs are never blocked by this)."""
    referenced: set[str] = set()
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            credentials = node.get("credentials")
            if isinstance(credentials, dict):
                referenced.update(str(key) for key in credentials)
    bound = bindings or {}
    rewritten = sorted(t for t in referenced if bound.get(t))
    missing = sorted(t for t in referenced if not bound.get(t))
    return rewritten, missing


class CredentialBindingService:
    def __init__(self, db: AsyncIOMotorDatabase, platform: "N8nPlatformService"):
        self.db = db
        self.platform = platform

    @property
    def bindings(self):
        return self.db[BINDINGS_COLLECTION]

    @property
    def templates(self):
        return self.db[TEMPLATES_COLLECTION]

    @property
    def installs(self):
        return self.db[USER_WORKFLOWS_COLLECTION]

    async def bindings_map(self, user_id: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        cursor = self.bindings.find({"user_id": user_id})
        async for doc in cursor:
            out[doc["cred_type"]] = {
                "id": doc["n8n_credential_id"],
                "name": doc.get("n8n_credential_name", ""),
            }
        return out

    @staticmethod
    def _binding_out(doc: dict) -> CredentialBindingOut:
        return CredentialBindingOut(
            cred_type=doc["cred_type"],
            n8n_credential_id=doc["n8n_credential_id"],
            n8n_credential_name=doc.get("n8n_credential_name", ""),
            updated_at=doc.get("updated_at"),
        )

    async def list_view(self, user_id: str) -> CredentialBindingsOut:
        binding_docs = []
        cursor = self.bindings.find({"user_id": user_id}).sort("cred_type", 1)
        async for doc in cursor:
            binding_docs.append(doc)
        bound_types = {doc["cred_type"] for doc in binding_docs}

        n8n_credentials: list[N8nCredentialOut] = []
        n8n_error: str | None = None
        try:
            raw_credentials = await self.platform.list_credentials()
            n8n_credentials = [N8nCredentialOut(**item) for item in raw_credentials]
        except ProviderError as exc:
            n8n_error = exc.code

        counts: dict[str, int] = {}
        cursor = self.templates.find(
            {"review_status": "approved"}, {"credential_types": 1}
        )
        async for doc in cursor:
            for cred_type in doc.get("credential_types") or []:
                counts[cred_type] = counts.get(cred_type, 0) + 1
        required = [
            RequiredCredentialTypeOut(
                cred_type=cred_type,
                template_count=counts[cred_type],
                bound=cred_type in bound_types,
            )
            for cred_type in sorted(counts)
        ]
        return CredentialBindingsOut(
            bindings=[self._binding_out(doc) for doc in binding_docs],
            n8n_credentials=n8n_credentials,
            required_types=required,
            n8n_error=n8n_error,
        )

    async def set_binding(
        self, user_id: str, cred_type: str, credential_id: str
    ) -> CredentialBindingOut:
        credentials = await self.platform.list_credentials()
        found = next((c for c in credentials if c["id"] == credential_id), None)
        if found is None or found["type"] != cred_type:
            raise ProviderError("credential_binding_invalid")
        now = _utcnow()
        await self.bindings.update_one(
            {"user_id": user_id, "cred_type": cred_type},
            {
                "$set": {
                    "n8n_credential_id": found["id"],
                    "n8n_credential_name": found["name"],
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "_id": uuid.uuid4().hex,
                    "user_id": user_id,
                    "cred_type": cred_type,
                },
            },
            upsert=True,
        )
        doc = await self.bindings.find_one(
            {"user_id": user_id, "cred_type": cred_type}
        )
        return self._binding_out(doc)

    async def delete_binding(self, user_id: str, cred_type: str) -> None:
        result = await self.bindings.delete_one(
            {"user_id": user_id, "cred_type": cred_type}
        )
        if result.deleted_count == 0:
            raise ProviderError("credential_binding_not_found")

    async def apply_to_installed(self, user_id: str) -> ApplyInstalledOut:
        """Re-apply the user's bindings to every workflow they already
        installed from the library. Each workflow is fetched live from
        n8n, rewritten in memory and PATCHed back only when at least one
        node actually changed."""
        bindings = await self.bindings_map(user_id)
        results: list[ApplyInstalledItemOut] = []
        updated = unchanged = failed = 0
        cursor = self.installs.find({"user_id": user_id}).sort("installed_at", -1)
        async for doc in cursor:
            item = ApplyInstalledItemOut(
                install_id=str(doc["_id"]),
                template_name=doc.get("template_name", ""),
                n8n_workflow_id=doc.get("n8n_workflow_id", ""),
                status="unchanged",
            )
            try:
                raw = await self.platform.fetch_workflow_json(doc["n8n_workflow_id"])
                nodes = raw.get("nodes") if isinstance(raw.get("nodes"), list) else []
                new_nodes, applied = apply_bindings_to_nodes(nodes, bindings)
                if applied:
                    connections = raw.get("connections")
                    settings = raw.get("settings")
                    payload = N8nWorkflowCreateIn(
                        name=str(raw.get("name") or doc.get("template_name") or "Workflow"),
                        nodes=new_nodes,
                        connections=connections if isinstance(connections, dict) else {},
                        settings=settings if isinstance(settings, dict) else {},
                    )
                    await self.platform.replace_workflow(doc["n8n_workflow_id"], payload)
                    item.status = "updated"
                    item.bound_types = applied
                    updated += 1
                else:
                    unchanged += 1
            except ProviderError as exc:
                item.status = "failed"
                item.error = exc.code
                failed += 1
            results.append(item)
        return ApplyInstalledOut(
            results=results, updated=updated, unchanged=unchanged, failed=failed
        )
