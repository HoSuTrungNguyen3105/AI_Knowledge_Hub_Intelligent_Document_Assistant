"""Schemas for the Workflow Studio conversion layer (Phase 4).

The Studio graph is MindFlow's own intermediate representation. Only
node types present in the catalog have schemas/adapters; anything else
travels as a ``raw`` node so it is preserved verbatim, never dropped.
"""

from typing import Any

from pydantic import BaseModel, Field


class StudioParamOut(BaseModel):
    name: str
    label: str
    type: str  # string | number | boolean | json | options
    required: bool = False
    default: Any = None
    options: list[str] = Field(default_factory=list)


class StudioNodeTypeOut(BaseModel):
    type: str
    display_name: str
    category: str
    type_version: float
    parameters: list[StudioParamOut] = Field(default_factory=list)


class StudioCatalogOut(BaseModel):
    node_types: list[StudioNodeTypeOut]


class StudioGraphNodeIn(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=200)
    position: list[float] = Field(default_factory=lambda: [0, 0])
    parameters: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None


class StudioEdgeIn(BaseModel):
    from_node: str
    to_node: str
    output_index: int = 0


class StudioGraphIn(BaseModel):
    name: str = Field(default="Workflow mới", max_length=200)
    nodes: list[StudioGraphNodeIn] = Field(min_length=1, max_length=200)
    edges: list[StudioEdgeIn] = Field(default_factory=list)


class StudioConvertOut(BaseModel):
    workflow_json: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class StudioParseIn(BaseModel):
    workflow_json: dict[str, Any]


class StudioGraphNodeOut(BaseModel):
    id: str
    name: str
    type: str
    position: list[float] = Field(default_factory=lambda: [0, 0])
    parameters: dict[str, Any] = Field(default_factory=dict)
    supported: bool = True
    raw: dict[str, Any] | None = None


class StudioGraphOut(BaseModel):
    name: str = ""
    nodes: list[StudioGraphNodeOut] = Field(default_factory=list)
    edges: list[StudioEdgeIn] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)
