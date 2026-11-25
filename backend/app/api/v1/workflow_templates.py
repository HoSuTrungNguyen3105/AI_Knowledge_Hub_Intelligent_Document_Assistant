"""Workflow Template Library endpoints (phase 1: GitHub importer).

Prefix: ``/ai/workflow-templates``. All endpoints require a signed-in user.
Importing reads a public GitHub repository and stores analysed templates in
the shared library as ``pending_review``; nothing is executed or installed
into n8n here — that stays with the n8n Platform layer, by user choice.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import AppSettings, CurrentUser, Database
from app.schemas.workflow_templates import (
    TemplateDetailOut,
    TemplateImportLogOut,
    TemplateListOut,
    TemplateReviewIn,
    TemplateSourceCreateIn,
    TemplateSourceOut,
    TemplateSummaryOut,
)
from app.services.workflow_templates import GitHubHTTP, WorkflowTemplateService

router = APIRouter(prefix="/ai/workflow-templates", tags=["workflow-templates"])


def github_http() -> GitHubHTTP:
    return GitHubHTTP()


GitHubHTTPDep = Annotated[GitHubHTTP, Depends(github_http)]


@router.get("/sources", response_model=list[TemplateSourceOut])
async def list_template_sources(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> list[TemplateSourceOut]:
    return await WorkflowTemplateService(db, settings, http).list_sources()


@router.post("/sources", response_model=TemplateSourceOut, status_code=201)
async def create_template_source(
    payload: TemplateSourceCreateIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateSourceOut:
    return await WorkflowTemplateService(db, settings, http).create_source(payload)


@router.post("/sources/default", response_model=TemplateSourceOut)
async def ensure_default_template_source(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateSourceOut:
    """Register the default awesome-n8n-templates source if missing."""
    return await WorkflowTemplateService(db, settings, http).ensure_default_source()


@router.post("/sources/{source_id}/import", response_model=TemplateImportLogOut)
async def import_template_source(
    source_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateImportLogOut:
    """Fetch, analyse and upsert every workflow JSON of the source.

    Idempotent: unchanged files are counted, changed files bump the
    template version, new files are created as pending_review.
    """
    return await WorkflowTemplateService(db, settings, http).import_source(source_id)


@router.get("/imports", response_model=list[TemplateImportLogOut])
async def list_template_imports(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
    source_id: str | None = None,
    limit: int = 20,
) -> list[TemplateImportLogOut]:
    return await WorkflowTemplateService(db, settings, http).list_import_logs(
        source_id=source_id, limit=limit
    )


@router.get("/templates", response_model=TemplateListOut)
async def list_templates(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
    q: str | None = None,
    category: str | None = None,
    source_id: str | None = None,
    review_status: str | None = None,
    compatibility: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> TemplateListOut:
    return await WorkflowTemplateService(db, settings, http).list_templates(
        q=q,
        category=category,
        source_id=source_id,
        review_status=review_status,
        compatibility=compatibility,
        limit=limit,
        offset=offset,
    )


@router.get("/templates/{template_id}", response_model=TemplateDetailOut)
async def get_template(
    template_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateDetailOut:
    return await WorkflowTemplateService(db, settings, http).get_template(template_id)


@router.patch("/templates/{template_id}/review", response_model=TemplateSummaryOut)
async def review_template(
    template_id: str,
    payload: TemplateReviewIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateSummaryOut:
    return await WorkflowTemplateService(db, settings, http).review_template(
        template_id, payload
    )
