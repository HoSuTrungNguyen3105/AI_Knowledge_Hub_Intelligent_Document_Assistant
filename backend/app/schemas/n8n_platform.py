"""Response shapes for the n8n Platform endpoints (phase 1).

These describe the user's own self-hosted n8n instance as MindFlow sees it
through the n8n public REST API: connection status plus a cached mirror of
its workflow list. Nothing here ever carries the n8n API key.
"""

from typing import Any

from datetime import datetime

from pydantic import BaseModel, Field


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
    # Definition snapshots MindFlow keeps for this workflow (see
    # N8nWorkflowSnapshotOut). Filled in on list responses; single-item
    # responses report whether this workflow has at least one snapshot.
    has_snapshot: bool = False
    snapshot_count: int = 0


class N8nWorkflowSnapshotOut(BaseModel):
    """One stored definition snapshot of an n8n workflow.

    Snapshots are the safety net for workflows that live in n8n: the
    newest definition seen on sync/create/update is kept (plus a short
    history) so a workflow broken or edited badly in n8n can be
    restored from MindFlow. The definition itself is not in this
    summary shape — restoring uses it server-side.
    """

    id: str
    workflow_id: str
    name: str
    node_count: int = 0
    content_hash: str
    # sync | create | update | duplicate | restore
    source: str
    created_at: datetime


class N8nWorkflowListOut(BaseModel):
    items: list[N8nWorkflowOut]
    total: int
    # When the cache was last refreshed from n8n; None if never synced.
    synced_at: datetime | None = None
    # Set when the list shown is a stale cache because the refresh failed.
    sync_error: str | None = None


class N8nNodeParamOut(BaseModel):
    # Dotted path inside the node's `parameters` object, e.g. "path" or
    # "options.timeout". Only scalar leaves are editable from MindFlow.
    path: str
    value: Any = None
    # "string" | "number" | "boolean" — drives the form control.
    kind: str


class N8nNodeOut(BaseModel):
    name: str
    type: str
    parameters: list[N8nNodeParamOut] = []


class N8nWorkflowDetailOut(BaseModel):
    id: str
    name: str
    active: bool
    editor_url: str
    nodes: list[N8nNodeOut] = []


class N8nWorkflowValidateIn(BaseModel):
    """A parsed workflow JSON object sent for validation only.

    Nothing is created in n8n; the service checks the structure and returns
    a preview so the user can confirm before the real import.
    """

    workflow: dict[str, Any]


class N8nWorkflowValidateOut(BaseModel):
    valid: bool
    # Machine-readable problem codes (workflow_name_missing,
    # workflow_nodes_missing, workflow_node_missing_name,
    # workflow_node_missing_type, workflow_connections_invalid,
    # workflow_not_an_object); empty when valid.
    errors: list[str] = []
    name: str | None = None
    node_count: int = 0
    node_types: list[str] = []
    triggers: list[str] = []
    webhook_paths: list[str] = []


class N8nWorkflowExportOut(BaseModel):
    """The freshest workflow definition, read live from n8n for download."""

    id: str
    name: str
    workflow: dict[str, Any]


class N8nStatsOut(BaseModel):
    """Dashboard statistics for the Workflow Management page.

    Workflow counts come from the synced mirror. Execution counts are read
    live from the n8n executions API for the current UTC day; they stay
    None (with `executions_error` set) when n8n cannot be read — numbers
    are never invented.
    """

    total_workflows: int
    active_workflows: int
    inactive_workflows: int
    executions_today: int | None = None
    failed_executions_today: int | None = None
    # True when the scan hit its page cap while more of today's executions
    # may exist; the counts are then a lower bound.
    executions_truncated: bool = False
    executions_error: str | None = None
    checked_at: datetime


class N8nExecutionOut(BaseModel):
    """One n8n execution (any workflow, not only MindFlow-started runs)."""

    id: str
    workflow_id: str
    # Joined from the synced workflow mirror; falls back to the id.
    workflow_name: str
    # success | error | running | waiting | stopped
    status: str
    mode: str | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None


class N8nExecutionListOut(BaseModel):
    items: list[N8nExecutionOut]
    total: int
    # Set when n8n could not be read; items is then empty, never faked.
    error: str | None = None


class N8nRunCreateIn(BaseModel):
    workflow_id: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class N8nNodeStatusOut(BaseModel):
    name: str
    status: str  # success | error | pending
    duration_ms: int | None = None
    error: str | None = None


class N8nRunOut(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    status: str  # running | success | error | stopped
    input: dict[str, Any] = Field(default_factory=dict)
    n8n_execution_id: str | None = None
    error: str | None = None
    retry_of: str | None = None
    node_statuses: list[N8nNodeStatusOut] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None


class N8nRunListOut(BaseModel):
    items: list[N8nRunOut]
    total: int


class N8nWorkflowCreateIn(BaseModel):
    """A whole workflow definition pasted/built by the user.

    Only the fields the n8n create API accepts are forwarded (name, nodes,
    connections, settings). The workflow is created inactive; credentials
    referenced by id inside nodes are resolved by n8n itself.
    """

    name: str = Field(min_length=1, max_length=200)
    nodes: list[dict[str, Any]] = Field(min_length=1, max_length=200)
    connections: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class N8nExecutionDetailOut(N8nExecutionOut):
    node_statuses: list[N8nNodeStatusOut] = []
