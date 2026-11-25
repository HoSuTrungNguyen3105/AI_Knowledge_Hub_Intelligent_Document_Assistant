"""Schemas for the AI Model & Agent Evaluation Center.

Datasets hold test cases with explicit scoring criteria; runs execute a
dataset against one or more model targets (or, later, an agent) and store
per-case results plus per-target summaries. Scores come from deterministic
criteria (exact/contains/regex/JSON validity/token similarity) or from an
optional LLM judge whose score is always labelled as a judge score, never
as ground truth.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = (
    "general",
    "qa",
    "coding",
    "rag",
    "tool_calling",
    "multi_agent",
    "workflow",
    "support",
    "structured",
    "vietnamese",
)

CriterionType = Literal["exact", "contains", "regex", "json_valid", "similarity"]


class CriterionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: CriterionType
    value: str = Field(default="", max_length=2000)
    threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class EvalCaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str = Field(min_length=1, max_length=8000)
    expected_output: str = Field(default="", max_length=4000)
    expected_behavior: str = Field(default="", max_length=2000)
    criteria: list[CriterionIn] = Field(default_factory=list, max_length=5)
    ground_truth: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=8)
    metadata: dict = Field(default_factory=dict)


class EvalCaseOut(EvalCaseIn):
    id: str


class DatasetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="general", max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=8)
    cases: list[EvalCaseIn] = Field(default_factory=list, max_length=200)


class DatasetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = Field(default=None, max_length=8)
    cases: list[EvalCaseIn] | None = Field(default=None, max_length=200)


class DatasetSummary(BaseModel):
    id: UUID
    name: str
    description: str
    category: str
    tags: list[str]
    version: int
    case_count: int
    created_at: datetime
    updated_at: datetime


class DatasetOut(DatasetSummary):
    cases: list[EvalCaseOut]


class DatasetList(BaseModel):
    datasets: list[DatasetSummary]


class DatasetImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["json", "csv"]
    content: str = Field(min_length=1, max_length=1_000_000)
    name: str = Field(default="", max_length=120)
    category: str = Field(default="general", max_length=40)


class DatasetExportOut(BaseModel):
    filename: str
    content: str


class EvalTargetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=200)


class JudgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=200)


class PromptSetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    template: str = Field(min_length=1, max_length=8000)


class PromptSetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    template: str | None = Field(default=None, min_length=1, max_length=8000)


class PromptVersionOut(BaseModel):
    version: int
    template: str
    created_at: datetime


class PromptSetOut(BaseModel):
    id: UUID
    name: str
    versions: list[PromptVersionOut]
    created_at: datetime
    updated_at: datetime


class PromptSetList(BaseModel):
    prompts: list[PromptSetOut]


class RunCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=120)
    dataset_id: UUID
    kind: Literal["model", "prompt", "agent"] = "model"
    targets: list[EvalTargetIn] = Field(default_factory=list, max_length=5)
    agent_id: UUID | None = None
    prompt_id: UUID | None = None
    prompt_version: int | None = None
    judge: JudgeIn | None = None
    pass_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    case_timeout_seconds: int = Field(default=120, ge=10, le=600)


class CriterionScore(BaseModel):
    type: str
    score: float
    passed: bool
    detail: str = ""


class CaseResultOut(BaseModel):
    case_id: str
    case_index: int
    target_key: str
    output: str
    status: str
    error_code: str | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    scores: list[CriterionScore] = Field(default_factory=list)
    score: float | None = None
    judge_score: float | None = None
    judge_reason: str = ""
    passed: bool
    trace: dict = Field(default_factory=dict)


class TargetSummaryOut(BaseModel):
    target_key: str
    total: int
    passed: int
    pass_rate: float
    accuracy: float | None = None
    avg_latency_ms: float | None = None
    avg_tokens: float | None = None
    total_cost: float | None = None
    errors: int


class RunOut(BaseModel):
    id: UUID
    name: str
    kind: str
    dataset_id: UUID
    dataset_name: str
    dataset_version: int
    targets: list[EvalTargetIn]
    agent_id: UUID | None = None
    agent_name: str = ""
    prompt_id: UUID | None = None
    prompt_name: str = ""
    prompt_version: int | None = None
    judge: JudgeIn | None = None
    status: str
    progress_done: int
    progress_total: int
    results: list[CaseResultOut]
    summaries: list[TargetSummaryOut]
    is_baseline: bool
    error_code: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class RunSummaryOut(BaseModel):
    id: UUID
    name: str
    kind: str
    dataset_id: UUID
    dataset_name: str
    status: str
    is_baseline: bool
    pass_rate: float | None = None
    accuracy: float | None = None
    created_at: datetime
    finished_at: datetime | None = None


class RunList(BaseModel):
    runs: list[RunSummaryOut]


class AffectedCase(BaseModel):
    case_id: str
    case_index: int
    target_key: str
    change: str
    baseline_score: float | None = None
    current_score: float | None = None


class RunComparisonOut(BaseModel):
    baseline: RunSummaryOut
    current: RunSummaryOut
    accuracy_delta: float | None = None
    pass_rate_delta: float | None = None
    latency_delta_ms: float | None = None
    cost_delta: float | None = None
    regression_detected: bool
    affected_cases: list[AffectedCase]


class OverviewPoint(BaseModel):
    run_id: UUID
    name: str
    kind: str
    created_at: datetime
    accuracy: float | None = None
    pass_rate: float | None = None
    avg_latency_ms: float | None = None
    total_cost: float | None = None


class OverviewOut(BaseModel):
    total_evaluations: int
    total_models_tested: int
    total_agents_evaluated: int
    total_datasets: int
    avg_accuracy: float | None = None
    avg_latency_ms: float | None = None
    avg_tokens: float | None = None
    avg_cost: float | None = None
    pass_rate: float | None = None
    failure_rate: float | None = None
    regression_runs: int
    series: list[OverviewPoint]
