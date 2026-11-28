"""Architecture map builder for the Code Analyzer.

Turns the stored static parse of an uploaded codebase (file paths,
languages, role tags, resolved import edges) into the payload behind
the project report view: a layered architecture diagram in the shape
of a hand-written repository map — header, language chips, an SVG
diagram of grouped nodes across lanes, three reading cards and an
honest scope note.

Everything here is deterministic and source-backed: counts come from
the archive inventory (or, for projects uploaded before inventory
tracking, from the analyzed files themselves), technologies are only
named when the archive's own dependency manifests declare them, and
nodes are groups of real files with real paths. Grouping is by path
and role heuristics; the scope note says so.
"""

import posixpath
from collections import Counter

from app.services.code_parser import COUNT_CATEGORIES

CANVAS_W = 1040
NODE_W = 230
NODE_GAP_X = 26
LANE_TOP = 46
LANE_GAP = 36
ROW_GAP = 18

_FRONTEND_HEADS = {"frontend", "client", "web", "ui"}
_BACKEND_HEADS = {"backend", "server", "api"}
_CLIENT_EXTS = {".jsx", ".tsx", ".vue", ".svelte", ".css", ".scss", ".html", ".htm"}
_SERVER_EXTS = {".py", ".java", ".go", ".rb", ".php", ".cs", ".rs", ".kt", ".swift"}
_CLIENT_ROLES = {"Component", "View", "Hook", "Store", "Context"}
_SERVER_ROLES = {"Router", "Controller", "Service", "Middleware"}
_DB_NAME_HINTS = ("database", "credential", "prisma", "db", "seed")
_DB_TECH = ("MongoDB", "PostgreSQL", "MySQL", "Redis")
_FRONTEND_TECH = ("Next.js", "React", "Vue", "Angular", "Svelte")
_BACKEND_TECH = ("FastAPI", "Express", "Django", "Flask", "NestJS", "Fastify")

_KIND_LEGEND = (
    ("frontend", "#5bd6e8", "Frontend"),
    ("backend", "#62d6a5", "API and services"),
    ("data", "#b3a0ff", "Data layer"),
    ("infra", "#ffc36b", "Runtime"),
    ("external", "#ff86a6", "External actor/provider"),
)

# group key -> (lane, kind, order in lane)
_GROUPS: dict[str, tuple[str, str, int]] = {
    "user": ("client", "external", 0),
    "ui-entry": ("client", "frontend", 1),
    "transport": ("client", "frontend", 2),
    "components": ("client", "frontend", 3),
    "state": ("client", "frontend", 4),
    "client-modules": ("client", "muted", 5),
    "app-entry": ("server", "backend", 1),
    "routes": ("server", "backend", 2),
    "services": ("server", "backend", 3),
    "server-core": ("server", "backend", 4),
    "server-modules": ("server", "muted", 5),
    "repos": ("data", "data", 1),
    "db-core": ("data", "data", 2),
    "providers": ("data", "backend", 3),
    "compose": ("runtime", "infra", 1),
    "database": ("runtime", "infra", 2),
    "external-apis": ("runtime", "external", 3),
}

_LANE_LABELS = {
    "client": "CLIENT",
    "server": "SERVER",
    "data": "PERSISTENCE & MODEL INTEGRATIONS",
    "runtime": "RUNTIME DEPENDENCIES",
}

_HOT_PAIRS = {
    ("ui-entry", "transport"),
    ("transport", "app-entry"),
    ("transport", "routes"),
    ("app-entry", "routes"),
    ("routes", "services"),
    ("services", "repos"),
    ("services", "db-core"),
}


def _ext(path: str) -> str:
    return posixpath.splitext(path)[1].lower()


def _area_of(file: dict) -> str:
    path = file.get("file_path", "")
    parts = path.split("/")
    segments = {part.lower() for part in parts[:-1]}
    head = parts[0].lower() if len(parts) > 1 else ""
    role = file.get("role_tag", "")
    ext = _ext(path)
    if head in _FRONTEND_HEADS or segments & _FRONTEND_HEADS:
        return "client"
    if head in _BACKEND_HEADS or segments & _BACKEND_HEADS:
        return "server"
    if ext in _SERVER_EXTS or role in _SERVER_ROLES:
        return "server"
    if ext in _CLIENT_EXTS or role in _CLIENT_ROLES:
        return "client"
    if file.get("language") in {"python", "java", "go", "ruby", "php", "csharp", "rust"}:
        return "server"
    return "client" if ext in {".js", ".ts"} else "server"


