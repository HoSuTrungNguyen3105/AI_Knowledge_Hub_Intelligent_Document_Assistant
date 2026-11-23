"""Website ZIP artifacts for Phase 6 workflows (output_type="website_zip").

The Developer agent returns the whole static website as fenced file blocks:

    ```file:path/to/file.ext
    <file content>
    ```

This module is the security boundary between untrusted model output and
anything stored or downloaded: it extracts blocks, normalises paths (no
traversal, no absolute paths), enforces a text-extension allowlist and the
central size limits from Settings, and builds the ZIP fully in memory with
the stdlib. Nothing here executes agent content.
"""

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field

# Text-only extensions a static website may ship. Executables, scripts that a
# server could run (sh/bat/py/php/...) and binaries are never accepted.
ALLOWED_EXTENSIONS = {
    "html",
    "css",
    "js",
    "mjs",
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
    def error_code(self) -> str | None:
        """Fatal artifact error, or None when a usable website was extracted."""
        if not self.files:
            return "artifact_no_files"
        if not any(f.path.lower() == "index.html" for f in self.files):
            return "artifact_missing_index"
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


def slugify(title: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:60].strip("-") or "workflow-website"


def _guide_markdown(title: str, goal: str) -> str:
    return (
        "# Hướng dẫn sử dụng website\n\n"
        "> File này do HỆ THỐNG MindFlow AI tự sinh khi đóng gói ZIP "
        "(không phải nội dung do Agent viết).\n\n"
        f"- Workflow: {title}\n"
        f"- Mục tiêu: {goal}\n\n"
        "## Cách chạy\n\n"
        "1. Giải nén toàn bộ file ZIP vào một thư mục.\n"
        "2. Mở file `index.html` bằng trình duyệt — website tĩnh này chạy "
        "trực tiếp, không cần cài thêm máy chủ hay thư viện.\n"
        "3. Muốn chia sẻ/hosting: tải toàn bộ thư mục lên bất kỳ dịch vụ "
        "hosting web tĩnh nào, giữ nguyên cấu trúc thư mục.\n"
    )


def build_zip(files: list[ParsedFile], title: str, goal: str) -> bytes:
    """Assemble the downloadable ZIP in memory from validated stored files."""
    buffer = io.BytesIO()
    names = {f.path.lower() for f in files}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for parsed in files:
            archive.writestr(parsed.path, parsed.content)
        basenames = {name.rsplit("/", 1)[-1] for name in names}
        if "readme.md" not in basenames and "huong-dan.md" not in basenames:
            archive.writestr("HUONG-DAN.md", _guide_markdown(title, goal))
    return buffer.getvalue()
