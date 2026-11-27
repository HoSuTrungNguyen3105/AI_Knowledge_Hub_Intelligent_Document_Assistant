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

import uuid
from datetime import datetime, timedelta, timezone

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings
from app.schemas.n8n_platform import (
    N8nExecutionDetailOut,
    N8nExecutionListOut,
    N8nExecutionOut,
    N8nNodeOut,
    N8nNodeParamOut,
    N8nNodeStatusOut,
    N8nRunCreateIn,
    N8nRunListOut,
    N8nRunOut,
    N8nStatsOut,
    N8nStatusOut,
    N8nWorkflowCreateIn,
    N8nWorkflowDetailOut,
    N8nWorkflowExportOut,
    N8nWorkflowListOut,
    N8nWorkflowOut,
    N8nWorkflowValidateOut,
)
from app.services.ai.base_provider import ProviderError

WORKFLOWS_COLLECTION = "n8n_workflows"
RUNS_COLLECTION = "n8n_runs"

_FINAL_RUN_STATUSES = {"success", "error", "stopped"}


def _parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _execution_status(raw: dict) -> str:
    """Map an n8n execution summary/detail onto the platform run status."""
    result_error = None
    data = raw.get("data")
    if isinstance(data, dict):
        result = data.get("resultData")
        if isinstance(result, dict):
            result_error = result.get("error")
    if raw.get("error") or result_error:
        return "error"
    status = raw.get("status")
    if isinstance(status, str):
        lowered = status.lower()
        if lowered in ("success",):
            return "success"
        if lowered in ("error", "crashed"):
            return "error"
        if lowered in ("canceled", "cancelled"):
            return "stopped"
        if lowered in ("running", "new", "waiting", "paused"):
            return "running"
    if raw.get("finished") is True:
        return "success"
    return "running"


def _node_statuses_from_execution(raw: dict) -> list["N8nNodeStatusOut"]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    result = data.get("resultData") if isinstance(data, dict) else None
    run_data = result.get("runData") if isinstance(result, dict) else None
    statuses: list[N8nNodeStatusOut] = []
    if not isinstance(run_data, dict):
        return statuses
    for name, entries in run_data.items():
        if not isinstance(entries, list) or not entries:
            statuses.append(N8nNodeStatusOut(name=name, status="pending"))
            continue
        last = entries[-1] if isinstance(entries[-1], dict) else {}
        error = last.get("error")
        duration = last.get("executionTime")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            statuses.append(
                N8nNodeStatusOut(
                    name=name,
                    status="error",
                    duration_ms=int(duration) if isinstance(duration, (int, float)) else None,
                    error=str(message)[:500] if message else "Node failed.",
                )
            )
        else:
            statuses.append(
                N8nNodeStatusOut(
                    name=name,
                    status="success",
                    duration_ms=int(duration) if isinstance(duration, (int, float)) else None,
                )
            )
    return statuses
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

    async def post_json_body(self, url: str, api_key: str, payload: dict, timeout_seconds: float):
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
                response = await client.post(url, json=payload)
        except (httpx.TimeoutException, httpx.RequestError):
            raise ProviderError("n8n_unreachable") from None
        try:
            data = response.json()
        except ValueError:
            data = None
        return response.status_code, data

    async def delete_json(self, url: str, api_key: str, timeout_seconds: float):
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
                response = await client.delete(url)
        except (httpx.TimeoutException, httpx.RequestError):
            raise ProviderError("n8n_unreachable") from None
        return response.status_code

    async def patch_json(self, url: str, api_key: str, payload: dict, timeout_seconds: float):
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
                response = await client.patch(url, json=payload)
        except (httpx.TimeoutException, httpx.RequestError):
            raise ProviderError("n8n_unreachable") from None
        try:
            data = response.json()
        except ValueError:
            data = None
        return response.status_code, data


