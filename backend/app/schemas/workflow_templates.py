"""Workflow Template Library schemas (phase 1: GitHub importer).

A template is a real n8n workflow JSON collected from a configured source
(a GitHub repository), analysed and security-scanned at import time, and
stored in the shared library with a review status. Nothing here executes a
template; installing/running stays with the n8n Platform layer.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_SOURCE_REPO = "enescingoz/awesome-n8n-templates"
DEFAULT_SOURCE_NAME = "awesome-n8n-templates (GitHub)"
DEFAULT_SOURCE_LICENSE = "CC BY 4.0"
DEFAULT_SOURCE_ATTRIBUTION = (
    "Workflow templates collected from github.com/enescingoz/awesome-n8n-templates "
    "by Enes Cingoz, licensed under CC BY 4.0."
)


class TemplateSourceCreateIn(BaseModel):
    repo_url: str = Field(min_length=1, max_length=300)
    branch: str = Field(default="main", min_length=1, max_length=100)
    name: str = Field(default="", max_length=200)


class TemplateSourceOut(BaseModel):
    id: str
    name: str
    kind: str = "github"
    repo: str  # "owner/repo"
    repo_url: str
    branch: str = "main"
    license: str = ""
    attribution: str = ""
    template_count: int = 0
    last_import_at: datetime | None = None
    created_at: datetime


class TemplateImportLogOut(BaseModel):
    id: str
    source_id: str
    source_repo: str
    status: str  # completed | failed
    found: int = 0
    downloaded: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    failures: list[dict[str, str]] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class TemplateSummaryOut(BaseModel):
    id: str
    name: str
    category: str
    source_kind: str  # github | official | community | personal
    source_id: str | None = None
    source_path: str | None = None
    source_url: str | None = None
    node_count: int = 0
    node_types: list[str] = Field(default_factory=list)
    credential_types: list[str] = Field(default_factory=list)
    complexity: str = "simple"  # simple | medium | complex
    compatibility: str = "compatible"  # compatible | needs_community_nodes
    community_nodes: list[str] = Field(default_factory=list)
    security_flag: bool = False
    risk_flags: list[str] = Field(default_factory=list)
    review_status: str = "pending_review"  # pending_review | approved | rejected
    version: int = 1
    license: str = ""
    attribution: str = ""
    updated_at: datetime


class TemplateDetailOut(TemplateSummaryOut):
    description: str = ""
    has_code_node: bool = False
    has_http_node: bool = False
    http_urls: list[str] = Field(default_factory=list)
    workflow_json: dict[str, Any] = Field(default_factory=dict)


class TemplateListOut(BaseModel):
    items: list[TemplateSummaryOut]
    total: int


class TemplateReviewIn(BaseModel):
    review_status: str = Field(pattern="^(approved|rejected|pending_review)$")


class TemplateVersionOut(BaseModel):
    version: int
    content_hash: str
    node_count: int = 0
    created_at: datetime


class TemplateVersionDetailOut(TemplateVersionOut):
    workflow_json: dict[str, Any] = Field(default_factory=dict)


class TemplateNodeChangeOut(BaseModel):
    name: str
    changed_fields: list[str] = Field(default_factory=list)


class TemplateDiffOut(BaseModel):
    from_version: int
    to_version: int
    nodes_added: list[str] = Field(default_factory=list)
    nodes_removed: list[str] = Field(default_factory=list)
    nodes_changed: list[TemplateNodeChangeOut] = Field(default_factory=list)
    connections_changed: bool = False


class ContributeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="Community", max_length=120)
    workflow_json: dict[str, Any]


class UserWorkflowOut(BaseModel):
    id: str
    template_id: str
    template_name: str
    category: str = ""
    n8n_workflow_id: str
    installed_version: int
    latest_version: int
    update_available: bool = False
    installed_at: datetime
    updated_at: datetime


class InstallIn(BaseModel):
    template_ids: list[str] = Field(min_length=1, max_length=50)


class InstallResultItemOut(BaseModel):
    template_id: str
    template_name: str = ""
    status: str  # installed | already_installed | failed
    error: str | None = None
    n8n_workflow_id: str | None = None


class InstallResultOut(BaseModel):
    results: list[InstallResultItemOut]


class SyncCandidatesOut(BaseModel):
    available: list[TemplateSummaryOut] = Field(default_factory=list)
    updates: list[UserWorkflowOut] = Field(default_factory=list)


class TemplateStatsOut(BaseModel):
    total: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    by_review_status: dict[str, int] = Field(default_factory=dict)
    by_compatibility: dict[str, int] = Field(default_factory=dict)
    services: list[str] = Field(default_factory=list)
