from pydantic import BaseModel, ConfigDict, Field


class SeedApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional explicit target. When omitted, the seed uses the caller's
    # first enabled + connected provider and its default model (or the
    # first synced model that is not explicitly non-chat).
    provider: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=512)


class SeedStatusOut(BaseModel):
    enabled: bool
    app_env: str
    seeded: bool
    demo_agents: int
    demo_teams: int


class SeedApplyOut(BaseModel):
    created_agents: list[str]
    reused_agents: list[str]
    created_teams: list[str]
    skipped_teams: list[str]


class SeedRemoveOut(BaseModel):
    removed_agents: int
    removed_teams: int
    kept_agents: list[str]


class WorkforceSeedOut(BaseModel):
    created: int
    skipped: int
    total: int


class WorkforceSeedRemoveOut(BaseModel):
    removed: int
