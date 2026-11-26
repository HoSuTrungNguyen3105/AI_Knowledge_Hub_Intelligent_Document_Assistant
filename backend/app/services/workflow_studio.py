"""Workflow Studio conversion layer (Phase 4 of Project_Workflow_update.md).

Controlled conversion between the MindFlow Studio graph and n8n
workflow JSON:

    Studio graph -> validator -> n8n JSON -> n8n execution engine

Only node types in ``CATALOG`` have a schema and an adapter. A node of
any other type is carried as a raw node: its original n8n JSON is kept
verbatim through parse and convert, and it is reported in the
``unsupported`` list / warnings — never silently dropped or rewritten.
"""

from __future__ import annotations

import uuid

from app.schemas.workflow_studio import (
    StudioCatalogOut,
    StudioConvertOut,
    StudioEdgeIn,
    StudioGraphIn,
    StudioGraphNodeOut,
    StudioGraphOut,
    StudioNodeTypeOut,
    StudioParamOut,
)
from app.services.ai.base_provider import ProviderError


def _param(name, label, type_, required=False, default=None, options=None):
    return StudioParamOut(
        name=name,
        label=label,
        type=type_,
        required=required,
        default=default,
        options=options or [],
    )


CATALOG: dict[str, StudioNodeTypeOut] = {
    "n8n-nodes-base.manualTrigger": StudioNodeTypeOut(
        type="n8n-nodes-base.manualTrigger",
        display_name="Manual Trigger",
        category="Trigger",
        type_version=1,
        parameters=[],
    ),
    "n8n-nodes-base.webhook": StudioNodeTypeOut(
        type="n8n-nodes-base.webhook",
        display_name="Webhook Trigger",
        category="Trigger",
        type_version=2,
        parameters=[
            _param("path", "Đường dẫn webhook", "string", required=True),
            _param(
                "httpMethod",
                "Phương thức HTTP",
                "options",
                default="GET",
                options=["GET", "POST", "PUT", "DELETE", "PATCH"],
            ),
        ],
    ),
    "n8n-nodes-base.scheduleTrigger": StudioNodeTypeOut(
        type="n8n-nodes-base.scheduleTrigger",
        display_name="Schedule Trigger",
        category="Trigger",
        type_version=1.2,
        parameters=[
            _param("rule", "Quy tắc lịch (JSON)", "json", required=True),
        ],
    ),
    "n8n-nodes-base.httpRequest": StudioNodeTypeOut(
        type="n8n-nodes-base.httpRequest",
        display_name="HTTP Request",
        category="Tích hợp",
        type_version=4.2,
        parameters=[
            _param("url", "URL", "string", required=True),
            _param(
                "method",
                "Phương thức",
                "options",
                default="GET",
                options=["GET", "POST", "PUT", "DELETE", "PATCH"],
            ),
        ],
    ),
    "n8n-nodes-base.set": StudioNodeTypeOut(
        type="n8n-nodes-base.set",
        display_name="Set / Edit Fields",
        category="Dữ liệu",
        type_version=3.4,
        parameters=[
            _param("assignments", "Gán giá trị (JSON)", "json"),
        ],
    ),
    "n8n-nodes-base.if": StudioNodeTypeOut(
        type="n8n-nodes-base.if",
        display_name="IF / ELSE",
        category="Logic",
        type_version=2.2,
        parameters=[
            _param("conditions", "Điều kiện (JSON)", "json", required=True),
        ],
    ),
    "n8n-nodes-base.merge": StudioNodeTypeOut(
        type="n8n-nodes-base.merge",
        display_name="Merge",
        category="Logic",
        type_version=3,
        parameters=[],
    ),
    "n8n-nodes-base.code": StudioNodeTypeOut(
        type="n8n-nodes-base.code",
        display_name="Code (JavaScript)",
        category="Logic",
        type_version=2,
        parameters=[
            _param("jsCode", "Mã JavaScript", "string", required=True),
        ],
    ),
    "n8n-nodes-base.respondToWebhook": StudioNodeTypeOut(
        type="n8n-nodes-base.respondToWebhook",
        display_name="Respond to Webhook",
        category="Trigger",
        type_version=1.1,
        parameters=[
            _param(
                "respondWith",
                "Kiểu phản hồi",
                "options",
                default="json",
                options=["json", "text", "noData"],
            ),
        ],
    ),
    "n8n-nodes-base.telegram": StudioNodeTypeOut(
        type="n8n-nodes-base.telegram",
        display_name="Telegram",
        category="Thông báo",
        type_version=1.2,
        parameters=[
            _param("chatId", "Chat ID", "string", required=True),
            _param("text", "Nội dung tin nhắn", "string", required=True),
        ],
    ),
    "n8n-nodes-base.gmail": StudioNodeTypeOut(
        type="n8n-nodes-base.gmail",
        display_name="Gmail",
        category="Thông báo",
        type_version=2.1,
        parameters=[
            _param("subject", "Tiêu đề email", "string"),
            _param("emailType", "Loại nội dung", "options", default="text", options=["text", "html"]),
            _param("message", "Nội dung", "string"),
        ],
    ),
    "@n8n/n8n-nodes-langchain.agent": StudioNodeTypeOut(
        type="@n8n/n8n-nodes-langchain.agent",
        display_name="AI Agent",
        category="AI",
        type_version=2.2,
        parameters=[
            _param("promptType", "Kiểu prompt", "options", default="define", options=["define", "auto"]),
            _param("text", "Prompt", "string"),
        ],
    ),
}


