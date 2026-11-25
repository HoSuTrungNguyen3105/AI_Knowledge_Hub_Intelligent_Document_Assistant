"""MindFlow -> n8n management bridge (n8n Platform, phase 1).

Where the AI Factory bridge fires one hardcoded webhook, this service talks
to the same self-hosted n8n through its public REST API so MindFlow can
show the connection status, mirror the instance's workflow list and toggle
workflows active/inactive. The n8n API key comes from server settings only
(env ``N8N_API_KEY``): it is never stored in MongoDB, never returned to the
browser and never attached to the Factory webhook calls.

The workflow list is mirrored into ``n8n_workflows`` so the page can still
render the last known list (marked stale) when the home n8n is off.
"""

from datetime import datetime, timezone

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings
from app.schemas.n8n_platform import N8nStatusOut, N8nWorkflowListOut, N8nWorkflowOut
from app.services.ai.base_provider import ProviderError

WORKFLOWS_COLLECTION = "n8n_workflows"
PAGE_LIMIT = 100


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _trigger_kind(node_type: str) -> str | None:
    lowered = node_type.lower()
    if lowered.endswith("webhook"):
        return "webhook"
    if "scheduletrigger" in lowered or lowered.endswith(".cron"):
        return "schedule"
    if "formtrigger" in lowered:
        return "form"
    if "manualtrigger" in lowered:
        return "manual"
    if "executeworkflowtrigger" in lowered:
        return "sub-workflow"
    return None


def parse_workflow(raw: dict, base_url: str) -> N8nWorkflowOut:
    """Map one n8n REST workflow object to the platform shape (pure)."""
    nodes = raw.get("nodes") or []
    triggers: list[str] = []
    webhook_paths: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = _trigger_kind(str(node.get("type") or ""))
        if kind and kind not in triggers:
            triggers.append(kind)
        if kind == "webhook":
            params = node.get("parameters") or {}
            path = params.get("path")
            if isinstance(path, str) and path and path not in webhook_paths:
                webhook_paths.append(path)
    tags: list[str] = []
    for tag in raw.get("tags") or []:
        if isinstance(tag, dict) and isinstance(tag.get("name"), str):
            tags.append(tag["name"])
        elif isinstance(tag, str):
            tags.append(tag)
    workflow_id = str(raw.get("id") or "")
    return N8nWorkflowOut(
        id=workflow_id,
        name=str(raw.get("name") or workflow_id),
        active=bool(raw.get("active")),
        tags=tags,
        triggers=triggers,
        webhook_paths=webhook_paths,
        node_count=len(nodes),
        n8n_created_at=raw.get("createdAt") if isinstance(raw.get("createdAt"), str) else None,
        n8n_updated_at=raw.get("updatedAt") if isinstance(raw.get("updatedAt"), str) else None,
        editor_url=f"{base_url}/workflow/{workflow_id}",
    )


class N8nApiHTTP:
    """Thin async client for the n8n public REST API.

    Returns ``(status, parsed_json)`` for any HTTP answer so the service can
    map statuses to fixed public error codes; transport failures raise
    ``ProviderError("n8n_unreachable")``. Dependency-overridable in tests.
    """

    async def _request(self, method: str, url: str, api_key: str, timeout_seconds: float):
        headers = {"Accept": "application/json"}
        if api_key:
            headers["X-N8N-API-KEY"] = api_key
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,
                trust_env=False,
                headers=headers,
            ) as client:
                response = await client.request(method, url)
        except (httpx.TimeoutException, httpx.RequestError):
            raise ProviderError("n8n_unreachable") from None
        try:
            data = response.json()
        except ValueError:
            data = None
        return response.status_code, data

    async def get_json(self, url: str, api_key: str, timeout_seconds: float):
        return await self._request("GET", url, api_key, timeout_seconds)

    async def post_json(self, url: str, api_key: str, timeout_seconds: float):
        return await self._request("POST", url, api_key, timeout_seconds)


