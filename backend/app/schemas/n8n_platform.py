"""Response shapes for the n8n Platform endpoints (phase 1).

These describe the user's own self-hosted n8n instance as MindFlow sees it
through the n8n public REST API: connection status plus a cached mirror of
its workflow list. Nothing here ever carries the n8n API key.
"""

from datetime import datetime

from pydantic import BaseModel


class N8nStatusOut(BaseModel):
    # True only when the server holds an API key for n8n.
    configured: bool
    # The instance answered at all (health check or API call).
    reachable: bool
    # The API key was accepted by the instance.
    authenticated: bool
    # Public origin the REST calls go to (no path, no credentials).
    api_base_url: str
    # Where the "Open in n8n" button points.
    editor_url: str
    workflow_count: int
    checked_at: datetime
    # Machine-readable reason when a check failed (e.g. n8n_unreachable,
    # n8n_api_unauthorized, n8n_api_not_configured); None when healthy.
    error: str | None = None


class N8nWorkflowOut(BaseModel):
    id: str
    name: str
    active: bool
    tags: list[str] = []
    # Trigger kinds found in the workflow's nodes, e.g. ["webhook"],
    # ["schedule"], ["manual"].
    triggers: list[str] = []
    # Webhook paths of webhook triggers, when the nodes declare them.
    webhook_paths: list[str] = []
    node_count: int = 0
    # ISO timestamps exactly as n8n reports them; None when absent.
    n8n_created_at: str | None = None
    n8n_updated_at: str | None = None
    editor_url: str


class N8nWorkflowListOut(BaseModel):
    items: list[N8nWorkflowOut]
    total: int
    # When the cache was last refreshed from n8n; None if never synced.
    synced_at: datetime | None = None
    # Set when the list shown is a stale cache because the refresh failed.
    sync_error: str | None = None