def _flatten_params(value, prefix: str = "") -> list[N8nNodeParamOut]:
    """Flatten a node's parameters to their scalar leaves (pure).

    Nested objects are walked; arrays and nulls are not editable from
    MindFlow (they stay editable in the n8n editor) and are skipped.
    """
    out: list[N8nNodeParamOut] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_flatten_params(value[key], child))
    elif isinstance(value, bool):
        out.append(N8nNodeParamOut(path=prefix, value=value, kind="boolean"))
    elif isinstance(value, (int, float)):
        out.append(N8nNodeParamOut(path=prefix, value=value, kind="number"))
    elif isinstance(value, str):
        out.append(N8nNodeParamOut(path=prefix, value=value, kind="string"))
    return out


def workflow_detail(raw: dict, base_url: str) -> N8nWorkflowDetailOut:
    """Map one full n8n workflow object to the editable detail shape (pure)."""
    nodes: list[N8nNodeOut] = []
    for node in raw.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        nodes.append(
            N8nNodeOut(
                name=str(node.get("name") or ""),
                type=str(node.get("type") or ""),
                parameters=_flatten_params(node.get("parameters") or {}),
            )
        )
    workflow_id = str(raw.get("id") or "")
    return N8nWorkflowDetailOut(
        id=workflow_id,
        name=str(raw.get("name") or workflow_id),
        active=bool(raw.get("active")),
        editor_url=f"{base_url}/workflow/{workflow_id}",
        nodes=nodes,
    )


def _execution_error_message(raw: dict) -> str | None:
    """Best-effort failure message from an n8n execution object."""
    error = raw.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])[:500]
    if isinstance(error, str) and error:
        return error[:500]
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    result = data.get("resultData") if isinstance(data, dict) else None
    if isinstance(result, dict):
        result_error = result.get("error")
        if isinstance(result_error, dict) and result_error.get("message"):
            return str(result_error["message"])[:500]
        if isinstance(result_error, str) and result_error:
            return result_error[:500]
    return None


def _history_status(raw: dict) -> str:
    """Status for the execution history: like `_execution_status` but
    `waiting` stays visible instead of collapsing into `running`."""
    if _execution_error_message(raw):
        return "error"
    status = raw.get("status")
    if isinstance(status, str):
        lowered = status.lower()
        if lowered == "success":
            return "success"
        if lowered in ("error", "crashed"):
            return "error"
        if lowered == "waiting":
            return "waiting"
        if lowered in ("canceled", "cancelled"):
            return "stopped"
        if lowered in ("running", "new", "paused"):
            return "running"
    if raw.get("finished") is True:
        return "success"
    return "running"


def _execution_out(raw: dict, names: dict[str, str]) -> N8nExecutionOut:
    """Map one n8n execution summary/detail to the history shape (pure)."""
    started = _parse_iso(raw.get("startedAt")) or _parse_iso(raw.get("createdAt"))
    stopped = _parse_iso(raw.get("stoppedAt"))
    duration_ms = None
    if started is not None and stopped is not None:
        duration_ms = int((stopped - started).total_seconds() * 1000)
    workflow_id = str(raw.get("workflowId") or "")
    workflow_data = raw.get("workflowData")
    fallback_name = (
        str(workflow_data.get("name"))
        if isinstance(workflow_data, dict) and workflow_data.get("name")
        else workflow_id
    )
    mode = raw.get("mode")
    return N8nExecutionOut(
        id=str(raw.get("id") or ""),
        workflow_id=workflow_id,
        workflow_name=names.get(workflow_id) or fallback_name,
        status=_history_status(raw),
        mode=mode if isinstance(mode, str) else None,
        started_at=started,
        stopped_at=stopped,
        duration_ms=duration_ms,
        error=_execution_error_message(raw),
    )


