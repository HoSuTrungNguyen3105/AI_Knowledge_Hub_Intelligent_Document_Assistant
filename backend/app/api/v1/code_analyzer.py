"""Codebase Architecture Analyzer routes (PROJECT_SPEC.md).

Mounted under /api/v1/ai/code-analyzer; the spec's /api/code-analyzer
paths map onto the codebase's /api/v1/ai prefix like every other AI
module. Uploads are analyzed directly in the backend with the
caller's own configured provider; the webhook callback remains as an
optional external path (n8n) and is the one unauthenticated route —
it checks the shared x-mindflow-secret header instead of a session.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.code_analyzer import (
    CodeCallbackIn,
    CodeCallbackOut,
    CodeFileDetail,
    CodeProjectDetail,
    CodeProjectList,
    SeedDemoOut,
    UploadOut,
)
from app.services.ai.chat import ChatHTTP
from app.services.code_analyzer import CodeAnalyzerService

router = APIRouter(prefix="/ai/code-analyzer", tags=["Code Analyzer"])


def analyzer_http() -> ChatHTTP:
    """Shared outbound HTTP client for provider calls (test seam)."""
    return ChatHTTP()


AnalyzerHTTPDep = Annotated[ChatHTTP, Depends(analyzer_http)]


def _service(db, settings, chat_http=None) -> CodeAnalyzerService:
    return CodeAnalyzerService(db, settings, chat_http)


@router.get("/projects", response_model=CodeProjectList)
async def list_projects(user: CurrentUser, db: Database, settings: AppSettings):
    """The caller's own projects plus the public demo projects."""
    projects = await _service(db, settings).list_projects(user.id)
    return CodeProjectList(projects=projects)


@router.post("/seed-demo", response_model=SeedDemoOut)
async def seed_demo(user: CurrentUser, db: Database, settings: AppSettings):
    """Create the shared public demo project once (dev/demo only)."""
    return await _service(db, settings).seed_demo(user.id)


@router.post("/upload", response_model=UploadOut, status_code=201)
async def upload(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    chat_http: AnalyzerHTTPDep,
    file: UploadFile = File(...),
    provider: str = Form(""),
    model: str = Form(""),
):
    """Ingest a ZIP: filter junk, statically parse imports, store the
    project, then summarize files directly with the caller's provider
    (explicit provider/model form fields, else the first configured
    one)."""
    data = await file.read()
    return await _service(db, settings, chat_http).ingest_upload(
        user.id,
        file.filename or "codebase.zip",
        data,
        provider=provider or None,
        model=model or None,
    )


@router.post("/webhook/callback", response_model=CodeCallbackOut)
async def webhook_callback(
    payload: CodeCallbackIn,
    db: Database,
    settings: AppSettings,
    x_mindflow_secret: str | None = Header(default=None),
):
    """Receive per-file AI results from an external (n8n) workflow."""
    return await _service(db, settings).apply_callback(x_mindflow_secret, payload)


@router.post(
    "/projects/{project_id}/report", response_model=UploadOut
)
async def regenerate_report(
    project_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    chat_http: AnalyzerHTTPDep,
    provider: str = Form(""),
    model: str = Form(""),
):
    """(Re)write the whole-project Markdown report with the caller's
    provider, using the excerpts stored at upload time."""
    return await _service(db, settings, chat_http).regenerate_report(
        user.id, project_id, provider=provider or None, model=model or None
    )


@router.get("/projects/{project_id}", response_model=CodeProjectDetail)
async def get_project(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
):
    return await _service(db, settings).get_project(user.id, project_id)


@router.get(
    "/projects/{project_id}/files/{file_id}", response_model=CodeFileDetail
)
async def get_file(
    project_id: UUID,
    file_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
):
    return await _service(db, settings).get_file(user.id, project_id, file_id)
