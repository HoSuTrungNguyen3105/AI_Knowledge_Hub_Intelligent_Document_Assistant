"""Offline contracts for the Workflow Studio conversion layer (phase 4).

Pure conversion tests: no n8n, no network. They verify the validator,
the graph -> n8n JSON conversion and the parse round-trip, including
the rule that unsupported nodes are preserved verbatim, never dropped.
"""

BASE = "/api/v1/ai/workflow-studio"

GRAPH = {
    "name": "Studio Flow",
    "nodes": [
        {
            "id": "a",
            "name": "Start",
            "type": "n8n-nodes-base.manualTrigger",
            "position": [100, 100],
            "parameters": {},
        },
        {
            "id": "b",
            "name": "Call API",
            "type": "n8n-nodes-base.httpRequest",
            "position": [340, 100],
            "parameters": {"url": "https://example.com/hook"},
        },
    ],
    "edges": [{"from_node": "Start", "to_node": "Call API", "output_index": 0}],
}


def test_catalog_lists_supported_types(owner):
    resp = owner.get(f"{BASE}/catalog")
    assert resp.status_code == 200, resp.text
    types = {item["type"] for item in resp.json()["node_types"]}
    assert "n8n-nodes-base.httpRequest" in types
    assert "n8n-nodes-base.if" in types
    assert "@n8n/n8n-nodes-langchain.agent" in types


def test_convert_builds_n8n_json(owner):
    resp = owner.post(f"{BASE}/convert", json=GRAPH)
    assert resp.status_code == 200, resp.text
    workflow = resp.json()["workflow_json"]
    assert workflow["name"] == "Studio Flow"
    assert len(workflow["nodes"]) == 2
    http_node = next(n for n in workflow["nodes"] if n["name"] == "Call API")
    assert http_node["typeVersion"] == 4.2
    assert http_node["parameters"]["method"] == "GET"  # default applied
    targets = workflow["connections"]["Start"]["main"][0]
    assert targets == [{"node": "Call API", "type": "main", "index": 0}]


def test_convert_rejects_unknown_type_and_missing_required(owner):
    unknown = {
        "name": "X",
        "nodes": [
            {
                "id": "a",
                "name": "Mystery",
                "type": "n8n-nodes-pdfmint.pdfMint",
                "position": [0, 0],
                "parameters": {},
            }
        ],
        "edges": [],
    }
    resp = owner.post(f"{BASE}/convert", json=unknown)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "studio_graph_invalid"

    missing = {
        "name": "X",
        "nodes": [
            {
                "id": "a",
                "name": "Call",
                "type": "n8n-nodes-base.httpRequest",
                "position": [0, 0],
                "parameters": {},
            }
        ],
        "edges": [],
    }
    resp2 = owner.post(f"{BASE}/convert", json=missing)
    assert resp2.status_code == 422


def test_parse_preserves_unsupported_nodes(owner):
    workflow = {
        "name": "Imported",
        "nodes": [
            {
                "id": "1",
                "name": "Start",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [100, 100],
                "parameters": {},
            },
            {
                "id": "2",
                "name": "PDF",
                "type": "n8n-nodes-pdfmint.pdfMint",
                "typeVersion": 1,
                "position": [340, 100],
                "parameters": {"operation": "create"},
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "PDF", "type": "main", "index": 0}]]}
        },
    }
    resp = owner.post(f"{BASE}/parse", json={"workflow_json": workflow})
    assert resp.status_code == 200, resp.text
    graph = resp.json()
    assert len(graph["unsupported"]) == 1
    pdf = next(n for n in graph["nodes"] if n["name"] == "PDF")
    assert pdf["supported"] is False
    assert pdf["raw"]["parameters"] == {"operation": "create"}
    assert graph["edges"] == [
        {"from_node": "Start", "to_node": "PDF", "output_index": 0}
    ]

    # Round-trip: converting the parsed graph keeps the raw node verbatim.
    back = owner.post(
        f"{BASE}/convert",
        json={"name": graph["name"], "nodes": graph["nodes"], "edges": graph["edges"]},
    )
    assert back.status_code == 200, back.text
    names = {n["name"] for n in back.json()["workflow_json"]["nodes"]}
    assert names == {"Start", "PDF"}
    assert len(back.json()["warnings"]) == 1


def test_studio_requires_auth(client):
    assert client.get(f"{BASE}/catalog").status_code == 401
