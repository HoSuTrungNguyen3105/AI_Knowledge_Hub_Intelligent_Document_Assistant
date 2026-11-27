from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.n8n_factory import FactoryRunRequest

SCHEDULE_TYPES = "^(once|daily|weekly|monthly|interval|cron)$"


class ScheduleTarget(BaseModel):
    """What a firing launches.

    ``factory`` (the original behaviour, and the default for every
    schedule stored before targets existed) fires the AI Factory
    request (workflow 07) through :class:`FactoryRunRequest`.
    ``n8n_workflow`` starts any synced n8n workflow through the n8n
    Platform run path, with ``payload`` as the webhook body.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="factory", pattern="^(factory|n8n_workflow)$")
    workflow_id: str | None = Field(default=None, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class ScheduleConfigIn(BaseModel):
    """Timing fields; which ones matter depends on ``schedule_type``.

    once: run_at · daily: hour/minute · weekly: weekdays + hour/minute ·
    monthly: day_of_month + hour/minute · interval: every + unit.
    """

    model_config = ConfigDict(extra="forbid")

    run_at: datetime | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    minute: int | None = Field(default=None, ge=0, le=59)
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    every: int | None = Field(default=None, ge=1, le=10080)
    unit: str | None = Field(default=None, pattern="^(minutes|hours)$")

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: list[int]) -> list[int]:
        for day in value:
            if not 1 <= day <= 7:
                raise ValueError("weekdays use ISO numbering 1 (Mon) to 7 (Sun)")
        return sorted(set(value))


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    # Required when the target kind is "factory" (enforced by the
    # service with a coded error); unused for "n8n_workflow" targets.
    factory_request: FactoryRunRequest | None = None
    target: ScheduleTarget = Field(default_factory=ScheduleTarget)
    schedule_type: str = Field(pattern=SCHEDULE_TYPES)
    cron_expression: str | None = Field(default=None, max_length=120)
    config: ScheduleConfigIn = Field(default_factory=ScheduleConfigIn)
    timezone: str = Field(default="Asia/Ho_Chi_Minh", min_length=1, max_length=64)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: str = Field(default="active", pattern="^(active|paused)$")
    concurrency_policy: str = Field(
        default="skip", pattern="^(skip|queue|allow_parallel)$"
    )
    notify_on_success: bool = False
    notify_on_failure: bool = True
    max_runs: int | None = Field(default=None, ge=1, le=100000)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must not be blank")
        return value


class SchedulePatch(BaseModel):
    """Partial update; ``config`` replaces the stored timing config whole."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    factory_request: FactoryRunRequest | None = None
    target: ScheduleTarget | None = None
    schedule_type: str | None = Field(default=None, pattern=SCHEDULE_TYPES)
    cron_expression: str | None = Field(default=None, max_length=120)
    config: ScheduleConfigIn | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    start_at: datetime | None = None
    end_at: datetime | None = None
    concurrency_policy: str | None = Field(
        default=None, pattern="^(skip|queue|allow_parallel)$"
    )
    notify_on_success: bool | None = None
    notify_on_failure: bool | None = None
    max_runs: int | None = Field(default=None, ge=1, le=100000)


class SchedulePreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_type: str = Field(pattern=SCHEDULE_TYPES)
    cron_expression: str | None = Field(default=None, max_length=120)
    config: ScheduleConfigIn = Field(default_factory=ScheduleConfigIn)
    timezone: str = Field(default="Asia/Ho_Chi_Minh", min_length=1, max_length=64)
    start_at: datetime | None = None
    end_at: datetime | None = None


class ScheduleOut(BaseModel):
    id: UUID
    name: str
    description: str
    factory_request: FactoryRunRequest | None
    target: ScheduleTarget = Field(default_factory=ScheduleTarget)
    schedule_type: str
    cron_expression: str | None
    config: ScheduleConfigIn
    timezone: str
    start_at: datetime | None
    end_at: datetime | None
    status: str
    concurrency_policy: str
    notify_on_success: bool
    notify_on_failure: bool
    max_runs: int | None
    run_count: int
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    description_text: str
    created_at: datetime
    updated_at: datetime


class ScheduleStats(BaseModel):
    total: int
    active: int
    paused: int
    completed: int


class ScheduleListOut(BaseModel):
    items: list[ScheduleOut]
    total: int
    stats: ScheduleStats


class SchedulePreviewOut(BaseModel):
    description_text: str
    next_runs: list[datetime]
    warnings: list[str]


class ScheduleNextRunsOut(BaseModel):
    next_runs: list[datetime]


class ScheduleExecutionOut(BaseModel):
    id: UUID
    schedule_id: UUID
    factory_run_id: UUID | None
    # Set instead of factory_run_id when the schedule's target is an
    # n8n Platform run (target kind "n8n_workflow").
    platform_run_id: str | None = None
    trigger_type: str
    scheduled_for: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    status: str
    duration_ms: int | None
    error: str | None
    created_at: datetime


class ScheduleExecutionListOut(BaseModel):
    items: list[ScheduleExecutionOut]
    total: int


class ScheduleTickOut(BaseModel):
    fired: int
    skipped: int
    deferred: int
    synced: int


class ScheduleHealthOut(BaseModel):
    """Health of the firing chain, from data the backend actually has.

    ``external_tick_configured`` only says whether the tick secret is
    set on this server — never its value. ``last_tick_at`` is the most
    recent tick this backend recorded (in-process loop or external
    cron); None means no tick has been recorded since the state was
    first tracked. n8n reachability mirrors the platform status check;
    ``n8n_reachable`` is None when n8n is not configured at all.
    """

    external_tick_configured: bool
    last_tick_at: datetime | None = None
    # "external" (cron POST) | "loop" (in-process) | None (never ticked)
    last_tick_source: str | None = None
    n8n_configured: bool
    n8n_reachable: bool | None = None
    n8n_error: str | None = None
    checked_at: datetime
