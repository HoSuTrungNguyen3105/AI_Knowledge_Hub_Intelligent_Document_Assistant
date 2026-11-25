from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.n8n_factory import FactoryRunRequest

SCHEDULE_TYPES = "^(once|daily|weekly|monthly|interval|cron)$"


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
    factory_request: FactoryRunRequest
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
    factory_request: FactoryRunRequest
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
