"""Architecture map tests (pure functions, no database).

The map mirrors a hand-written repository map: extension counts over
the whole archive inventory, technologies named only when a manifest
declares them, and a layered diagram grouped from the stored static
parse (paths, role tags, resolved import edges).
"""

import io
import zipfile

from app.services.architecture_map import build_architecture_map
from app.services.code_parser import (
    inventory_from_names,
    parse_codebase,
    zip_entry_names,
)


def _zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_inventory_counts_docs_and_config_but_not_junk():
    names = [
        "backend/app/main.py",
        "backend/app/api/chat.py",
        "frontend/app/page.jsx",
        "frontend/services/api.js",
        "README.md",
        "docker-compose.yml",
        "frontend/package.json",
        "node_modules/react/index.js",
        "frontend/node_modules/react/package.json",
        "package-lock.json",
        ".env",
        "dist/bundle.js",
        "src/util.min.js",
    ]
    inventory = inventory_from_names(names)
    by_key = {c["key"]: c["count"] for c in inventory["counts"]}
    assert by_key["python"] == 2
    assert by_key["javascript-jsx"] == 1
    assert by_key["javascript"] == 1
    assert by_key["markdown"] == 1
    assert by_key["json"] == 1
    # node_modules, dist, lockfiles, dotfiles and minified files are out.
    assert inventory["total_counted"] == 7
    assert inventory["flags"]["docker_compose"] is True
    assert inventory["flags"]["package_json"] is True
    assert inventory["flags"]["readme"] is True


def test_parse_codebase_detects_tech_from_manifests():
    data = _zip(
        {
            "repo/frontend/package.json": (
                '{"dependencies": {"next": "16", "react": "19"}}'
            ),
            "repo/frontend/app/page.jsx": "export default function Page() {}",
            "repo/backend/requirements.txt": "fastapi\nmotor\n",
            "repo/backend/app/main.py": "from app.api import chat\n",
            "repo/backend/app/api/chat.py": "x = 1\n",
            "repo/README.md": "# Demo\n",
        }
    )
    parsed = parse_codebase(data)
    inventory = parsed["inventory"]
    assert "Next.js" in inventory["tech"]
    assert "React" in inventory["tech"]
    assert "FastAPI" in inventory["tech"]
    assert "MongoDB" in inventory["tech"]
    assert inventory["total_counted"] == 6
    assert zip_entry_names(data)[0].startswith("frontend/")


def _fixture_files():
    def f(path, language, role, targets=(), imported_by=()):
        return {
            "file_path": path,
            "language": language,
            "role_tag": role,
            "imports": [{"target_file": t} for t in targets],
            "imported_by": list(imported_by),
        }

    return [
        f("frontend/app/layout.js", "javascript", "Entry Point",
          ["frontend/services/api.js"], ["frontend/app/page.jsx"]),
        f("frontend/app/page.jsx", "javascript", "Component",
          ["frontend/services/api.js"], []),
        f("frontend/services/api.js", "javascript", "API Client",
          [], ["frontend/app/layout.js", "frontend/app/page.jsx"]),
        f("backend/app/main.py", "python", "Entry Point",
          ["backend/app/api/chat.py"], []),
        f("backend/app/api/chat.py", "python", "Router",
          ["backend/app/services/chat.py"], ["backend/app/main.py"]),
        f("backend/app/services/chat.py", "python", "Service",
          ["backend/app/repositories/chat.py", "backend/app/services/ai/ai_factory.py"],
          ["backend/app/api/chat.py"]),
        f("backend/app/repositories/chat.py", "python", "Repository",
          ["backend/app/core/database.py"], ["backend/app/services/chat.py"]),
        f("backend/app/core/database.py", "python", "Config",
          [], ["backend/app/repositories/chat.py"]),
        f("backend/app/services/ai/ai_factory.py", "python", "Service",
          [], ["backend/app/services/chat.py"]),
    ]


def _fixture_inventory():
    return {
        "counts": [
            {"key": "python", "label": "Python files", "short": "Python", "count": 6},
            {"key": "javascript", "label": "JavaScript", "short": "JavaScript", "count": 3},
            {"key": "markdown", "label": "Markdown", "short": "Markdown", "count": 1},
        ],
        "total_counted": 10,
        "flags": {"docker_compose": True, "dockerfile": False, "readme": True,
                  "package_json": True, "python_manifest": True},
        "tech": ["Next.js", "React", "FastAPI", "MongoDB"],
    }


def test_map_groups_layers_nodes_and_wires():
    payload = build_architecture_map(
        project_name="Demo Hub",
        files=_fixture_files(),
        inventory=_fixture_inventory(),
        has_report=True,
    )
    assert payload["title"] == "Demo Hub"
    lane_ids = [lane["id"] for lane in payload["lanes"]]
    assert lane_ids == ["client", "server", "data", "runtime"]
    assert payload["lanes"][0]["label"] == "CLIENT · NEXT.JS APP ROUTER"
    assert payload["lanes"][1]["label"] == "SERVER · FASTAPI"
    keys = {node["key"] for node in payload["nodes"]}
    assert {"user", "ui-entry", "transport", "app-entry", "routes",
            "services", "repos", "db-core", "providers",
            "compose", "database", "external-apis"} <= keys
    by_key = {node["key"]: node for node in payload["nodes"]}
    assert by_key["app-entry"]["title"] == "FastAPI application"
    assert by_key["database"]["title"] == "MongoDB"
    assert "backend/app/services/api.js" not in str(by_key["transport"]["subs"])
    assert "frontend/services/api.js" in by_key["transport"]["subs"]
    # Every node is placed inside the canvas.
    for node in payload["nodes"]:
        assert 0 <= node["x"] and node["x"] + node["w"] <= payload["view_box"]["w"]
        assert node["y"] + node["h"] <= payload["view_box"]["h"]
    hot = [w for w in payload["wires"] if w["cls"] == "hot"]
    alt = [w for w in payload["wires"] if w["cls"] == "alt"]
    assert hot, "the main request chain must be highlighted"
    assert alt, "the provider edge must use the AI call style"
    # Chips: top counts first, total chip last without a value.
    assert payload["chips"][0] == {"value": 6, "label": "Python files"}
    assert payload["chips"][-1]["value"] is None
    assert "10 source/config/doc paths counted" in payload["chips"][-1]["label"]
    assert "Next.js" in payload["intro"]
    reading = payload["cards"]["reading"]
    assert reading and "frontend/app/layout.js" in reading[0]["path"]
    assert "Python 6" in payload["cards"]["languages"]["text"]


def test_map_falls_back_to_file_counts_without_inventory():
    payload = build_architecture_map(
        project_name="Old Project",
        files=_fixture_files(),
        inventory=None,
        has_report=False,
    )
    assert payload["chips"][-1]["value"] is None
    assert "analyzed code files counted" in payload["chips"][-1]["label"]
    assert "before inventory tracking" in payload["cards"]["languages"]["note"]
    assert "No AI report" in payload["scope_note"]
    # No manifest was seen, so no stack may be named in the intro.
    assert "Next.js" not in payload["intro"]
    assert "FastAPI" not in payload["intro"]