def validate_definition(raw) -> N8nWorkflowValidateOut:
    """Structural check of a parsed workflow JSON object (pure).

    Mirrors the rules the create path enforces (name present, nodes a
    non-empty list, every node named and typed) plus a connections shape
    check, and builds the preview the import flow shows before creating.
    """
    if not isinstance(raw, dict):
        return N8nWorkflowValidateOut(valid=False, errors=["workflow_not_an_object"])
    errors: list[str] = []
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("workflow_name_missing")
    nodes = raw.get("nodes")
    node_types: list[str] = []
    triggers: list[str] = []
    webhook_paths: list[str] = []
    if not isinstance(nodes, list) or not nodes:
        errors.append("workflow_nodes_missing")
        nodes = []
    else:
        missing_name = False
        missing_type = False
        for node in nodes:
            if not isinstance(node, dict):
                missing_name = True
                missing_type = True
                continue
            if not isinstance(node.get("name"), str) or not node.get("name"):
                missing_name = True
            node_type = node.get("type")
            if not isinstance(node_type, str) or not node_type:
                missing_type = True
                continue
            if node_type not in node_types:
                node_types.append(node_type)
            kind = _trigger_kind(node_type)
            if kind and kind not in triggers:
                triggers.append(kind)
            if kind == "webhook":
                params = node.get("parameters")
                path = params.get("path") if isinstance(params, dict) else None
                if isinstance(path, str) and path and path not in webhook_paths:
                    webhook_paths.append(path)
        if missing_name:
            errors.append("workflow_node_missing_name")
        if missing_type:
            errors.append("workflow_node_missing_type")
    connections = raw.get("connections")
    if connections is not None and not isinstance(connections, dict):
        errors.append("workflow_connections_invalid")
    return N8nWorkflowValidateOut(
        valid=not errors,
        errors=errors,
        name=name if isinstance(name, str) and name else None,
        node_count=len(nodes),
        node_types=sorted(node_types),
        triggers=triggers,
        webhook_paths=webhook_paths,
    )


