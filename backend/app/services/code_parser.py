"""Static codebase parsing for the Code Analyzer (PROJECT_SPEC.md).

Pure functions over an in-memory ZIP: junk filtering, language
detection, and regex-based import extraction for JavaScript/TypeScript
and Python. No token cost and no filesystem writes, so repositories
with 1000+ files stay cheap to ingest; the AI pass (summaries, roles,
relation labels) happens later on n8n from these results.
"""

import ast
import io
import posixpath
import re
import zipfile
from collections import Counter

MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_FILES = 2000
MAX_FILE_BYTES = 512 * 1024

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", "venv", ".venv",
    "__pycache__", "vendor", "target", ".idea", ".vscode", "coverage",
    ".turbo", "out",
}
SKIP_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "cargo.lock", "composer.lock", "gemfile.lock",
}
SOURCE_ROOT_NAMES = {
    "src", "app", "apps", "backend", "frontend", "lib", "libs", "pkg", "cmd",
    "internal", "api", "server", "client", "packages", "modules", "tests", "test",
}
LANGUAGES = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".py": "python", ".java": "java", ".go": "go", ".rb": "ruby",
    ".php": "php", ".cs": "csharp", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".rs": "rust", ".kt": "kotlin",
    ".swift": "swift", ".vue": "vue", ".svelte": "svelte",
    ".html": "html", ".css": "css", ".scss": "css", ".sql": "sql",
    ".sh": "shell",
}

_JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[^'"]*?\s+from\s+)?|export\s+[^'"]*?\s+from\s+"""
    r"""|require\s*\()\s*['"]([^'"]+)['"]"""
)

_ROLE_HINTS = (
    ("controller", "Controller"),
    ("service", "Service"),
    ("model", "Model"),
    ("schema", "Model"),
    ("route", "Router"),
    ("router", "Router"),
    ("middleware", "Middleware"),
    ("repository", "Repository"),
    ("repo", "Repository"),
    ("component", "Component"),
    ("hook", "Hook"),
    ("util", "Util"),
    ("helper", "Util"),
    ("config", "Config"),
    ("client", "API Client"),
    ("api", "API Client"),
    ("store", "Store"),
    ("context", "Context"),
)


def _is_test_file(name: str) -> bool:
    return (
        ".test." in name
        or ".spec." in name
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("_test.go")
    )


def _kept(path: str) -> bool:
    parts = path.split("/")
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return False
    name = parts[-1]
    if name in SKIP_NAMES or name.startswith("."):
        return False
    if _is_test_file(name) or name.endswith((".min.js", ".min.css", ".snap")):
        return False
    return posixpath.splitext(name)[1].lower() in LANGUAGES


def _strip_common_root(paths: list[str]) -> list[str]:
    """GitHub ZIPs wrap everything in one top folder; drop that prefix."""
    if not paths or any("/" not in p for p in paths):
        return paths
    roots = {p.split("/", 1)[0] for p in paths}
    if len(roots) == 1:
        root = roots.pop()
        # Preserve conventional source/package directories. A ZIP containing
        # only ``src/...`` is often a hand-made project archive, not a GitHub
        # export wrapper; removing it would corrupt reported file paths.
        if root.casefold() in SOURCE_ROOT_NAMES:
            return paths
        return [p[len(root) + 1:] for p in paths]
    return paths