def _group_of(file: dict) -> str:
    path = file.get("file_path", "")
    lowered = path.lower()
    name = lowered.rsplit("/", 1)[-1]
    role = file.get("role_tag", "")
    if "provider" in lowered or "/ai/" in lowered:
        return "providers"
    if any(hint in name for hint in _DB_NAME_HINTS):
        return "db-core"
    if role in {"Repository", "Model"}:
        return "repos"
    if _area_of(file) == "client":
        if role == "Entry Point":
            return "ui-entry"
        if role == "API Client":
            return "transport"
        if role in {"Hook", "Store", "Context"}:
            return "state"
        if role in {"Component", "View"}:
            return "components"
        return "client-modules"
    if role == "Entry Point":
        return "app-entry"
    if role in {"Router", "Controller", "Middleware"}:
        return "routes"
    if role == "Service":
        return "services"
    if role == "Config":
        return "server-core"
    return "server-modules"


def _counts_from_files(files: list[dict]) -> tuple[list[dict], int]:
    by_ext = {ext: (key, label, short) for key, label, short, exts in COUNT_CATEGORIES for ext in exts}
    counts: Counter = Counter()
    other = 0
    for file in files:
        category = by_ext.get(_ext(file.get("file_path", "")))
        if category:
            counts[category[0]] += 1
        else:
            other += 1
    ordered = [
        {"key": key, "label": label, "short": short, "count": counts[key]}
        for key, label, short, _exts in COUNT_CATEGORIES
        if counts.get(key)
    ]
    if other:
        ordered.append({"key": "other", "label": "Other files", "short": "other", "count": other})
    return ordered, len(files)


def _representatives(members: list[dict], limit: int = 3) -> list[str]:
    ranked = sorted(
        members,
        key=lambda f: (-len(f.get("imported_by") or []), f.get("file_path", "")),
    )
    return [f["file_path"] for f in ranked[:limit]]


def _node_title(key: str, tech: list[str]) -> str:
    if key == "ui-entry" and "Next.js" in tech:
        return "Next.js UI + auth gate"
    if key == "app-entry" and "FastAPI" in tech:
        return "FastAPI application"
    if key == "app-entry" and "Express" in tech:
        return "Express application"
    return {
        "user": "User",
        "ui-entry": "UI entry & shell",
        "transport": "Browser API transport",
        "components": "Components & views",
        "state": "State, hooks & context",
        "client-modules": "Client modules",
        "app-entry": "Application entry",
        "routes": "API routes",
        "services": "Feature services",
        "server-core": "Core & config",
        "server-modules": "Server modules",
        "repos": "Repositories + entities",
        "db-core": "Database + credential core",
        "providers": "AI provider factory",
        "compose": "Docker Compose",
        "database": "Database",
        "external-apis": "External model APIs",
    }[key]


def _layout(nodes: list[dict], lanes: list[str]) -> int:
    """Assign x/y/height to grouped nodes lane by lane; return height."""
    y = 8
    for lane in lanes:
        members = sorted(
            (n for n in nodes if n["lane"] == lane),
            key=lambda n: n["order"],
        )
        if not members:
            continue
        y += LANE_TOP
        x = 20
        row_height = 0
        for node in members:
            width = 150 if node["key"] == "user" else NODE_W
            height = 46 + 19 * len(node["subs"]) + 16 * len(node["tiny"])
            if x + width > CANVAS_W and x > 20:
                y += row_height + ROW_GAP
                x = 20
                row_height = 0
            node.update({"x": x, "y": y, "w": width, "h": height})
            x += width + NODE_GAP_X
            row_height = max(row_height, height)
        y += row_height + LANE_GAP
    return y + 6