class N8nPlatformService:
    def __init__(self, db: AsyncIOMotorDatabase, settings: Settings, http: N8nApiHTTP):
        self.db = db
        self.settings = settings
        self.http = http

    @property
    def workflows(self):
        return self.db[WORKFLOWS_COLLECTION]

    @property
    def runs(self):
        return self.db[RUNS_COLLECTION]

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

    async def fetch_workflow_json(self, workflow_id: str) -> dict:
        """The raw workflow definition, live from n8n (public wrapper
        around the internal fetch, for the template credential-binding
        flow that rewrites node credentials in place)."""
        return await self._get_raw_workflow(workflow_id)

    async def list_credentials(self) -> list[dict]:
        """Credentials that exist in the user's n8n: id, name and type
        only — the n8n API never returns secret values. Used to bind
        template nodes to the user's own credentials instead of the
        template author's."""
        key = self._require_key()
        status, data = await self.http.get_json(
            f"{self.base_url}/api/v1/credentials",
            key,
            self.settings.n8n_api_timeout_seconds,
        )
        if status in (401, 403):
            raise ProviderError("n8n_api_unauthorized")
        if status >= 400 or not isinstance(data, dict):
            raise ProviderError("n8n_api_failed")
        items = data.get("data")
        if not isinstance(items, list):
            raise ProviderError("n8n_api_failed")
        out = []
        for item in items:
            if isinstance(item, dict) and item.get("id") is not None and item.get("type"):
                out.append(
                    {
                        "id": str(item["id"]),
                        "name": str(item.get("name") or ""),
                        "type": str(item["type"]),
                    }
                )
        return sorted(out, key=lambda c: (c["type"], c["name"].lower()))

    async def _get_raw_workflow(self, workflow_id: str) -> dict:
        key = self._require_key()
        status, data = await self.http.get_json(
            f"{self.base_url}/api/v1/workflows/{workflow_id}",
            key,
            self.settings.n8n_api_timeout_seconds,
        )
        if status == 404:
            raise ProviderError("n8n_workflow_not_found")
        if status in (401, 403):
            raise ProviderError("n8n_api_unauthorized")
        if status >= 400 or not isinstance(data, dict):
            raise ProviderError("n8n_api_failed")
        return data

    @staticmethod
    def _validate_nodes(nodes: list) -> None:
        """Every node needs a name and a type; anything else is forwarded
        to n8n exactly as supplied."""
        for node in nodes:
            if (
                not isinstance(node, dict)
                or not isinstance(node.get("name"), str)
                or not node.get("name")
                or not isinstance(node.get("type"), str)
                or not node.get("type")
            ):
                raise ProviderError("n8n_workflow_invalid")

    async def create_workflow(self, payload_in: N8nWorkflowCreateIn) -> N8nWorkflowOut:
        """Create a workflow in n8n from a user-supplied definition.

        The definition is validated structurally (every node needs a name
        and a type) and forwarded as-is otherwise. n8n creates it inactive;
        the user reviews, wires credentials and activates it in n8n.
        """
        self._validate_nodes(payload_in.nodes)
        key = self._require_key()
        payload = {
            "name": payload_in.name,
            "nodes": payload_in.nodes,
            "connections": payload_in.connections,
            "settings": payload_in.settings,
        }
        status, data = await self.http.post_json_body(
            f"{self.base_url}/api/v1/workflows",
            key,
            payload,
            self.settings.n8n_api_timeout_seconds,
        )
        if status == 400:
            raise ProviderError("n8n_workflow_invalid")
        if status in (401, 403):
            raise ProviderError("n8n_api_unauthorized")
        if status >= 400 or not isinstance(data, dict) or data.get("id") is None:
            raise ProviderError("n8n_api_failed")
        item = parse_workflow(data, self.base_url)
        await self._store(item, _utcnow())
        return item

    async def replace_workflow(self, workflow_id: str, payload_in: N8nWorkflowCreateIn) -> N8nWorkflowOut:
        """Replace a workflow's definition in n8n (used by template sync
        updates). Same PATCH path as parameter editing; only the fields the
        n8n update API accepts are sent."""
        key = self._require_key()
        payload = {
            "name": payload_in.name,
            "nodes": payload_in.nodes,
            "connections": payload_in.connections,
            "settings": payload_in.settings,
        }
        status, data = await self.http.patch_json(
            f"{self.base_url}/api/v1/workflows/{workflow_id}",
            key,
            payload,
            self.settings.n8n_api_timeout_seconds,
        )
        if status == 404:
            raise ProviderError("n8n_workflow_not_found")
        if status in (401, 403):
            raise ProviderError("n8n_api_unauthorized")
        if status >= 400 or not isinstance(data, dict):
            raise ProviderError("n8n_api_failed")
        item = parse_workflow(data, self.base_url)
        await self._store(item, _utcnow())
        return item

    async def delete_workflow(self, workflow_id: str) -> None:
        """Delete a workflow from n8n. A 404 counts as success: the goal
        state (workflow gone) is already reached — the mirror entry is
        dropped either way so the list cannot resurrect it."""
        key = self._require_key()
        status = await self.http.delete_json(
            f"{self.base_url}/api/v1/workflows/{workflow_id}",
            key,
            self.settings.n8n_api_timeout_seconds,
        )
        if status in (401, 403):
            raise ProviderError("n8n_api_unauthorized")
        if status >= 400 and status != 404:
            raise ProviderError("n8n_api_failed")
        await self.workflows.delete_one({"_id": workflow_id})

    async def update_workflow(
        self, workflow_id: str, payload_in: N8nWorkflowCreateIn
    ) -> N8nWorkflowOut:
        """Replace an existing workflow's definition from an imported JSON
        (Workflow Management "Update JSON"). The id comes from the stored
        link, never from the payload, so an update can never create or
        overwrite a different workflow; on failure nothing is deleted."""
        self._validate_nodes(payload_in.nodes)
        return await self.replace_workflow(workflow_id, payload_in)

    async def validate_workflow(self, raw) -> N8nWorkflowValidateOut:
        """Validate-only pass for the import flow; touches nothing."""
        return validate_definition(raw)

    async def export_workflow(self, workflow_id: str) -> N8nWorkflowExportOut:
        """The workflow definition read live from n8n (never the mirror),
        so an export is always the freshest version."""
        raw = await self._get_raw_workflow(workflow_id)
        return N8nWorkflowExportOut(
            id=str(raw.get("id") or workflow_id),
            name=str(raw.get("name") or ""),
            workflow=raw,
        )

    async def _count_today_executions(self, key: str) -> tuple[int, int, bool]:
        """Count today's (UTC) executions and failures from the n8n API.

        Executions come newest-first; paging stops at the first page that
        reaches an older execution, or at a hard page cap — in that case
        the counts are a lower bound and `truncated` says so.
        """
        boundary = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today = 0
        failed = 0
        truncated = False
        cursor: str | None = None
        for _page in range(5):
            url = f"{self.base_url}/api/v1/executions?limit={PAGE_LIMIT}"
            if cursor:
                url += f"&cursor={cursor}"
            status, data = await self.http.get_json(
                url, key, self.settings.n8n_api_timeout_seconds
            )
            if status in (401, 403):
                raise ProviderError("n8n_api_unauthorized")
            if status >= 400 or not isinstance(data, dict) or not isinstance(
                data.get("data"), list
            ):
                raise ProviderError("n8n_api_failed")
            reached_older = False
            for item in data["data"]:
                if not isinstance(item, dict):
                    continue
                started = _parse_iso(item.get("startedAt")) or _parse_iso(
                    item.get("createdAt")
                )
                if started is None:
                    continue
                if started >= boundary:
                    today += 1
                    if _history_status(item) == "error":
                        failed += 1
                else:
                    reached_older = True
            cursor = data.get("nextCursor")
            if reached_older or not cursor:
                break
        else:
            truncated = True
        return today, failed, truncated

    async def get_stats(self) -> N8nStatsOut:
        listing = await self.list_workflows()
        active = sum(1 for item in listing.items if item.active)
        executions_today: int | None = None
        failed_today: int | None = None
        truncated = False
        error: str | None = None
        try:
            key = self._require_key()
            executions_today, failed_today, truncated = (
                await self._count_today_executions(key)
            )
        except ProviderError as err:
            error = err.code
        return N8nStatsOut(
            total_workflows=listing.total,
            active_workflows=active,
            inactive_workflows=listing.total - active,
            executions_today=executions_today,
            failed_executions_today=failed_today,
            executions_truncated=truncated,
            executions_error=error,
            checked_at=_utcnow(),
        )

    async def list_executions(
        self,
        workflow_id: str | None = None,
        status_filter: str | None = None,
        limit: int = 50,
    ) -> N8nExecutionListOut:
        """Execution history read live from n8n (all workflows, not only
        runs MindFlow started). Like the workflow list, a read failure is
        reported on the object instead of failing the page."""
        try:
            key = self._require_key()
            limit = max(1, min(limit, 100))
            fetch = min(250, limit * 3) if status_filter else limit
            url = f"{self.base_url}/api/v1/executions?limit={fetch}"
            if workflow_id:
                url += f"&workflowId={workflow_id}"
            status, data = await self.http.get_json(
                url, key, self.settings.n8n_api_timeout_seconds
            )
            if status in (401, 403):
                raise ProviderError("n8n_api_unauthorized")
            if status >= 400 or not isinstance(data, dict) or not isinstance(
                data.get("data"), list
            ):
                raise ProviderError("n8n_api_failed")
            names = {item.id: item.name for item in await self._cached()}
            mapped = [
                _execution_out(raw, names)
                for raw in data["data"]
                if isinstance(raw, dict)
            ]
            if status_filter:
                mapped = [item for item in mapped if item.status == status_filter]
            return N8nExecutionListOut(
                items=mapped[:limit], total=len(mapped), error=None
            )
        except ProviderError as err:
            return N8nExecutionListOut(items=[], total=0, error=err.code)

    async def get_execution(self, execution_id: str) -> N8nExecutionDetailOut:
        key = self._require_key()
        status, data = await self.http.get_json(
            f"{self.base_url}/api/v1/executions/{execution_id}?includeData=true",
            key,
            self.settings.n8n_api_timeout_seconds,
        )
        if status == 404:
            raise ProviderError("execution_not_found")
        if status in (401, 403):
            raise ProviderError("n8n_api_unauthorized")
        if status >= 400 or not isinstance(data, dict):
            raise ProviderError("n8n_api_failed")
        raw = data
        if not isinstance(raw.get("id"), str) and isinstance(data.get("data"), dict):
            raw = data["data"]
        names = {item.id: item.name for item in await self._cached()}
        base = _execution_out(raw, names)
        return N8nExecutionDetailOut(
            **base.model_dump(),
            node_statuses=_node_statuses_from_execution(raw),
        )

    async def get_workflow_detail(self, workflow_id: str) -> N8nWorkflowDetailOut:
        raw = await self._get_raw_workflow(workflow_id)
        return workflow_detail(raw, self.base_url)

    # -- Phase 2: generic runs, reconciled against n8n executions --------

    @staticmethod
    def _run_out(doc: dict) -> N8nRunOut:
        return N8nRunOut(
            id=str(doc["_id"]),
            workflow_id=doc.get("workflow_id", ""),
            workflow_name=doc.get("workflow_name", ""),
            status=doc.get("status", "running"),
            input=doc.get("input") or {},
            n8n_execution_id=doc.get("n8n_execution_id"),
            error=doc.get("error"),
            retry_of=doc.get("retry_of"),
            node_statuses=[
                N8nNodeStatusOut(**item) for item in (doc.get("node_statuses") or [])
            ],
            started_at=doc.get("started_at"),
            finished_at=doc.get("finished_at"),
        )

    async def _save_run(self, doc: dict) -> None:
        await self.runs.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def start_run(self, user_id: str, payload_in: N8nRunCreateIn, *, retry_of: str | None = None) -> N8nRunOut:
        """Start any active webhook workflow and track it as a run.

        The workflow fires through its public webhook (no API key on that
        call, exactly like the Factory bridge). The run is then reconciled
        against the n8n executions API to attach the real execution id and
        per-node progress; nothing about the outcome is invented here.
        """
        workflow = await self.workflows.find_one({"_id": payload_in.workflow_id})
        if workflow is None:
            raise ProviderError("n8n_workflow_not_found")
        if not workflow.get("active"):
            raise ProviderError("n8n_workflow_inactive")
        paths = workflow.get("webhook_paths") or []
        if not paths:
            raise ProviderError("n8n_workflow_no_webhook")
        now = _utcnow()
        doc = {
            "_id": uuid.uuid4().hex,
            "user_id": user_id,
            "workflow_id": payload_in.workflow_id,
            "workflow_name": workflow.get("name", ""),
            "status": "running",
            "input": payload_in.payload,
            "n8n_execution_id": None,
            "error": None,
            "retry_of": retry_of,
            "node_statuses": [],
            "started_at": now,
            "finished_at": None,
        }
        await self._save_run(doc)
        webhook_base = self.settings.n8n_webhook_base_url.rstrip("/")
        try:
            status, _data = await self.http.post_json_body(
                f"{webhook_base}/{paths[0].lstrip('/')}",
                "",
                payload_in.payload,
                self.settings.n8n_factory_timeout_seconds,
            )
            if status >= 400:
                doc["status"] = "error"
                doc["error"] = f"webhook_http_{status}"
                doc["finished_at"] = _utcnow()
                await self._save_run(doc)
                return self._run_out(doc)
        except ProviderError:
            doc["status"] = "error"
            doc["error"] = "n8n_unreachable"
            doc["finished_at"] = _utcnow()
            await self._save_run(doc)
            return self._run_out(doc)
        await self._reconcile(doc)
        return self._run_out(doc)

    async def _reconcile(self, doc: dict) -> None:
        """Attach the n8n execution and refresh status/node progress.

        Best effort: any API problem leaves the stored run untouched so a
        later read can retry the reconciliation.
        """
        if doc.get("status") in _FINAL_RUN_STATUSES:
            return
        key = self.api_key
        if not key:
            return
        timeout = self.settings.n8n_api_timeout_seconds
        try:
            if not doc.get("n8n_execution_id"):
                status, data = await self.http.get_json(
                    f"{self.base_url}/api/v1/executions?workflowId={doc['workflow_id']}&limit=10",
                    key,
                    timeout,
                )
                if status >= 400 or not isinstance(data, dict):
                    return
                items = data.get("data")
                if not isinstance(items, list):
                    return
                threshold = doc["started_at"] - timedelta(seconds=5)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    started = _parse_iso(item.get("startedAt"))
                    if started is not None and started >= threshold and item.get("id") is not None:
                        doc["n8n_execution_id"] = str(item["id"])
                        break
                if not doc.get("n8n_execution_id"):
                    return
                await self._save_run(doc)
            status, data = await self.http.get_json(
                f"{self.base_url}/api/v1/executions/{doc['n8n_execution_id']}?includeData=true",
                key,
                timeout,
            )
            if status >= 400 or not isinstance(data, dict):
                return
        except ProviderError:
            return
        detail = data.get("data") if isinstance(data.get("data"), dict) else data
        new_status = _execution_status(detail)
        doc["node_statuses"] = [
            item.model_dump() for item in _node_statuses_from_execution(detail)
        ]
        if new_status != "running":
            doc["status"] = new_status
            stopped = _parse_iso(detail.get("stoppedAt"))
            doc["finished_at"] = stopped or _utcnow()
            if new_status == "error" and not doc.get("error"):
                result = detail.get("data", {}).get("resultData", {}) if isinstance(detail.get("data"), dict) else {}
                error = result.get("error") if isinstance(result, dict) else None
                if isinstance(error, dict) and error.get("message"):
                    doc["error"] = str(error["message"])[:500]
        await self._save_run(doc)

    async def list_runs(self, user_id: str, workflow_id: str | None = None, limit: int = 50) -> N8nRunListOut:
        query: dict = {"user_id": user_id}
        if workflow_id:
            query["workflow_id"] = workflow_id
        total = await self.runs.count_documents(query)
        cursor = self.runs.find(query).sort("started_at", -1).limit(max(1, min(limit, 100)))
        items = []
        async for doc in cursor:
            await self._reconcile(doc)
            items.append(self._run_out(doc))
        return N8nRunListOut(items=items, total=total)

    async def _get_run_doc(self, user_id: str, run_id: str) -> dict:
        doc = await self.runs.find_one({"_id": run_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("n8n_run_not_found")
        return doc

    async def get_run(self, user_id: str, run_id: str) -> N8nRunOut:
        doc = await self._get_run_doc(user_id, run_id)
        await self._reconcile(doc)
        return self._run_out(doc)

    async def stop_run(self, user_id: str, run_id: str) -> N8nRunOut:
        doc = await self._get_run_doc(user_id, run_id)
        await self._reconcile(doc)
        if doc.get("status") in _FINAL_RUN_STATUSES:
            return self._run_out(doc)
        if doc.get("n8n_execution_id") and self.api_key:
            try:
                await self.http.delete_json(
                    f"{self.base_url}/api/v1/executions/{doc['n8n_execution_id']}",
                    self.api_key,
                    self.settings.n8n_api_timeout_seconds,
                )
            except ProviderError:
                pass  # The run is still marked stopped in MindFlow below.
        doc["status"] = "stopped"
        doc["finished_at"] = _utcnow()
        await self._save_run(doc)
        return self._run_out(doc)

    async def retry_run(self, user_id: str, run_id: str) -> N8nRunOut:
        doc = await self._get_run_doc(user_id, run_id)
        return await self.start_run(
            user_id,
            N8nRunCreateIn(workflow_id=doc["workflow_id"], payload=doc.get("input") or {}),
            retry_of=run_id,
        )