class N8nPlatformService:
    def __init__(self, db: AsyncIOMotorDatabase, settings: Settings, http: N8nApiHTTP):
        self.db = db
        self.settings = settings
        self.http = http

    @property
    def workflows(self):
        return self.db[WORKFLOWS_COLLECTION]

    @property
    def base_url(self) -> str:
        return (self.settings.n8n_api_base_url or self.settings.n8n_webhook_base_url).rstrip("/")

    @property
    def api_key(self) -> str:
        key = self.settings.n8n_api_key
        return key.get_secret_value() if key is not None else ""

    def _require_key(self) -> str:
        key = self.api_key
        if not key:
            raise ProviderError("n8n_api_not_configured")
        return key

    async def _cached(self) -> list[N8nWorkflowOut]:
        docs = await self.workflows.find({}).sort("name", 1).to_list(length=500)
        return [self._out(doc) for doc in docs]

    @staticmethod
    def _out(doc: dict) -> N8nWorkflowOut:
        return N8nWorkflowOut(
            id=doc["_id"],
            name=doc["name"],
            active=doc["active"],
            tags=doc.get("tags") or [],
            triggers=doc.get("triggers") or [],
            webhook_paths=doc.get("webhook_paths") or [],
            node_count=doc.get("node_count") or 0,
            n8n_created_at=doc.get("n8n_created_at"),
            n8n_updated_at=doc.get("n8n_updated_at"),
            editor_url=doc["editor_url"],
        )

    async def _store(self, item: N8nWorkflowOut, synced_at: datetime) -> None:
        doc = item.model_dump()
        doc["_id"] = doc.pop("id")
        doc["synced_at"] = synced_at
        await self.workflows.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def get_status(self) -> N8nStatusOut:
        checked_at = _utcnow()
        base = self.base_url
        count = await self.workflows.count_documents({})
        key = self.api_key
        if not key:
            return N8nStatusOut(
                configured=False,
                reachable=False,
                authenticated=False,
                api_base_url=base,
                editor_url=base,
                workflow_count=count,
                checked_at=checked_at,
                error="n8n_api_not_configured",
            )
        try:
            status, _data = await self.http.get_json(
                f"{base}/api/v1/workflows?limit=1",
                key,
                self.settings.n8n_api_timeout_seconds,
            )
        except ProviderError:
            return N8nStatusOut(
                configured=True,
                reachable=False,
                authenticated=False,
                api_base_url=base,
                editor_url=base,
                workflow_count=count,
                checked_at=checked_at,
                error="n8n_unreachable",
            )
        if status in (401, 403):
            return N8nStatusOut(
                configured=True,
                reachable=True,
                authenticated=False,
                api_base_url=base,
                editor_url=base,
                workflow_count=count,
                checked_at=checked_at,
                error="n8n_api_unauthorized",
            )
        if status >= 400:
            return N8nStatusOut(
                configured=True,
                reachable=True,
                authenticated=False,
                api_base_url=base,
                editor_url=base,
                workflow_count=count,
                checked_at=checked_at,
                error="n8n_api_failed",
            )
        return N8nStatusOut(
            configured=True,
            reachable=True,
            authenticated=True,
            api_base_url=base,
            editor_url=base,
            workflow_count=count,
            checked_at=checked_at,
            error=None,
        )

    async def sync_workflows(self) -> list[N8nWorkflowOut]:
        """Refresh the mirror from n8n and return the fresh list."""
        key = self._require_key()
        base = self.base_url
        items: list[N8nWorkflowOut] = []
        cursor: str | None = None
        while True:
            url = f"{base}/api/v1/workflows?limit={PAGE_LIMIT}"
            if cursor:
                url += f"&cursor={cursor}"
            status, data = await self.http.get_json(
                url, key, self.settings.n8n_api_timeout_seconds
            )
            if status in (401, 403):
                raise ProviderError("n8n_api_unauthorized")
            if status >= 400 or not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise ProviderError("n8n_api_failed")
            for raw in data["data"]:
                if isinstance(raw, dict) and raw.get("id") is not None:
                    items.append(parse_workflow(raw, base))
            cursor = data.get("nextCursor")
            if not cursor:
                break
        synced_at = _utcnow()
        for item in items:
            await self._store(item, synced_at)
        # Drop workflows that no longer exist in n8n.
        ids = [item.id for item in items]
        await self.workflows.delete_many({"_id": {"$nin": ids}})
        return sorted(items, key=lambda item: item.name.lower())

    async def list_workflows(self) -> N8nWorkflowListOut:
        try:
            items = await self.sync_workflows()
            return N8nWorkflowListOut(
                items=items, total=len(items), synced_at=_utcnow(), sync_error=None
            )
        except ProviderError as err:
            cached = await self._cached()
            synced_at = None
            newest = await self.workflows.find_one({}, sort=[("synced_at", -1)])
            if newest is not None:
                synced_at = newest.get("synced_at")
            return N8nWorkflowListOut(
                items=cached, total=len(cached), synced_at=synced_at, sync_error=err.code
            )

    async def set_active(self, workflow_id: str, active: bool) -> N8nWorkflowOut:
        key = self._require_key()
        base = self.base_url
        action = "activate" if active else "deactivate"
        status, data = await self.http.post_json(
            f"{base}/api/v1/workflows/{workflow_id}/{action}",
            key,
            self.settings.n8n_api_timeout_seconds,
        )
        if status == 404:
            raise ProviderError("n8n_workflow_not_found")
        if status in (401, 403):
            raise ProviderError("n8n_api_unauthorized")
        if status >= 400:
            raise ProviderError("n8n_api_failed")
        if isinstance(data, dict) and data.get("id") is not None:
            item = parse_workflow(data, base)
        else:
            doc = await self.workflows.find_one({"_id": workflow_id})
            if doc is None:
                raise ProviderError("n8n_workflow_not_found")
            doc["active"] = active
            item = self._out(doc)
        await self._store(item, _utcnow())
        return item