def extract_files(data: bytes) -> tuple[int, list[dict]]:
    """Return (raw entry count, kept files with decoded content)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return 0, []
    entries = [i for i in archive.infolist() if not i.is_dir()]
    names = _strip_common_root([i.filename.replace("\\", "/") for i in entries])
    kept: list[dict] = []
    for info, path in zip(entries, names, strict=True):
        if not _kept(path) or info.file_size > MAX_FILE_BYTES:
            continue
        try:
            content = archive.read(info).decode("utf-8", errors="replace")
        except (RuntimeError, KeyError):
            continue
        kept.append({"path": path, "content": content})
        if len(kept) >= MAX_FILES:
            break
    return len(entries), kept


def _resolve_js(spec: str, from_path: str, known: set[str]) -> str | None:
    if not spec.startswith("."):
        return None  # bare specifier: external package, not a graph edge
    base = posixpath.normpath(posixpath.join(posixpath.dirname(from_path), spec))
    candidates = [base]
    for ext in (".js", ".jsx", ".ts", ".tsx"):
        candidates.append(base + ext)
    for ext in (".js", ".ts"):
        candidates.append(f"{base}/index{ext}")
    for candidate in candidates:
        if candidate in known:
            return candidate
    return None


def _resolve_py(module: str, from_path: str, known: set[str]) -> str | None:
    base = module.replace(".", "/")
    for candidate in (f"{base}.py", f"{base}/__init__.py"):
        if candidate in known:
            return candidate
    return None


def _resolve_py_relative(spec: str, from_path: str, known: set[str]) -> str | None:
    level = len(spec) - len(spec.lstrip("."))
    rest = spec[level:]
    package = posixpath.dirname(from_path)
    for _ in range(level - 1):
        package = posixpath.dirname(package)
    module = f"{package}/{rest.replace('.', '/')}" if rest else package
    module = module.strip("/")
    for candidate in (f"{module}.py", f"{module}/__init__.py"):
        if candidate in known:
            return candidate
    return None


def _resolve_py_from(
    module: str | None, level: int, imported_names: list[str], from_path: str, known: set[str]
) -> list[str]:
    """Resolve the package module and imported submodules from ``from ... import``.

    Python permits namespace packages without ``__init__.py`` and the common
    ``from package import submodule`` form. Resolve both the imported module
    and any imported names that are actual files in the archive.
    """
    if level:
        base = posixpath.dirname(from_path)
        for _ in range(level - 1):
            base = posixpath.dirname(base)
        if module:
            base = posixpath.join(base, module.replace(".", "/"))
    else:
        if not module:
            return []
        base = module.replace(".", "/")
    base = base.strip("/")

    found: list[str] = []
    module_file = next(
        (candidate for candidate in (f"{base}.py", f"{base}/__init__.py") if candidate in known),
        None,
    )
    if module_file:
        found.append(module_file)
    package_base = posixpath.splitext(module_file)[0] if module_file else base
    for name in imported_names:
        if name == "*":
            continue
        child = posixpath.join(package_base, name.replace(".", "/"))
        for candidate in (f"{child}.py", f"{child}/__init__.py"):
            if candidate in known and candidate not in found:
                found.append(candidate)
                break
    return found


def extract_imports(path: str, content: str, known: set[str]) -> list[str]:
    """Resolved in-repo import targets of one file, order-stable, deduped."""
    language = LANGUAGES.get(posixpath.splitext(path)[1].lower(), "")
    targets: list[str] = []

    def add(target: str | None) -> None:
        if target and target != path and target not in targets:
            targets.append(target)

    if language in {"javascript", "typescript", "vue", "svelte"}:
        for spec in _JS_IMPORT.findall(content):
            add(_resolve_js(spec, path, known))
    elif language == "python":
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError, RecursionError):
            return targets
        imports = sorted(
            (node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))),
            key=lambda node: node.lineno,
        )
        for node in imports:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    add(_resolve_py(alias.name, path, known))
            else:
                names = [alias.name for alias in node.names]
                for target in _resolve_py_from(node.module, node.level, names, path, known):
                    add(target)
    return targets


def role_tag_for(path: str) -> str:
    name = posixpath.basename(path).lower()
    stem = posixpath.splitext(name)[0]
    lowered = path.lower()
    if stem in {"main", "index", "app", "server", "__main__"}:
        return "Entry Point"
    for hint, tag in _ROLE_HINTS:
        if hint in stem or f"/{hint}" in lowered:
            return tag
    if posixpath.splitext(name)[1] in {".html", ".css", ".scss"}:
        return "View"
    return "Module"


def parse_codebase(data: bytes) -> dict:
    """Full static pass: filter, parse imports, compute reverse edges."""
    raw_count, kept = extract_files(data)
    known = {f["path"] for f in kept}
    files: list[dict] = []
    for f in kept:
        language = LANGUAGES.get(posixpath.splitext(f["path"])[1].lower(), "")
        files.append(
            {
                "file_path": f["path"],
                "language": language,
                "role_tag": role_tag_for(f["path"]),
                "content": f["content"],
                "targets": extract_imports(f["path"], f["content"], known),
            }
        )
    languages = Counter(f["language"] for f in files if f["language"])
    return {
        "total_raw_files": raw_count,
        "files": files,
        "primary_language": languages.most_common(1)[0][0] if languages else "",
    }
