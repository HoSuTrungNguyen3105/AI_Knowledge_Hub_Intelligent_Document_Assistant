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
    has_report: bool = False
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
    ai_summary: str = ""
    imports: list[CodeImport] = Field(default_factory=list)
    imported_by: list[str] = Field(default_factory=list)


class CodeProjectDetail(CodeProjectSummary):
    diagram_data: dict = Field(default_factory=dict)
    files: list[CodeFileSummary] = Field(default_factory=list)
    # One long AI-written Markdown report for the whole project (page /
    # feature -> file mapping included); empty when no provider ran.
    report_markdown: str = ""


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
    # ai: the direct in-backend AI pass wrote the project's Markdown
    # report with the caller's own provider; static: no provider was
    # available (or the call failed), so the project has static data
    # only. ai_analyzed counts the files the report was based on.
    analysis_dispatch: str = "static"
    ai_analyzed: int = 0
    # Classified provider error code when a target was prepared but the
    # report call failed ("" when no call was made or it succeeded), so
    # the UI can say WHY there is no report instead of guessing.
    ai_error: str = ""


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
