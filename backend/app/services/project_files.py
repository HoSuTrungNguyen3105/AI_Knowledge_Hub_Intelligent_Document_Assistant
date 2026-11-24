"""Text extraction for uploaded project brief files.

Supported: .txt/.md/.markdown (UTF-8 text), .pdf (pypdf), .docx
(python-docx). Extraction libraries are imported lazily so the rest
of the backend never pays for them unless an upload arrives.
"""

import io

from app.services.ai.base_provider import ProviderError

MAX_FILE_BYTES = 5 * 1024 * 1024
TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def extract_project_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise ProviderError("project_file_too_large")
    if not data:
        raise ProviderError("project_file_empty")
    extension = _extension(filename)
    if extension in TEXT_EXTENSIONS:
        text = data.decode("utf-8", errors="replace")
    elif extension == ".pdf":
        text = _from_pdf(data)
    elif extension == ".docx":
        text = _from_docx(data)
    else:
        raise ProviderError("project_file_unsupported")
    text = text.strip()
    if not text:
        raise ProviderError("project_file_empty")
    return text


def _from_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ProviderError("project_file_unsupported") from None
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        raise ProviderError("project_file_unreadable") from None


def _from_docx(data: bytes) -> str:
    try:
        import docx
    except ImportError:
        raise ProviderError("project_file_unsupported") from None
    try:
        document = docx.Document(io.BytesIO(data))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception:
        raise ProviderError("project_file_unreadable") from None
