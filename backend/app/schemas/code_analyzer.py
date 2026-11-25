"""Codebase Architecture Analyzer contracts (PROJECT_SPEC.md).

A code project is one uploaded codebase; its files carry the static
import graph plus the AI summary/role that the n8n analysis later fills
in. Diagram data is prebuilt at ingest time so the UI renders instantly.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CodeImport(BaseModel):
    target_file: str = ""
    target_id: UUID | None = None
    relation_label: str = ""


class CodeProjectStats(BaseModel):
    total_raw_files: int = 0
    analyzed_files: int = 0
    primary_language: str = ""


class CodeProjectSummary(BaseModel):
    id: UUID
    name: str
    description: str = ""
    is_public_demo: bool = False
    status: str = "PROCESSING"
    stats: CodeProjectStats = Field(default_factory=CodeProjectStats)
    created_at: datetime
    updated_at: datetime


class CodeProjectList(BaseModel):
    projects: list[CodeProjectSummary]


class CodeFileSummary(BaseModel):
    id: UUID
    file_path: str
    file_name: str
    module_group: str = ""
    language: str = ""
    role_tag: str = ""
    import_count: int = 0
    imported_by_count: int = 0


class CodeProjectDetail(CodeProjectSummary):
    diagram_data: dict = Field(default_factory=dict)
    files: list[CodeFileSummary] = Field(default_factory=list)


class CodeFileDetail(BaseModel):
    id: UUID
    project_id: UUID
    file_path: str
    file_name: str
    module_group: str = ""
    language: str = ""
    ai_summary: str = ""
    role_tag: str = ""
    imports: list[CodeImport] = Field(default_factory=list)
    imported_by: list[str] = Field(default_factory=list)


class SeedDemoOut(BaseModel):
    created: bool
    project: CodeProjectSummary


class UploadOut(BaseModel):
    project: CodeProjectSummary
    # sent: batches delivered to the n8n webhook; skipped: webhook not
    # configured (project completed with static parsing only); failed:
    # delivery attempted but the webhook did not acknowledge.
    analysis_dispatch: str = "skipped"


class CodeCallbackFileIn(BaseModel):
    file_id: UUID | None = None
    file_path: str = Field(min_length=1, max_length=1000)
    ai_summary: str = Field(default="", max_length=4000)
    role_tag: str = Field(default="", max_length=80)
    imports: list[CodeImport] = Field(default_factory=list, max_length=100)


class CodeCallbackIn(BaseModel):
    project_id: UUID
    # completed | failed | processing (a non-final batch)
    status: str = Field(default="completed", max_length=20)
    files: list[CodeCallbackFileIn] = Field(default_factory=list, max_length=60)


class CodeCallbackOut(BaseModel):
    received: bool = True
    updated: int = 0
