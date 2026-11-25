from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.evaluation import (
    DatasetExportOut,
    DatasetImportIn,
    DatasetIn,
    DatasetList,
    DatasetOut,
    DatasetPatch,
    OverviewOut,
    PromptSetIn,
    PromptSetList,
    PromptSetOut,
    PromptSetPatch,
    RunComparisonOut,
    RunCreateIn,
    RunList,
    RunOut,
)
from app.services.ai.chat import ChatHTTP
from app.services.evaluation import EvaluationService

router = APIRouter(prefix="/ai/evaluations", tags=["AI evaluations"])


def eval_http() -> ChatHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return ChatHTTP()


EvalHTTPDep = Annotated[ChatHTTP, Depends(eval_http)]


@router.get("/overview", response_model=OverviewOut)
async def overview(
    user: CurrentUser, db: Database, settings: AppSettings
) -> OverviewOut:
    return await EvaluationService(db, settings).overview(user.id)


@router.get("/datasets", response_model=DatasetList)
async def list_datasets(
    user: CurrentUser, db: Database, settings: AppSettings
) -> DatasetList:
    return await EvaluationService(db, settings).list_datasets(user.id)


@router.post("/datasets", response_model=DatasetOut, status_code=201)
async def create_dataset(
    payload: DatasetIn, user: CurrentUser, db: Database, settings: AppSettings
) -> DatasetOut:
    return await EvaluationService(db, settings).create_dataset(user.id, payload)


@router.post("/datasets/import", response_model=DatasetOut, status_code=201)
async def import_dataset(
    payload: DatasetImportIn, user: CurrentUser, db: Database, settings: AppSettings
) -> DatasetOut:
    return await EvaluationService(db, settings).import_dataset(user.id, payload)


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
async def get_dataset(
    dataset_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> DatasetOut:
    return await EvaluationService(db, settings).get_dataset(user.id, dataset_id)


@router.patch("/datasets/{dataset_id}", response_model=DatasetOut)
async def update_dataset(
    dataset_id: UUID,
    payload: DatasetPatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> DatasetOut:
    return await EvaluationService(db, settings).update_dataset(
        user.id, dataset_id, payload
    )


@router.delete("/datasets/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    await EvaluationService(db, settings).delete_dataset(user.id, dataset_id)
    return Response(status_code=204)


@router.get("/datasets/{dataset_id}/export", response_model=DatasetExportOut)
async def export_dataset(
    dataset_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> DatasetExportOut:
    return await EvaluationService(db, settings).export_dataset(user.id, dataset_id)


@router.get("/prompts", response_model=PromptSetList)
async def list_prompts(
    user: CurrentUser, db: Database, settings: AppSettings
) -> PromptSetList:
    return await EvaluationService(db, settings).list_prompts(user.id)


@router.post("/prompts", response_model=PromptSetOut, status_code=201)
async def create_prompt(
    payload: PromptSetIn, user: CurrentUser, db: Database, settings: AppSettings
) -> PromptSetOut:
    return await EvaluationService(db, settings).create_prompt(user.id, payload)


@router.patch("/prompts/{prompt_id}", response_model=PromptSetOut)
async def update_prompt(
    prompt_id: UUID,
    payload: PromptSetPatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> PromptSetOut:
    return await EvaluationService(db, settings).update_prompt(
        user.id, prompt_id, payload
    )


@router.delete("/prompts/{prompt_id}", status_code=204)
async def delete_prompt(
    prompt_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    await EvaluationService(db, settings).delete_prompt(user.id, prompt_id)
    return Response(status_code=204)


@router.get("/runs/compare", response_model=RunComparisonOut)
async def compare_runs(
    baseline_id: UUID,
    current_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> RunComparisonOut:
    return await EvaluationService(db, settings).compare_runs(
        user.id, baseline_id, current_id
    )


@router.get("/runs", response_model=RunList)
async def list_runs(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    kind: str | None = Query(default=None),
    dataset_id: UUID | None = Query(default=None),
) -> RunList:
    return await EvaluationService(db, settings).list_runs(user.id, kind, dataset_id)


@router.post("/runs", response_model=RunOut, status_code=201)
async def create_run(
    payload: RunCreateIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: EvalHTTPDep,
) -> RunOut:
    return await EvaluationService(db, settings, http).create_run(user.id, payload)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> RunOut:
    return await EvaluationService(db, settings).get_run(user.id, run_id)


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(
    run_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> RunOut:
    return await EvaluationService(db, settings).cancel_run(user.id, run_id)


@router.post("/runs/{run_id}/baseline", response_model=RunOut)
async def set_baseline(
    run_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> RunOut:
    return await EvaluationService(db, settings).set_baseline(user.id, run_id)