def get_catalog() -> StudioCatalogOut:
    return StudioCatalogOut(node_types=sorted(CATALOG.values(), key=lambda n: (n.category, n.display_name)))


def convert_graph(graph: StudioGraphIn) -> StudioConvertOut:
    names = [node.name for node in graph.nodes]
    if len(set(names)) != len(names):
        raise ProviderError("studio_graph_invalid")
    known = set(names)
    warnings: list[str] = []
    n8n_nodes: list[dict] = []
    for node in graph.nodes:
        if node.raw is not None:
            raw = dict(node.raw)
            raw["name"] = node.name
            n8n_nodes.append(raw)
            warnings.append(
                f"Node '{node.name}' ({node.type}) chưa có adapter trong Studio — "
                "được giữ nguyên JSON gốc khi lưu."
            )
            continue
        spec = CATALOG.get(node.type)
        if spec is None:
            raise ProviderError("studio_graph_invalid")
        for param in spec.parameters:
            if param.required and node.parameters.get(param.name) in (None, ""):
                raise ProviderError("studio_graph_invalid")
        params = dict(node.parameters)
        for param in spec.parameters:
            if param.name not in params and param.default is not None:
                params[param.name] = param.default
        n8n_nodes.append(
            {
                "parameters": params,
                "id": uuid.uuid4().hex,
                "name": node.name,
                "type": node.type,
                "typeVersion": spec.type_version,
                "position": [float(node.position[0]) if node.position else 0, float(node.position[1]) if len(node.position) > 1 else 0],
            }
        )
    connections: dict[str, dict] = {}
    for edge in graph.edges:
        if edge.from_node not in known or edge.to_node not in known:
            raise ProviderError("studio_graph_invalid")
        entry = connections.setdefault(edge.from_node, {"main": []})
        outputs = entry["main"]
        while len(outputs) <= edge.output_index:
            outputs.append([])
        outputs[edge.output_index].append(
            {"node": edge.to_node, "type": "main", "index": 0}
        )
    workflow = {
        "name": graph.name,
        "nodes": n8n_nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }
    return StudioConvertOut(workflow_json=workflow, warnings=warnings)


def parse_workflow(workflow_json: dict) -> StudioGraphOut:
    nodes: list[StudioGraphNodeOut] = []
    unsupported: list[str] = []
    for index, node in enumerate(workflow_json.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type", ""))
        supported = node_type in CATALOG
        position = node.get("position") or [0, 0]
        nodes.append(
            StudioGraphNodeOut(
                id=str(node.get("id") or f"node-{index}"),
                name=str(node.get("name", f"Node {index + 1}")),
                type=node_type,
                position=[float(position[0]), float(position[1])] if len(position) >= 2 else [0, 0],
                parameters=node.get("parameters") or {},
                supported=supported,
                raw=None if supported else node,
            )
        )
        if not supported:
            unsupported.append(f"{node.get('name')} ({node_type})")
    edges: list[StudioEdgeIn] = []
    for from_name, by_type in (workflow_json.get("connections") or {}).items():
        if not isinstance(by_type, dict):
            continue
        for conn_type, outputs in by_type.items():
            if conn_type != "main" or not isinstance(outputs, list):
                continue
            for output_index, targets in enumerate(outputs):
                for target in targets or []:
                    if isinstance(target, dict) and target.get("node"):
                        edges.append(
                            StudioEdgeIn(
                                from_node=str(from_name),
                                to_node=str(target["node"]),
                                output_index=output_index,
                            )
                        )
    return StudioGraphOut(
        name=str(workflow_json.get("name", "")),
        nodes=nodes,
        edges=edges,
        unsupported=unsupported,
    )
