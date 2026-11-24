"""MindFlow -> n8n `agent.created` webhook (mindflow-workforce-feature
section 11, wave 5).

When a workforce AI resource is created, the backend notifies the
user's n8n so automations can react (welcome flow, registry, alerts).
The payload NEVER contains an API key — only the agent profile. The
delivery outcome is stored on the resource document as `n8n_sync`:

  pending  not attempted yet, or the webhook URL is not configured
  synced   n8n answered 200 with received=true and a matching agentId
  failed   every attempt failed; `error` keeps a short machine reason

Delivery is best-effort with a short timeout and up to 3 attempts; it
never fails the resource creation itself. Retrying is idempotent on
the n8n side, which upserts its receipt by agent id.
"""

import asyncio
from datetime import datetime, timezone

import httpx

from app.core.config import Settings
from app.models.base import utcnow

MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 3.0


def build_agent_payload(resource: dict, sent_at: datetime) -> dict:
    ai = resource.get("ai") or {}
    return {
        "event": "agent.created",
        "sentAt": sent_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "agent": {
            "id": str(resource["_id"]),
            "name": resource["name"],
            "type": resource["type"],
            "provider": ai.get("provider"),
            "model": ai.get("model"),
            "role": resource["role"],
            "skills": [skill["name"] for skill in resource.get("skills", [])],
            "allowedTools": ai.get("allowed_tools", []),
            "deniedScopes": ai.get("denied_scopes", []),
            "tokenLimitPerTask": ai.get("token_limit_per_task"),
            "status": "active" if resource["availability_status"] == "connected" else "inactive",
        },
    }


async def deliver(
    url: str, secret: str, payload: dict, transport: httpx.BaseTransport | None = None
) -> tuple[bool, str | None, str | None]:
    """POST the payload; success requires the contract receipt
    (HTTP 200 + received is true + agentId matches). Returns
    (ok, execution_id, error)."""
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-mindflow-secret"] = secret
    last_error: str | None = None
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=transport) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("received") is True and str(
                        data.get("agentId")
                    ) == payload["agent"]["id"]:
                        execution = data.get("executionId")
                        return True, str(execution) if execution else None, None
                    last_error = "unexpected_receipt"
                else:
                    last_error = f"http_{response.status_code}"
            except (httpx.HTTPError, ValueError) as exc:
                last_error = type(exc).__name__
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(0.2 * (attempt + 1))
    return False, None, last_error


async def sync_resource(
    db, settings: Settings, resource: dict, transport: httpx.BaseTransport | None = None
) -> dict:
    """Deliver (when configured) and persist the n8n_sync block on the
    resource document. Returns the n8n_sync dict."""
    now = utcnow()
    if not settings.n8n_agent_webhook_url:
        sync = {
            "status": "pending",
            "last_attempt_at": None,
            "execution_id": None,
            "error": "webhook_not_configured",
        }
    else:
        payload = build_agent_payload(resource, now)
        ok, execution_id, error = await deliver(
            settings.n8n_agent_webhook_url,
            settings.n8n_agent_webhook_secret,
            payload,
            transport,
        )
        sync = {
            "status": "synced" if ok else "failed",
            "last_attempt_at": now,
            "execution_id": execution_id,
            "error": error,
        }
    await db.resources.update_one({"_id": resource["_id"]}, {"$set": {"n8n_sync": sync}})
    return sync
