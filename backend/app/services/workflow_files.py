"""Website ZIP artifacts for Phase 6 workflows (output_type="website_zip").

The Developer agent returns the whole website — either a standalone static
site or a complete front-end project source (React/Vite/Tailwind, detected
by a package.json) — as fenced file blocks:

    ```file:path/to/file.ext
    <file content>
    ```

This module is the security boundary between untrusted model output and
anything stored or downloaded: it extracts blocks, normalises paths (no
traversal, no absolute paths), enforces a text-extension allowlist and the
central size limits from Settings, and builds the ZIP fully in memory with
the stdlib. Nothing here executes agent content.
"""

import html
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field

# Text-only extensions a website or front-end project source may ship
# (static HTML/CSS/JS plus React/Vite/Tailwind project files: .jsx/.ts/.tsx
# and plain-text config modules). Executables, scripts that a server could
# run (sh/bat/py/php/...) and binaries are never accepted.
ALLOWED_EXTENSIONS = {
    "html",
    "css",
    "js",
    "mjs",
    "cjs",
    "jsx",
    "ts",
    "mts",
    "cts",
    "tsx",
    "json",
    "md",
    "txt",
    "svg",
    "xml",
}

_BLOCK_RE = re.compile(r"```file:([^\n`]+)\r?\n(.*?)```", re.DOTALL)
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class ArtifactLimits:
    max_files: int = 50
    max_file_bytes: int = 262_144
    max_total_bytes: int = 2_097_152

    @classmethod
    def from_settings(cls, settings) -> "ArtifactLimits":
        return cls(
            max_files=settings.artifact_max_files,
            max_file_bytes=settings.artifact_max_file_bytes,
            max_total_bytes=settings.artifact_max_total_bytes,
        )


@dataclass
class ParsedFile:
    path: str
    content: str

    @property
    def size_bytes(self) -> int:
        return len(self.content.encode("utf-8"))


@dataclass
class ExtractionResult:
    files: list[ParsedFile] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    limit_hit: bool = False

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)

    @property
    def mode(self) -> str:
        """Artifact kind derived from the extracted files.

        ``project`` when a package.json is present (React/Vite/Tailwind
        source the user builds themselves); otherwise ``static``.
        """
        basenames = {f.path.rsplit("/", 1)[-1].lower() for f in self.files}
        return "project" if "package.json" in basenames else "static"

    @property
    def error_code(self) -> str | None:
        """Fatal artifact error, or None when a usable artifact was extracted.

        Static mode needs an index.html entry. Project mode needs
        package.json plus at least one real source file (under src/) or an
        index.html — a bare package.json is not a runnable project.
        """
        if not self.files:
            return "artifact_no_files"
        basenames = {f.path.rsplit("/", 1)[-1].lower() for f in self.files}
        has_index = "index.html" in basenames
        if self.mode == "project":
            has_src = any(
                f.path.startswith("src/") or "/src/" in f.path for f in self.files
            )
            return None if (has_src or has_index) else "artifact_missing_entry"
        if not has_index:
            return "artifact_missing_entry"
        return None


def normalize_path(raw: str) -> str | None:
    """Return a safe relative path, or None when the raw path is unsafe."""
    path = raw.strip().replace("\\", "/")
    if not path or path.startswith("/") or _DRIVE_RE.match(path):
        return None
    segments = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == ".." or segment.startswith("."):
            return None
        if not _SEGMENT_RE.match(segment):
            return None
        segments.append(segment)
    if not segments:
        return None
    return "/".join(segments)