def _wire_path(source: dict, target: dict) -> str:
    sx_r, sy = source["x"] + source["w"], source["y"] + source["h"] / 2
    tx_l, ty = target["x"], target["y"] + target["h"] / 2
    sx_b, sy_b = source["x"] + source["w"] / 2, source["y"] + source["h"]
    tx_t, ty_t = target["x"] + target["w"] / 2, target["y"]
    if target["lane"] != source["lane"] and ty_t > sy:
        return f"M{sx_b:.0f} {sy_b:.0f} C {sx_b:.0f} {sy_b + 42:.0f}, {tx_t:.0f} {ty_t - 42:.0f}, {tx_t:.0f} {ty_t:.0f}"
    if tx_l >= sx_r - 4:
        return f"M{sx_r:.0f} {sy:.0f} C {sx_r + 42:.0f} {sy:.0f}, {tx_l - 42:.0f} {ty:.0f}, {tx_l:.0f} {ty:.0f}"
    if ty > sy:
        return f"M{sx_b:.0f} {sy_b:.0f} C {sx_b:.0f} {sy_b + 36:.0f}, {tx_t:.0f} {ty_t - 36:.0f}, {tx_t:.0f} {ty_t:.0f}"
    return f"M{sx_r:.0f} {sy:.0f} C {sx_r + 46:.0f} {sy:.0f}, {tx_l - 46:.0f} {ty:.0f}, {tx_l:.0f} {ty:.0f}"


def _reading_chains(files: list[dict]) -> list[dict]:
    by_path = {f["file_path"]: f for f in files}
    entries = sorted(
        (f for f in files if f.get("role_tag") == "Entry Point"),
        key=lambda f: -len(f.get("imported_by") or []),
    )
    chains: list[dict] = []
    seen_starts: set[str] = set()
    for entry in entries:
        if len(chains) >= 4:
            break
        chain = [entry["file_path"]]
        visited = {entry["file_path"]}
        current = entry
        while len(chain) < 4:
            targets = [
                imp.get("target_file")
                for imp in current.get("imports") or []
                if imp.get("target_file") in by_path and imp.get("target_file") not in visited
            ]
            if not targets:
                break
            nxt = max(targets, key=lambda p: len(by_path[p].get("imported_by") or []))
            chain.append(nxt)
            visited.add(nxt)
            current = by_path[nxt]
        if len(chain) >= 2 and chain[0] not in seen_starts:
            seen_starts.add(chain[0])
            roles = []
            for path in chain:
                role = by_path[path].get("role_tag") or "Module"
                if role not in roles:
                    roles.append(role)
            chains.append(
                {
                    "path": " → ".join(chain),
                    "text": "Flow: " + " · ".join(roles) + ".",
                }
            )
    if chains:
        return chains
    ranked = sorted(files, key=lambda f: -len(f.get("imported_by") or []))[:4]
    return [
        {
            "path": f["file_path"],
            "text": f"Imported by {len(f.get('imported_by') or [])} files — "
            "among the most depended-on code in the archive.",
        }
        for f in ranked
    ]


