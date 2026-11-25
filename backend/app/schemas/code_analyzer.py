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