def _extension(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def extract_files(text: str, limits: ArtifactLimits) -> ExtractionResult:
    """Extract + validate file blocks from raw agent output.

    Unsafe or oversized blocks are rejected individually and reported; the
    count/total limits cut the remainder and set ``limit_hit`` so the caller
    can surface exactly what was dropped instead of silently storing a
    partial website.
    """
    result = ExtractionResult()
    seen: set[str] = set()
    for raw_path, content in _BLOCK_RE.findall(text or ""):
        path = normalize_path(raw_path)
        if path is None:
            result.rejected.append({"path": raw_path.strip()[:120], "reason": "unsafe_path"})
            continue
        if _extension(path) not in ALLOWED_EXTENSIONS:
            result.rejected.append({"path": path, "reason": "extension_not_allowed"})
            continue
        if path.lower() in seen:
            result.rejected.append({"path": path, "reason": "duplicate_path"})
            continue
        parsed = ParsedFile(path=path, content=content.strip("\n"))
        if parsed.size_bytes > limits.max_file_bytes:
            result.rejected.append({"path": path, "reason": "file_too_large"})
            continue
        if len(result.files) >= limits.max_files or (
            result.total_bytes + parsed.size_bytes > limits.max_total_bytes
        ):
            result.limit_hit = True
            result.rejected.append({"path": path, "reason": "limit_exceeded"})
            continue
        seen.add(path.lower())
        result.files.append(parsed)
    result.files.sort(key=lambda f: f.path)
    return result


# Candidate entry source files for a Vite-style project, in preference order.
_ENTRY_SOURCES = (
    "src/main.jsx",
    "src/main.tsx",
    "src/main.js",
    "src/main.ts",
    "src/index.jsx",
    "src/index.tsx",
    "src/index.js",
)

_VITE_INDEX_TEMPLATE = """<!doctype html>
<html lang="vi">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/{entry}"></script>
  </body>
</html>
"""


def ensure_project_entry(result: ExtractionResult, title: str) -> str | None:
    """Guarantee a project artifact has its entry ``index.html`` at the
    project root (next to package.json), repairing the common model mistake
    of shipping only ``public/index.html`` (a Create React App convention —
    Vite ignores it as an entry and the project then cannot start).

    - A ``public/index.html`` that already loads the src entry as a module
      is MOVED to the root.
    - Otherwise a standard Vite ``index.html`` is synthesised pointing at
      the project's real entry source (``src/main.jsx`` etc.).
    Returns the entry path when a repair happened, else None. Static
    artifacts and projects that already have a root index.html are left
    untouched; when no entry source exists nothing is invented and the
    caller keeps the previous validation behaviour.
    """
    if result.mode != "project" or not result.files:
        return None
    package = next(
        (f for f in result.files if f.path.rsplit("/", 1)[-1].lower() == "package.json"),
        None,
    )
    if package is None:
        return None
    prefix = package.path[: -len("package.json")]
    entry_path = f"{prefix}index.html"
    if any(f.path == entry_path for f in result.files):
        return None
    public_index = next(
        (f for f in result.files if f.path == f"{prefix}public/index.html"), None
    )
    if (
        public_index is not None
        and 'type="module"' in public_index.content
        and "/src/" in public_index.content
    ):
        public_index.path = entry_path
        result.files.sort(key=lambda f: f.path)
        return entry_path
    entry_source = next(
        (f"{prefix}{name}" for name in _ENTRY_SOURCES
         if any(f.path == f"{prefix}{name}" for f in result.files)),
        None,
    )
    if entry_source is None:
        return None
    content = _VITE_INDEX_TEMPLATE.format(
        title=html.escape(title or "MindFlow Website", quote=True),
        entry=entry_source,
    )
    result.files.append(ParsedFile(path=entry_path, content=content))
    result.files.sort(key=lambda f: f.path)
    return entry_path


def slugify(title: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:60].strip("-") or "workflow-website"


def _guide_markdown(title: str, goal: str, mode: str = "static") -> str:
    header = (
        "# Hướng dẫn sử dụng\n\n"
        "> File này do HỆ THỐNG MindFlow AI tự sinh khi đóng gói ZIP "
        "(không phải nội dung do Agent viết).\n\n"
        f"- Workflow: {title}\n"
        f"- Mục tiêu: {goal}\n\n"
    )
    if mode == "project":
        return header + (
            "## Loại sản phẩm: Source project (React/Vite/Tailwind…)\n\n"
            "> Lưu ý trung thực: source này được đóng gói từ kết quả Agent "
            "trả về, **chưa được build thử trên server** (server không chạy "
            "code/npm theo chính sách an toàn). Hãy tự kiểm tra bằng các lệnh "
            "dưới đây.\n\n"
            "## Cách chạy\n\n"
            "Yêu cầu: Node.js LTS đã cài trên máy.\n\n"
            "1. Giải nén toàn bộ file ZIP vào một thư mục.\n"
            "2. Mở terminal tại thư mục chứa `package.json` và cài thư viện:\n\n"
            "   ```sh\n   npm install\n   ```\n\n"
            "3. Chạy môi trường phát triển:\n\n"
            "   ```sh\n   npm run dev\n   ```\n\n"
            "4. Kiểm tra bản build production:\n\n"
            "   ```sh\n   npm run build\n   ```\n\n"
            "Nếu Agent có kèm `README.md` riêng, ưu tiên làm theo README đó "
            "cho các chi tiết riêng của project.\n"
        )
    return header + (
        "## Loại sản phẩm: Website tĩnh\n\n"
        "## Cách chạy\n\n"
        "1. Giải nén toàn bộ file ZIP vào một thư mục.\n"
        "2. Mở file `index.html` bằng trình duyệt — website tĩnh này chạy "
        "trực tiếp, không cần cài thêm máy chủ hay thư viện.\n"
        "3. Muốn chia sẻ/hosting: tải toàn bộ thư mục lên bất kỳ dịch vụ "
        "hosting web tĩnh nào, giữ nguyên cấu trúc thư mục.\n"
    )


def artifact_mode(files: list[ParsedFile]) -> str:
    basenames = {f.path.rsplit("/", 1)[-1].lower() for f in files}
    return "project" if "package.json" in basenames else "static"


def build_zip(files: list[ParsedFile], title: str, goal: str) -> bytes:
    """Assemble the downloadable ZIP in memory from validated stored files."""
    buffer = io.BytesIO()
    names = {f.path.lower() for f in files}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for parsed in files:
            archive.writestr(parsed.path, parsed.content)
        basenames = {name.rsplit("/", 1)[-1] for name in names}
        if "readme.md" not in basenames and "huong-dan.md" not in basenames:
            archive.writestr(
                "HUONG-DAN.md", _guide_markdown(title, goal, artifact_mode(files))
            )
    return buffer.getvalue()