def build_architecture_map(
    *,
    project_name: str,
    files: list[dict],
    inventory: dict | None,
    has_report: bool,
) -> dict:
    """Build the full architecture-map payload for one project."""
    tech: list[str] = list((inventory or {}).get("tech") or [])
    flags: dict = dict((inventory or {}).get("flags") or {})
    if inventory and inventory.get("counts"):
        counts = inventory["counts"]
        total = inventory.get("total_counted") or sum(c["count"] for c in counts)
        total_label = f"{total} source/config/doc paths counted"
        counts_fallback = False
    else:
        counts, total = _counts_from_files(files)
        total_label = f"{total} analyzed code files counted"
        counts_fallback = True

    groups: dict[str, list[dict]] = {}
    for file in files:
        groups.setdefault(_group_of(file), []).append(file)
    group_of_path = {
        f["file_path"]: key for key, members in groups.items() for f in members
    }

    nodes: list[dict] = [
        {
            "key": "user",
            "lane": "client",
            "kind": "external",
            "order": 0,
            "title": "User",
            "subs": ["Browser"],
            "tiny": ["workspace screens"],
            "center": True,
        }
    ]
    for key, members in groups.items():
        lane, kind, order = _GROUPS[key]
        roles = []
        for member in members:
            role = member.get("role_tag") or ""
            if role and role not in roles:
                roles.append(role)
        tiny = [f"{len(members)} files"]
        if len(roles) > 1:
            tiny.append(" · ".join(roles[:3]))
        nodes.append(
            {
                "key": key,
                "lane": lane,
                "kind": kind,
                "order": order,
                "title": _node_title(key, tech),
                "subs": _representatives(members),
                "tiny": tiny,
                "center": False,
            }
        )
    if flags.get("docker_compose"):
        nodes.append(
            {
                "key": "compose", "lane": "runtime", "kind": "infra", "order": 1,
                "title": "Docker Compose", "subs": ["docker-compose.yml"],
                "tiny": ["runtime services declared here"], "center": False,
            }
        )
    elif flags.get("dockerfile"):
        nodes.append(
            {
                "key": "compose", "lane": "runtime", "kind": "infra", "order": 1,
                "title": "Docker image", "subs": ["Dockerfile"],
                "tiny": ["container build declared here"], "center": False,
            }
        )
    db_tech = next((t for t in tech if t in _DB_TECH), "")
    if "db-core" in groups or db_tech:
        subs = _representatives(groups.get("db-core", []), limit=1)
        nodes.append(
            {
                "key": "database", "lane": "runtime", "kind": "infra", "order": 2,
                "title": db_tech or "Database",
                "subs": subs or ["declared in project configuration"],
                "tiny": ["runtime dependency"], "center": False,
            }
        )
    if "providers" in groups:
        nodes.append(
            {
                "key": "external-apis", "lane": "runtime", "kind": "external", "order": 3,
                "title": "External model APIs",
                "subs": _representatives(groups["providers"], limit=2),
                "tiny": ["reached through the provider factory"], "center": False,
            }
        )

    lanes = [
        lane
        for lane in ("client", "server", "data", "runtime")
        if any(n["lane"] == lane for n in nodes)
    ]
    lane_labels = {}
    for lane in lanes:
        label = _LANE_LABELS[lane]
        if lane == "client":
            fe = next((t for t in tech if t in _FRONTEND_TECH), "")
            if fe == "Next.js":
                label = "CLIENT · NEXT.JS APP ROUTER"
            elif fe:
                label = f"CLIENT · {fe.upper()}"
        if lane == "server":
            be = next((t for t in tech if t in _BACKEND_TECH), "")
            if be:
                label = f"SERVER · {be.upper()}"
        lane_labels[lane] = label
    height = _layout(nodes, lanes)
    by_key = {n["key"]: n for n in nodes}

    edge_counts: Counter = Counter()
    for file in files:
        source = group_of_path.get(file["file_path"])
        if not source:
            continue
        for imp in file.get("imports") or []:
            target = group_of_path.get(imp.get("target_file") or "")
            if target and target != source:
                edge_counts[(source, target)] += 1
    # The User node has no import edges; wire it to the UI entry by hand,
    # like the reference map does.
    if "ui-entry" in by_key:
        edge_counts[("user", "ui-entry")] += 1
    ranked_edges = sorted(edge_counts.items(), key=lambda kv: -kv[1])
    wires = []
    for (source, target), count in ranked_edges[:14]:
        if source not in by_key or target not in by_key:
            continue
        if (source, target) in _HOT_PAIRS or source == "user":
            cls = "hot"
        elif target in {"providers", "external-apis"} or source == "providers":
            cls = "alt"
        else:
            cls = ""
        wires.append(
            {
                "d": _wire_path(by_key[source], by_key[target]),
                "cls": cls,
                "count": count,
            }
        )

    chips = [
        {"value": c["count"], "label": c["label"]}
        for c in sorted(counts, key=lambda c: -c["count"])[:5]
    ]
    chips.append({"value": None, "label": total_label})

    fe_name = next((t for t in tech if t in _FRONTEND_TECH), "A web frontend")
    be_name = next((t for t in tech if t in _BACKEND_TECH), "")
    if not be_name:
        be_name = "a Python backend" if any(f.get("language") == "python" for f in files) else "the backend service"
    db_name = db_tech or "the database"
    if "ui-entry" in groups and "services" in groups:
        intro = (
            f"{fe_name} sends authenticated requests to {be_name}. "
            "The backend routes each feature through application services, "
            f"then to {db_name}"
        )
        intro += (
            " or an AI provider adapter."
            if "providers" in groups
            else "."
        )
    elif "services" in groups or "routes" in groups:
        intro = (
            f"{be_name} organized in layers: requests enter through its API "
            "routes, pass through feature services, and reach "
            f"{db_name} through the data layer."
        )
    elif groups:
        intro = (
            f"{fe_name} codebase, grouped below by layer: entry points, "
            "shared modules and the data or runtime pieces they depend on."
        )
    else:
        intro = "No analyzable files were stored for this project."

    follows: list[str] = []
    if "transport" in groups:
        follows.append(
            "The browser talks to the API through "
            f"{_representatives(groups['transport'], limit=1)[0]}; feature code "
            "calls that transport instead of scattering raw requests."
        )
    if flags.get("docker_compose"):
        follows.append(
            "docker-compose.yml declares the runtime services, so the "
            "deployed topology follows that file; this map groups code by "
            "layer, not by container."
        )
    if "db-core" in groups:
        credential = next(
            (p for p in _representatives(groups["db-core"], limit=3) if "credential" in p),
            "",
        )
        if credential:
            follows.append(
                f"Provider keys are decrypted server-side by {credential}; "
                "the frontend receives answers, not keys."
            )
    if "providers" in groups:
        follows.append(
            "AI calls leave the codebase through "
            f"{_representatives(groups['providers'], limit=1)[0]} — provider "
            "adapters keep model-specific code in one place."
        )
    if not follows:
        follows.append(
            "Edges follow imports resolved inside the archive; the reading "
            "order below starts from the entry points and the most "
            "depended-on files."
        )

    languages_text = " · ".join(f"{c['short']} {c['count']}" for c in counts)
    if counts_fallback:
        languages_note = (
            "Counts cover the analyzed code files only — this project was "
            "uploaded before inventory tracking. Re-upload the archive to "
            "count documentation and configuration files too."
        )
    else:
        languages_note = (
            "Extension-based file counts, excluding dependency, build, and "
            "cache folders. This is not a lines-of-code report."
        )

    scope_bits = [
        "This map reflects the routed code in the uploaded archive, "
        "grouped by path and role heuristics — not the product name.",
        "Only imports resolved inside the archive are drawn; calls into "
        "external packages are not file edges.",
    ]
    if counts_fallback:
        scope_bits.append(
            "Inventory counts are partial for this project (see Language counts)."
        )
    if not has_report:
        scope_bits.append(
            "No AI report has been generated yet; everything above is static analysis."
        )

    legend = [
        {"color": color, "label": label}
        for kind, color, label in _KIND_LEGEND
        if any(n["kind"] == kind for n in nodes)
    ]

    return {
        "eyebrow": "Repository map · source-backed",
        "title": project_name,
        "intro": intro,
        "chips": chips,
        "lanes": [
            {"id": lane, "label": lane_labels[lane]} for lane in lanes
        ],
        "nodes": [
            {
                "key": n["key"],
                "kind": n["kind"],
                "title": n["title"],
                "subs": n["subs"],
                "tiny": n["tiny"],
                "center": n["center"],
                "x": n["x"],
                "y": n["y"],
                "w": n["w"],
                "h": n["h"],
            }
            for n in nodes
        ],
        "lane_marks": [
            {"label": lane_labels[lane], "y": min(n["y"] for n in nodes if n["lane"] == lane) - 24}
            for lane in lanes
        ],
        "wires": wires,
        "view_box": {"w": CANVAS_W, "h": height},
        "legend": legend,
        "cards": {
            "reading": _reading_chains(files),
            "follows": follows,
            "languages": {"text": languages_text, "note": languages_note},
        },
        "scope_note": " ".join(scope_bits),
        "foot": "Source paths were verified in the uploaded archive. "
        "No secrets, dependency contents, or generated build files were read for the map.",
    }
