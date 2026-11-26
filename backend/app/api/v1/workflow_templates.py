"""Workflow Template Library endpoints (phase 1: GitHub importer).

Prefix: ``/ai/workflow-templates``. All endpoints require a signed-in user.
Importing reads a public GitHub repository and stores analysed templates in
the shared library as ``pending_review``; nothing is executed or installed
into n8n here — that stays with the n8n Platform layer, by user choice.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.n8n_platform import N8nApiHTTPDep
from app.schemas.workflow_templates import (
    AssistantApplyIn,
    AssistantIn,
    AssistantOut,
    ContributeIn,
    InstallIn,
    TemplateDiffOut,
    TemplateVersionDetailOut,
    TemplateVersionOut,
    InstallResultOut,
    SyncCandidatesOut,
    TemplateDetailOut,
    TemplateImportLogOut,
    TemplateListOut,
    TemplateReviewIn,
    TemplateSourceCreateIn,
    TemplateSourceOut,
    TemplateStatsOut,
    TemplateSummaryOut,
    UserWorkflowOut,
)
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.n8n_platform import N8nPlatformService
from app.services.template_assistant import TemplateAssistantService
from app.services.workflow_templates import (
    GitHubHTTP,
    WorkflowSyncService,
    WorkflowTemplateService,
)

router = APIRouter(prefix="/ai/workflow-templates", tags=["workflow-templates"])


def github_http() -> GitHubHTTP:
    return GitHubHTTP()


GitHubHTTPDep = Annotated[GitHubHTTP, Depends(github_http)]


def assistant_http() -> ChatHTTP:
    """Shared outbound HTTP client for provider calls (test seam)."""
    return ChatHTTP()


AssistantHTTPDep = Annotated[ChatHTTP, Depends(assistant_http)]


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


@router.get("/templates/stats", response_model=TemplateStatsOut)
async def template_stats(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateStatsOut:
    return await WorkflowTemplateService(db, settings, http).template_stats()


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
    complexity: str | None = None,
    service: str | None = None,
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
) -> TemplateListOut:
    return await WorkflowTemplateService(db, settings, http).list_templates(
        q=q,
        category=category,
        source_id=source_id,
        review_status=review_status,
        compatibility=compatibility,
        complexity=complexity,
        service=service,
        sort=sort,
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


# -- Phase 6: versioning & community -----------------------------------------


@router.post("/templates/contribute", response_model=TemplateDetailOut, status_code=201)
async def contribute_template(
    payload: ContributeIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateDetailOut:
    return await WorkflowTemplateService(db, settings, http).contribute(user.id, payload)


@router.get("/templates/{template_id}/versions", response_model=list[TemplateVersionOut])
async def list_template_versions(
    template_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> list[TemplateVersionOut]:
    return await WorkflowTemplateService(db, settings, http).list_versions(template_id)


@router.get(
    "/templates/{template_id}/versions/{version}",
    response_model=TemplateVersionDetailOut,
)
async def get_template_version(
    template_id: str,
    version: int,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateVersionDetailOut:
    return await WorkflowTemplateService(db, settings, http).get_version(template_id, version)


@router.get("/templates/{template_id}/diff", response_model=TemplateDiffOut)
async def diff_template_versions(
    template_id: str,
    from_version: int,
    to_version: int,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateDiffOut:
    return await WorkflowTemplateService(db, settings, http).diff_versions(
        template_id, from_version, to_version
    )


@router.post(
    "/templates/{template_id}/versions/{version}/restore",
    response_model=TemplateDetailOut,
)
async def restore_template_version(
    template_id: str,
    version: int,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
) -> TemplateDetailOut:
    return await WorkflowTemplateService(db, settings, http).restore_version(
        template_id, version
    )


# -- Phase 5: AI template assistant -------------------------------------------


@router.post("/templates/{template_id}/assistant", response_model=AssistantOut)
async def ask_template_assistant(
    template_id: str,
    payload: AssistantIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
    chat_http: AssistantHTTPDep,
) -> AssistantOut:
    template = await WorkflowTemplateService(db, settings, http).get_template(template_id)
    return await TemplateAssistantService(db, settings, chat_http).ask(
        user.id, template, payload
    )


@router.post(
    "/templates/{template_id}/assistant/apply", response_model=UserWorkflowOut, status_code=201
)
async def apply_template_proposal(
    template_id: str,
    payload: AssistantApplyIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
    n8n_http: N8nApiHTTPDep,
) -> UserWorkflowOut:
    service = WorkflowTemplateService(db, settings, http)
    template = await service.templates.find_one({"_id": template_id})
    if template is None:
        raise ProviderError("template_not_found")
    analysis = analyze_workflow(
        json.dumps(payload.workflow_json, ensure_ascii=False), "proposal.json"
    )
    if "rejected" in analysis:
        raise ProviderError("template_contribute_invalid")
    return await _sync_service(db, settings, n8n_http).install_custom(
        user.id, template, payload.workflow_json, payload.name
    )


# -- Phase 3: per-user sync ---------------------------------------------------
# These endpoints compose the template service with the n8n Platform
# service: installing a template creates the workflow in the user's n8n
# through the exact same create path as the platform tab.


def _sync_service(db: Database, settings: AppSettings, n8n_http) -> WorkflowSyncService:
    return WorkflowSyncService(db, N8nPlatformService(db, settings, n8n_http))


@router.get("/mine", response_model=list[UserWorkflowOut])
async def list_my_workflows(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
    n8n_http: N8nApiHTTPDep,
) -> list[UserWorkflowOut]:
    return await _sync_service(db, settings, n8n_http).list_mine(user.id)


@router.get("/sync-candidates", response_model=SyncCandidatesOut)
async def sync_candidates(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
    n8n_http: N8nApiHTTPDep,
) -> SyncCandidatesOut:
    return await _sync_service(db, settings, n8n_http).sync_candidates(user.id)


@router.post("/install", response_model=InstallResultOut)
async def install_templates(
    payload: InstallIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
    n8n_http: N8nApiHTTPDep,
) -> InstallResultOut:
    return await _sync_service(db, settings, n8n_http).install(user.id, payload.template_ids)


@router.post("/mine/{install_id}/update", response_model=UserWorkflowOut)
async def update_my_workflow(
    install_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
    n8n_http: N8nApiHTTPDep,
) -> UserWorkflowOut:
    return await _sync_service(db, settings, n8n_http).update_install(user.id, install_id)


@router.delete("/mine/{install_id}", status_code=204)
async def remove_my_workflow(
    install_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: GitHubHTTPDep,
    n8n_http: N8nApiHTTPDep,
) -> None:
    await _sync_service(db, settings, n8n_http).remove_install(user.id, install_id)
    return None
