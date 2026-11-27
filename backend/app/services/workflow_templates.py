"""Workflow Template Library (phase 1): GitHub importer + shared library.

The importer walks a configured GitHub repository (default:
``enescingoz/awesome-n8n-templates``, CC BY 4.0 — attribution is stored on
every template), downloads the real workflow JSON files, analyses and
security-scans each one, and upserts it into ``shared_workflows`` keyed by
``owner/repo:path`` with a content hash, so re-imports never duplicate and
upstream changes are detected as updates. Templates land as
``pending_review`` and are never executed by the importer.

Analysis is deliberately deterministic (no AI): JSON validity, n8n
structure, node inventory, credential types referenced, community-node
detection, a hardcoded-secret scan over parameter values, and risk flags
for Code nodes, HTTP Request nodes and external write endpoints.
"""

import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings
from app.schemas.workflow_templates import (
    DEFAULT_SOURCE_ATTRIBUTION,
    DEFAULT_SOURCE_LICENSE,
    DEFAULT_SOURCE_NAME,
    DEFAULT_SOURCE_REPO,
    ContributeIn,
    InstallResultItemOut,
    InstallResultOut,
    SyncCandidatesOut,
    TemplateDiffOut,
    TemplateNodeChangeOut,
    TemplateVersionDetailOut,
    TemplateVersionOut,
    TemplateDetailOut,
    TemplateImportLogOut,
    TemplateListOut,
    TemplateNameViIn,
    TemplateReviewIn,
    TemplateSourceCreateIn,
    TemplateSourceOut,
    TemplateStatsOut,
    TemplateSummaryOut,
    TranslateNamesIn,
    TranslateNamesOut,
    UserWorkflowOut,
)
from app.schemas.n8n_platform import N8nWorkflowCreateIn
from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat_types import ChatRequest, ChatTurn
from app.services.credential_bindings import (
    CredentialBindingService,
    apply_bindings_to_nodes,
    credential_coverage,
)
from app.services.n8n_platform import N8nPlatformService
from app.services.template_assistant import TemplateAssistantService

SOURCES_COLLECTION = "workflow_template_sources"
TEMPLATES_COLLECTION = "shared_workflows"
VERSIONS_COLLECTION = "shared_workflow_versions"
IMPORT_LOGS_COLLECTION = "workflow_import_logs"

MAX_FILE_BYTES = 2_000_000
DOWNLOAD_CONCURRENCY = 10
MAX_RECORDED_FAILURES = 100
TRANSLATE_BATCH_SIZE = 40

_TRANSLATION_LINE = re.compile(r"^\s*(\d+)[.)]\s*(.+?)\s*$")


def _parse_translation_lines(text: str, expected: int) -> list[str] | None:
    """Parse a numbered translation reply. Every index 1..expected must
    be present exactly — a partial or merged reply is rejected whole so
    a translation can never land on the wrong template."""
    found: dict[int, str] = {}
    for line in text.splitlines():
        match = _TRANSLATION_LINE.match(line)
        if match:
            found[int(match.group(1))] = match.group(2).strip().strip('"')
    if set(found) != set(range(1, expected + 1)):
        return None
    return [found[index] for index in range(1, expected + 1)]

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),  # OpenAI-style keys
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),  # GitHub personal tokens
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),  # Slack tokens
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),  # Google API keys
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b"),  # Telegram bot tokens
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}"),
]

_STANDARD_PREFIXES = ("n8n-nodes-base.", "@n8n/")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_github_repo(repo_url: str) -> str:
    """Accept https://github.com/owner/repo(.git), git@github.com:owner/repo
    or a bare owner/repo slug; return the slug or raise."""
    value = (repo_url or "").strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    match = re.search(r"github\.com[/:]([^/]+)/([^/]+)$", value)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    if re.fullmatch(r"[^/\s]+/[^/\s]+", value):
        return value
    raise ProviderError("template_source_invalid")


def _iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def scan_secrets(parameters: dict) -> bool:
    """True when a parameter value looks like a hardcoded secret.

    n8n expressions (``={{ ... }}``) and ``$env`` references are the
    sanctioned way to inject secrets, so strings using them are skipped.
    """
    for text in _iter_strings(parameters):
        if "{{" in text or "$env" in text:
            continue
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                return True
    return False


def analyze_workflow(raw_text: str, path: str) -> dict:
    """Analyse one downloaded file. Returns a template fields dict, or a
    dict with ``rejected`` set to the reason code."""
    try:
        data = json.loads(raw_text)
    except (ValueError, TypeError):
        return {"rejected": "invalid_json"}
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list) or not data["nodes"]:
        return {"rejected": "invalid_structure"}
    nodes = [node for node in data["nodes"] if isinstance(node, dict)]
    if not nodes:
        return {"rejected": "invalid_structure"}

    node_types: list[str] = []
    credential_types: list[str] = []
    community_nodes: list[str] = []
    http_urls: list[str] = []
    has_code = False
    has_http = False
    secret_found = False
    for node in nodes:
        node_type = node.get("type")
        is_http = False
        if isinstance(node_type, str) and node_type:
            if node_type not in node_types:
                node_types.append(node_type)
            if not node_type.startswith(_STANDARD_PREFIXES) and node_type not in community_nodes:
                community_nodes.append(node_type)
            lowered = node_type.lower()
            if lowered.endswith(".code") or "code" in lowered.rsplit(".", 1)[-1]:
                has_code = True
            if "httprequest" in lowered.replace("-", ""):
                has_http = True
                is_http = True
        credentials = node.get("credentials")
        if isinstance(credentials, dict):
            for cred_type in credentials:
                if cred_type not in credential_types:
                    credential_types.append(cred_type)
        parameters = node.get("parameters")
        if isinstance(parameters, dict):
            if scan_secrets(parameters):
                secret_found = True
            if is_http:
                url = parameters.get("url")
                if isinstance(url, str) and url and url not in http_urls:
                    http_urls.append(url[:300])

    risk_flags: list[str] = []
    if secret_found:
        risk_flags.append("suspected_hardcoded_secret")
    if has_code:
        risk_flags.append("contains_code_node")
    if has_http:
        risk_flags.append("contains_http_request")
    if community_nodes:
        risk_flags.append("needs_community_nodes")

    node_count = len(nodes)
    complexity = "simple" if node_count <= 5 else "medium" if node_count <= 12 else "complex"
    category = path.split("/", 1)[0] if "/" in path else "Root"
    name = data.get("name") if isinstance(data.get("name"), str) and data.get("name") else path.rsplit("/", 1)[-1].removesuffix(".json")
    return {
        "name": name[:300],
        "category": category,
        "node_count": node_count,
        "node_types": node_types,
        "credential_types": credential_types,
        "complexity": complexity,
        "compatibility": "needs_community_nodes" if community_nodes else "compatible",
        "community_nodes": community_nodes,
        "security_flag": secret_found,
        "risk_flags": risk_flags,
        "has_code_node": has_code,
        "has_http_node": has_http,
        "http_urls": http_urls,
        "workflow_json": data,
    }


class GitHubHTTP:
    """Thin GitHub reader: git trees for the file list, raw URLs for file
    contents (raw downloads do not consume API rate limit)."""

    async def get_json(self, url: str, token: str, timeout_seconds: float):
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=True,
                trust_env=False,
                headers=headers,
            ) as client:
                response = await client.get(url)
        except (httpx.TimeoutException, httpx.RequestError):
            raise ProviderError("github_unreachable") from None
        try:
            data = response.json()
        except ValueError:
            data = None
        return response.status_code, data

    async def get_text(self, url: str, timeout_seconds: float):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=True,
                trust_env=False,
            ) as client:
                response = await client.get(url)
        except (httpx.TimeoutException, httpx.RequestError):
            raise ProviderError("github_unreachable") from None
        return response.status_code, response.text


class WorkflowTemplateService:
    def __init__(self, db: AsyncIOMotorDatabase, settings: Settings, http: GitHubHTTP):
        self.db = db
        self.settings = settings
        self.http = http

    @property
    def sources(self):
        return self.db[SOURCES_COLLECTION]

    @property
    def templates(self):
        return self.db[TEMPLATES_COLLECTION]

    @property
    def logs(self):
        return self.db[IMPORT_LOGS_COLLECTION]

    @property
    def _token(self) -> str:
        if self.settings.github_token is None:
            return ""
        return self.settings.github_token.get_secret_value()

    # -- sources -----------------------------------------------------------

    @staticmethod
    def _source_out(doc: dict, template_count: int) -> TemplateSourceOut:
        return TemplateSourceOut(
            id=str(doc["_id"]),
            name=doc.get("name", ""),
            kind=doc.get("kind", "github"),
            repo=doc.get("repo", ""),
            repo_url=doc.get("repo_url", ""),
            branch=doc.get("branch", "main"),
            license=doc.get("license", ""),
            attribution=doc.get("attribution", ""),
            template_count=template_count,
            last_import_at=doc.get("last_import_at"),
            created_at=doc.get("created_at"),
        )

    async def list_sources(self) -> list[TemplateSourceOut]:
        out = []
        async for doc in self.sources.find({}).sort("created_at", 1):
            count = await self.templates.count_documents({"source_id": str(doc["_id"])})
            out.append(self._source_out(doc, count))
        return out

    async def create_source(self, payload: TemplateSourceCreateIn) -> TemplateSourceOut:
        repo = parse_github_repo(payload.repo_url)
        existing = await self.sources.find_one({"repo": repo, "branch": payload.branch})
        if existing is not None:
            raise ProviderError("template_source_exists")
        is_default = repo == DEFAULT_SOURCE_REPO
        doc = {
            "_id": uuid.uuid4().hex,
            "name": payload.name or (DEFAULT_SOURCE_NAME if is_default else repo),
            "kind": "github",
            "repo": repo,
            "repo_url": f"https://github.com/{repo}",
            "branch": payload.branch,
            "license": DEFAULT_SOURCE_LICENSE if is_default else "",
            "attribution": DEFAULT_SOURCE_ATTRIBUTION if is_default else "",
            "last_import_at": None,
            "created_at": _utcnow(),
        }
        await self.sources.insert_one(doc)
        return self._source_out(doc, 0)

    async def ensure_default_source(self) -> TemplateSourceOut:
        existing = await self.sources.find_one({"repo": DEFAULT_SOURCE_REPO})
        if existing is not None:
            count = await self.templates.count_documents({"source_id": str(existing["_id"])})
            return self._source_out(existing, count)
        return await self.create_source(
            TemplateSourceCreateIn(repo_url=f"https://github.com/{DEFAULT_SOURCE_REPO}")
        )

    async def _get_source(self, source_id: str) -> dict:
        doc = await self.sources.find_one({"_id": source_id})
        if doc is None:
            raise ProviderError("template_source_not_found")
        return doc

    # -- importer ----------------------------------------------------------

    async def start_import(self, source_id: str) -> tuple[TemplateImportLogOut, bool]:
        """Create a ``running`` import log and return it with a started flag.

        The import itself runs in the background (see :meth:`run_import`):
        downloading and analysing hundreds of files takes minutes, far
        beyond the frontend client's 20-second request timeout, so the
        HTTP request must return immediately and the client polls the log.
        If an import for this source is already running, its log is
        returned with ``started=False`` instead of starting a second one.
        """
        source = await self._get_source(source_id)
        running = await self.logs.find_one(
            {"source_id": source_id, "status": "running"},
            sort=[("started_at", -1)],
        )
        if running is not None:
            return self._log_out(running), False
        log = {
            "_id": uuid.uuid4().hex,
            "source_id": source_id,
            "source_repo": source["repo"],
            "status": "running",
            "found": 0,
            "downloaded": 0,
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
            "failures": [],
            "error": None,
            "started_at": _utcnow(),
            "finished_at": None,
        }
        await self.logs.insert_one(dict(log))
        return self._log_out(log), True

    async def run_import(self, log_id: str) -> None:
        """Execute the import for a log created by :meth:`start_import`.

        Progress counters are persisted every 25 processed files so the
        polling client sees real progress; the final state is written at
        the end. Never raises: failures land on the log itself.
        """
        log = await self.logs.find_one({"_id": log_id})
        if log is None:
            return
        source_id = log["source_id"]
        try:
            source = await self._get_source(source_id)
        except ProviderError as exc:
            log["status"] = "failed"
            log["error"] = exc.code
            log["finished_at"] = _utcnow()
            await self.logs.replace_one({"_id": log_id}, log)
            return
        repo = source["repo"]
        branch = source.get("branch", "main")
        try:
            status, tree = await self.http.get_json(
                f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1",
                self._token,
                self.settings.github_import_timeout_seconds,
            )
            if status >= 400 or not isinstance(tree, dict) or not isinstance(tree.get("tree"), list):
                raise ProviderError("github_unreachable")
            paths = [
                item["path"]
                for item in tree["tree"]
                if isinstance(item, dict)
                and item.get("type") == "blob"
                and isinstance(item.get("path"), str)
                and item["path"].lower().endswith(".json")
            ]
            log["found"] = len(paths)
            await self._persist_progress(log)
            progress = {"done": 0}
            semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

            async def process(path: str) -> str:
                async with semaphore:
                    raw_url = (
                        f"https://raw.githubusercontent.com/{repo}/{branch}/"
                        + quote(path, safe="/")
                    )
                    try:
                        status, text = await self.http.get_text(
                            raw_url, self.settings.github_import_timeout_seconds
                        )
                    except ProviderError:
                        return self._record_failure(log, path, "download_failed")
                    if status >= 400:
                        return self._record_failure(log, path, "download_failed")
                    if len(text.encode("utf-8", "ignore")) > MAX_FILE_BYTES:
                        return self._record_failure(log, path, "file_too_large")
                    log["downloaded"] += 1
                    analysis = analyze_workflow(text, path)
                    if "rejected" in analysis:
                        return self._record_failure(log, path, analysis["rejected"])
                    return await self._upsert_template(source, path, text, analysis, log)

            async def tracked(path: str) -> str:
                result = await process(path)
                progress["done"] += 1
                if progress["done"] % 25 == 0:
                    await self._persist_progress(log)
                return result

            await asyncio.gather(*(tracked(path) for path in paths))
            log["status"] = "completed"
        except ProviderError as exc:
            log["status"] = "failed"
            log["error"] = exc.code
        except Exception:  # noqa: BLE001 - the failure belongs on the log
            log["status"] = "failed"
            log["error"] = "import_failed"
        log["finished_at"] = _utcnow()
        await self.logs.replace_one({"_id": log["_id"]}, log)
        await self.sources.update_one(
            {"_id": source_id}, {"$set": {"last_import_at": log["finished_at"]}}
        )

    async def _persist_progress(self, log: dict) -> None:
        await self.logs.update_one(
            {"_id": log["_id"]},
            {
                "$set": {
                    "found": log["found"],
                    "downloaded": log["downloaded"],
                    "created": log["created"],
                    "updated": log["updated"],
                    "unchanged": log["unchanged"],
                    "rejected": log["rejected"],
                    "failures": log["failures"],
                }
            },
        )

    @staticmethod
    def _record_failure(log: dict, path: str, reason: str) -> str:
        log["rejected"] += 1
        if len(log["failures"]) < MAX_RECORDED_FAILURES:
            log["failures"].append({"path": path, "reason": reason})
        return reason

    async def _upsert_template(self, source: dict, path: str, raw_text: str, analysis: dict, log: dict) -> str:
        source_key = f"{source['repo']}:{path}"
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        existing = await self.templates.find_one({"source_key": source_key})
        now = _utcnow()
        fields = {
            "name": analysis["name"],
            "description": "",
            "category": analysis["category"],
            "source_kind": "github",
            "source_id": str(source["_id"]),
            "source_path": path,
            "source_url": f"{source['repo_url']}/blob/{source.get('branch', 'main')}/{quote(path, safe='/')}",
            "node_count": analysis["node_count"],
            "node_types": analysis["node_types"],
            "credential_types": analysis["credential_types"],
            "complexity": analysis["complexity"],
            "compatibility": analysis["compatibility"],
            "community_nodes": analysis["community_nodes"],
            "security_flag": analysis["security_flag"],
            "risk_flags": analysis["risk_flags"],
            "has_code_node": analysis["has_code_node"],
            "has_http_node": analysis["has_http_node"],
            "http_urls": analysis["http_urls"],
            "workflow_json": analysis["workflow_json"],
            "license": source.get("license", ""),
            "attribution": source.get("attribution", ""),
            "content_hash": content_hash,
            "updated_at": now,
        }
        if existing is None:
            fields.update(
                {
                    "_id": uuid.uuid4().hex,
                    "source_key": source_key,
                    "review_status": "pending_review",
                    "version": 1,
                    "created_at": now,
                }
            )
            await self.templates.insert_one(fields)
            await self._store_version(fields, 1)
            log["created"] += 1
            return "created"
        if existing.get("content_hash") == content_hash:
            log["unchanged"] += 1
            return "unchanged"
        fields["version"] = int(existing.get("version", 1)) + 1
        await self.templates.update_one({"_id": existing["_id"]}, {"$set": fields})
        await self._store_version({**existing, **fields}, fields["version"])
        log["updated"] += 1
        return "updated"

    @property
    def versions(self):
        return self.db[VERSIONS_COLLECTION]

    async def _store_version(self, template: dict, version: int) -> None:
        workflow = template.get("workflow_json") or {}
        await self.versions.update_one(
            {"template_id": str(template["_id"]), "version": version},
            {
                "$set": {
                    "workflow_json": workflow,
                    "content_hash": template.get("content_hash", ""),
                    "node_count": len(workflow.get("nodes") or []),
                    "updated_at": _utcnow(),
                },
                "$setOnInsert": {
                    "_id": uuid.uuid4().hex,
                    "template_id": str(template["_id"]),
                    "version": version,
                    "created_at": _utcnow(),
                },
            },
            upsert=True,
        )

    async def _get_template_or_404(self, template_id: str) -> dict:
        doc = await self.templates.find_one({"_id": template_id})
        if doc is None:
            raise ProviderError("template_not_found")
        return doc

    async def list_versions(self, template_id: str) -> list[TemplateVersionOut]:
        await self._get_template_or_404(template_id)
        out = []
        cursor = self.versions.find({"template_id": template_id}).sort("version", -1)
        async for doc in cursor:
            out.append(
                TemplateVersionOut(
                    version=int(doc.get("version", 1)),
                    content_hash=doc.get("content_hash", ""),
                    node_count=int(doc.get("node_count", 0)),
                    created_at=doc.get("created_at"),
                )
            )
        return out

    async def get_version(self, template_id: str, version: int) -> TemplateVersionDetailOut:
        await self._get_template_or_404(template_id)
        doc = await self.versions.find_one(
            {"template_id": template_id, "version": version}
        )
        if doc is None:
            raise ProviderError("template_version_not_found")
        return TemplateVersionDetailOut(
            version=int(doc.get("version", 1)),
            content_hash=doc.get("content_hash", ""),
            node_count=int(doc.get("node_count", 0)),
            created_at=doc.get("created_at"),
            workflow_json=doc.get("workflow_json") or {},
        )

    @staticmethod
    def diff_workflows(old: dict, new: dict) -> TemplateDiffOut:
        def by_name(workflow: dict) -> dict[str, dict]:
            out: dict[str, dict] = {}
            for node in workflow.get("nodes") or []:
                if isinstance(node, dict) and node.get("name"):
                    out[str(node["name"])] = node
            return out

        old_nodes = by_name(old)
        new_nodes = by_name(new)
        changed: list[TemplateNodeChangeOut] = []
        for name in sorted(set(old_nodes) & set(new_nodes)):
            before, after = old_nodes[name], new_nodes[name]
            fields: list[str] = []
            if before.get("type") != after.get("type"):
                fields.append("type")
            old_params = before.get("parameters") or {}
            new_params = after.get("parameters") or {}
            for key in sorted(set(old_params) | set(new_params)):
                if old_params.get(key) != new_params.get(key):
                    fields.append(f"parameters.{key}")
            if fields:
                changed.append(TemplateNodeChangeOut(name=name, changed_fields=fields))
        return TemplateDiffOut(
            from_version=0,
            to_version=0,
            nodes_added=sorted(set(new_nodes) - set(old_nodes)),
            nodes_removed=sorted(set(old_nodes) - set(new_nodes)),
            nodes_changed=changed,
            connections_changed=(old.get("connections") or {}) != (new.get("connections") or {}),
        )

    async def diff_versions(
        self, template_id: str, from_version: int, to_version: int
    ) -> TemplateDiffOut:
        old = await self.get_version(template_id, from_version)
        new = await self.get_version(template_id, to_version)
        diff = self.diff_workflows(old.workflow_json, new.workflow_json)
        diff.from_version = from_version
        diff.to_version = to_version
        return diff

    async def restore_version(self, template_id: str, version: int) -> TemplateDetailOut:
        template = await self._get_template_or_404(template_id)
        snapshot = await self.get_version(template_id, version)
        workflow = snapshot.workflow_json
        raw_text = json.dumps(workflow, ensure_ascii=False, sort_keys=True)
        analysis = analyze_workflow(raw_text, template.get("source_path") or "restored.json")
        if "rejected" in analysis:
            raise ProviderError("template_contribute_invalid")
        now = _utcnow()
        new_version = int(template.get("version", 1)) + 1
        fields = {
            "name": analysis["name"] or template.get("name", ""),
            "category": template.get("category", analysis["category"]),
            "node_count": analysis["node_count"],
            "node_types": analysis["node_types"],
            "credential_types": analysis["credential_types"],
            "complexity": analysis["complexity"],
            "compatibility": analysis["compatibility"],
            "community_nodes": analysis["community_nodes"],
            "security_flag": analysis["security_flag"],
            "risk_flags": analysis["risk_flags"],
            "has_code_node": analysis["has_code_node"],
            "has_http_node": analysis["has_http_node"],
            "http_urls": analysis["http_urls"],
            "workflow_json": workflow,
            "content_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "version": new_version,
            "updated_at": now,
        }
        await self.templates.update_one({"_id": template_id}, {"$set": fields})
        await self._store_version({**template, **fields, "_id": template_id}, new_version)
        return await self.get_template(template_id)

    async def contribute(self, user_id: str, payload: ContributeIn) -> TemplateDetailOut:
        raw_text = json.dumps(payload.workflow_json, ensure_ascii=False)
        analysis = analyze_workflow(raw_text, "community.json")
        if "rejected" in analysis:
            raise ProviderError("template_contribute_invalid")
        now = _utcnow()
        doc = {
            "_id": uuid.uuid4().hex,
            "source_key": f"community:{user_id}:{uuid.uuid4().hex}",
            "name": payload.name,
            "description": "",
            "category": payload.category or analysis["category"],
            "source_kind": "community",
            "source_id": None,
            "source_path": None,
            "source_url": None,
            "node_count": analysis["node_count"],
            "node_types": analysis["node_types"],
            "credential_types": analysis["credential_types"],
            "complexity": analysis["complexity"],
            "compatibility": analysis["compatibility"],
            "community_nodes": analysis["community_nodes"],
            "security_flag": analysis["security_flag"],
            "risk_flags": analysis["risk_flags"],
            "has_code_node": analysis["has_code_node"],
            "has_http_node": analysis["has_http_node"],
            "http_urls": analysis["http_urls"],
            "workflow_json": analysis["workflow_json"],
            "license": "Người đóng góp tự chịu trách nhiệm về bản quyền nội dung.",
            "attribution": "Đóng góp bởi người dùng MindFlow",
            "content_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "review_status": "pending_review",
            "version": 1,
            "created_by": user_id,
            "created_at": now,
            "updated_at": now,
        }
        await self.templates.insert_one(doc)
        await self._store_version(doc, 1)
        return await self.get_template(str(doc["_id"]))

    @staticmethod
    def _log_out(doc: dict) -> TemplateImportLogOut:
        return TemplateImportLogOut(
            id=str(doc["_id"]),
            source_id=doc.get("source_id", ""),
            source_repo=doc.get("source_repo", ""),
            status=doc.get("status", "failed"),
            found=doc.get("found", 0),
            downloaded=doc.get("downloaded", 0),
            created=doc.get("created", 0),
            updated=doc.get("updated", 0),
            unchanged=doc.get("unchanged", 0),
            rejected=doc.get("rejected", 0),
            failures=doc.get("failures") or [],
            error=doc.get("error"),
            started_at=doc.get("started_at"),
            finished_at=doc.get("finished_at"),
        )

    async def list_import_logs(self, source_id: str | None = None, limit: int = 20) -> list[TemplateImportLogOut]:
        query = {"source_id": source_id} if source_id else {}
        cursor = self.logs.find(query).sort("started_at", -1).limit(max(1, min(limit, 50)))
        return [self._log_out(doc) async for doc in cursor]

    # -- library reads + review ---------------------------------------------

    @staticmethod
    def _summary_out(doc: dict) -> TemplateSummaryOut:
        return TemplateSummaryOut(
            id=str(doc["_id"]),
            name=doc.get("name", ""),
            name_vi=doc.get("name_vi"),
            category=doc.get("category", ""),
            source_kind=doc.get("source_kind", "github"),
            source_id=doc.get("source_id"),
            source_path=doc.get("source_path"),
            source_url=doc.get("source_url"),
            node_count=doc.get("node_count", 0),
            node_types=doc.get("node_types") or [],
            credential_types=doc.get("credential_types") or [],
            complexity=doc.get("complexity", "simple"),
            compatibility=doc.get("compatibility", "compatible"),
            community_nodes=doc.get("community_nodes") or [],
            security_flag=bool(doc.get("security_flag")),
            risk_flags=doc.get("risk_flags") or [],
            review_status=doc.get("review_status", "pending_review"),
            version=int(doc.get("version", 1)),
            license=doc.get("license", ""),
            attribution=doc.get("attribution", ""),
            updated_at=doc.get("updated_at"),
        )

    async def list_templates(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        source_id: str | None = None,
        review_status: str | None = None,
        compatibility: str | None = None,
        complexity: str | None = None,
        service: str | None = None,
        sort: str = "name",
        limit: int = 50,
        offset: int = 0,
    ) -> TemplateListOut:
        query: dict = {}
        if category:
            query["category"] = category
        if source_id:
            query["source_id"] = source_id
        if review_status:
            query["review_status"] = review_status
        if compatibility:
            query["compatibility"] = compatibility
        if complexity:
            query["complexity"] = complexity
        or_groups = []
        if service:
            or_groups.append(
                {
                    "$or": [
                        {"credential_types": service},
                        {"node_types": {"$regex": re.escape(service), "$options": "i"}},
                    ]
                }
            )
        if q:
            pattern = {"$regex": re.escape(q), "$options": "i"}
            or_groups.append({"$or": [{"name": pattern}, {"name_vi": pattern}]})
        if len(or_groups) == 1:
            query.update(or_groups[0])
        elif or_groups:
            query["$and"] = or_groups
        total = await self.templates.count_documents(query)
        sort_field = {
            "name": ("name", 1),
            "newest": ("updated_at", -1),
            "nodes": ("node_count", -1),
        }.get(sort, ("name", 1))
        cursor = (
            self.templates.find(query, {"workflow_json": 0})
            .sort(sort_field[0], sort_field[1])
            .skip(max(0, offset))
            .limit(max(1, min(limit, 100)))
        )
        items = [self._summary_out(doc) async for doc in cursor]
        return TemplateListOut(items=items, total=total)

    async def template_stats(self) -> TemplateStatsOut:
        by_category: dict[str, int] = {}
        by_review: dict[str, int] = {}
        by_compat: dict[str, int] = {}
        services: set[str] = set()
        total = 0
        cursor = self.templates.find(
            {}, {"category": 1, "review_status": 1, "compatibility": 1, "credential_types": 1}
        )
        async for doc in cursor:
            total += 1
            by_category[doc.get("category", "")] = by_category.get(doc.get("category", ""), 0) + 1
            by_review[doc.get("review_status", "")] = by_review.get(doc.get("review_status", ""), 0) + 1
            by_compat[doc.get("compatibility", "")] = by_compat.get(doc.get("compatibility", ""), 0) + 1
            for cred in doc.get("credential_types") or []:
                services.add(cred)
        return TemplateStatsOut(
            total=total,
            by_category=dict(sorted(by_category.items())),
            by_review_status=by_review,
            by_compatibility=by_compat,
            services=sorted(services),
        )

    async def get_template(self, template_id: str) -> TemplateDetailOut:
        doc = await self.templates.find_one({"_id": template_id})
        if doc is None:
            raise ProviderError("template_not_found")
        summary = self._summary_out(doc)
        return TemplateDetailOut(
            **summary.model_dump(),
            description=doc.get("description", ""),
            has_code_node=bool(doc.get("has_code_node")),
            has_http_node=bool(doc.get("has_http_node")),
            http_urls=doc.get("http_urls") or [],
            workflow_json=doc.get("workflow_json") or {},
        )

    async def review_template(self, template_id: str, payload: TemplateReviewIn) -> TemplateSummaryOut:
        result = await self.templates.update_one(
            {"_id": template_id},
            {"$set": {"review_status": payload.review_status, "updated_at": _utcnow()}},
        )
        if result.matched_count == 0:
            raise ProviderError("template_not_found")
        doc = await self.templates.find_one({"_id": template_id}, {"workflow_json": 0})
        return self._summary_out(doc)

    async def rename_name_vi(
        self, template_id: str, payload: TemplateNameViIn
    ) -> TemplateSummaryOut:
        cleaned = (payload.name_vi or "").strip() or None
        result = await self.templates.update_one(
            {"_id": template_id},
            {"$set": {"name_vi": cleaned, "updated_at": _utcnow()}},
        )
        if result.matched_count == 0:
            raise ProviderError("template_not_found")
        doc = await self.templates.find_one({"_id": template_id}, {"workflow_json": 0})
        return self._summary_out(doc)

    async def translate_names(
        self, user_id, chat_http, payload: TranslateNamesIn
    ) -> TranslateNamesOut:
        """Bulk-translate template names into Vietnamese with the user's
        own configured AI provider (same candidate resolution as the
        template assistant). Only templates without a Vietnamese name
        are touched, so re-running is cheap and idempotent; a batch
        whose reply does not parse completely is skipped, never
        half-applied."""
        query = {
            "$or": [
                {"name_vi": {"$exists": False}},
                {"name_vi": None},
                {"name_vi": ""},
            ]
        }
        total_pending = await self.templates.count_documents(query)
        docs: list[tuple[str, str]] = []
        cursor = (
            self.templates.find(query, {"name": 1}).sort("name", 1).limit(payload.limit)
        )
        async for doc in cursor:
            if doc.get("name"):
                docs.append((str(doc["_id"]), doc["name"]))
        if not docs:
            return TranslateNamesOut(translated=0, remaining=total_pending)
        assistant = TemplateAssistantService(self.db, self.settings, chat_http)
        candidates = await assistant._resolve_candidates(
            user_id, payload.provider, payload.model
        )
        if not candidates:
            raise ProviderError("credentials_missing")
        translated = 0
        failed_batches = 0
        for start in range(0, len(docs), TRANSLATE_BATCH_SIZE):
            batch = docs[start : start + TRANSLATE_BATCH_SIZE]
            mapping = await self._translate_batch(
                chat_http, candidates, [name for _id, name in batch]
            )
            if mapping is None:
                failed_batches += 1
                continue
            for (template_id, _name), translated_name in zip(batch, mapping):
                await self.templates.update_one(
                    {"_id": template_id},
                    {"$set": {"name_vi": translated_name, "updated_at": _utcnow()}},
                )
                translated += 1
        return TranslateNamesOut(
            translated=translated,
            remaining=max(0, total_pending - translated),
            failed_batches=failed_batches,
            provider=candidates[0][0],
            model=candidates[0][1],
        )

    async def _translate_batch(self, chat_http, candidates, names) -> list[str] | None:
        numbered = "\n".join(
            f"{index + 1}. {name}" for index, name in enumerate(names)
        )
        prompt = (
            "Dịch tên các workflow n8n sau sang tiếng Việt tự nhiên, ngắn gọn, dễ hiểu. "
            "Giữ nguyên tên riêng và thuật ngữ công nghệ (Gmail, Google Sheets, Drive, "
            "OpenAI, Telegram, AI, API, RAG, CRM...). "
            f"Trả về đúng {len(names)} dòng theo định dạng \"số. bản dịch\", "
            f"không thêm giải thích.\n\n{numbered}"
        )
        for cand_provider, cand_model, cand_key in candidates[:3]:
            try:
                adapter = create_provider(cand_provider, chat_http=chat_http)
            except Exception:  # noqa: BLE001 - try the next candidate
                continue
            for budget in (4096, 2048):
                request = ChatRequest(
                    model=cand_model,
                    turns=(ChatTurn("user", prompt),),
                    max_output_tokens=budget,
                )
                chunks: list[str] = []

                async def collect() -> None:
                    async for event in adapter.stream_chat(cand_key, request):
                        if event.kind == "delta":
                            chunks.append(event.text)

                try:
                    await asyncio.wait_for(collect(), timeout=120)
                except Exception:  # noqa: BLE001 - next budget / candidate
                    continue
                parsed = _parse_translation_lines("".join(chunks), len(names))
                if parsed is not None:
                    return parsed
        return None


# -- Phase 3: per-user sync -------------------------------------------------

USER_WORKFLOWS_COLLECTION = "user_workflows"


class WorkflowSyncService:
    """Installs approved shared templates into the user's n8n and tracks
    the mapping per user.

    Installing reuses the n8n Platform create path (workflow lands
    inactive in n8n); updating PUTs the new template definition over
    the installed copy; removing deletes the copy from n8n and then the
    mapping — the shared template itself is never touched. Because the
    current platform is one shared n8n instance, ownership lives in this
    mapping, exactly as audited in the Phase 0 report.
    """

    def __init__(self, db: AsyncIOMotorDatabase, platform: "N8nPlatformService"):
        self.db = db
        self.platform = platform
        self.bindings = CredentialBindingService(db, platform)

    @property
    def installs(self):
        return self.db[USER_WORKFLOWS_COLLECTION]

    @property
    def templates(self):
        return self.db[TEMPLATES_COLLECTION]

    @staticmethod
    def _install_out(
        doc: dict,
        template: dict | None,
        missing_credential_types: list[str] | None = None,
    ) -> UserWorkflowOut:
        latest = int(template.get("version", doc.get("installed_version", 1))) if template else int(doc.get("installed_version", 1))
        installed = int(doc.get("installed_version", 1))
        return UserWorkflowOut(
            id=str(doc["_id"]),
            template_id=doc.get("template_id", ""),
            template_name=(template or {}).get("name_vi")
            or (template or {}).get("name", doc.get("template_name", "")),
            category=(template or {}).get("category", ""),
            n8n_workflow_id=doc.get("n8n_workflow_id", ""),
            installed_version=installed,
            latest_version=latest,
            update_available=latest > installed,
            installed_at=doc.get("installed_at"),
            updated_at=doc.get("updated_at"),
            missing_credential_types=missing_credential_types or [],
        )

    async def list_mine(self, user_id: str) -> list[UserWorkflowOut]:
        bindings = await self.bindings.bindings_map(user_id)
        out = []
        cursor = self.installs.find({"user_id": user_id}).sort("installed_at", -1)
        async for doc in cursor:
            template = await self.templates.find_one(
                {"_id": doc["template_id"]}, {"workflow_json": 0}
            )
            missing: list[str] = []
            if template is not None and not doc.get("customized"):
                # The template's extracted credential types minus the
                # user's bindings: those nodes still carry the author's
                # credential ids in the user's n8n. Customized installs
                # are skipped — their definition lives only in n8n.
                needed = {str(t) for t in template.get("credential_types") or []}
                missing = sorted(needed - set(bindings))
            out.append(self._install_out(doc, template, missing))
        return out

    async def sync_candidates(self, user_id: str) -> SyncCandidatesOut:
        mine = await self.list_mine(user_id)
        installed_ids = {item.template_id for item in mine}
        updates = [item for item in mine if item.update_available]
        available = []
        cursor = self.templates.find(
            {"review_status": "approved"}, {"workflow_json": 0}
        ).sort("name", 1)
        async for doc in cursor:
            if str(doc["_id"]) not in installed_ids:
                available.append(WorkflowTemplateService._summary_out(doc))
        return SyncCandidatesOut(available=available, updates=updates)

    @staticmethod
    def _display_name(template: dict) -> str:
        workflow = template.get("workflow_json") or {}
        return (
            template.get("name_vi")
            or template.get("name")
            or workflow.get("name")
            or "Workflow template"
        )

    @staticmethod
    def _coverage(
        template: dict, bindings: dict | None
    ) -> tuple[list[str], list[str]]:
        """(rewritten, missing) credential types for the template's
        definition against the user's bindings — reported on install
        results so an install never silently keeps author credential
        ids the user's n8n does not have."""
        workflow = template.get("workflow_json") or {}
        return credential_coverage(workflow.get("nodes") or [], bindings or {})

    @staticmethod
    def _create_payload(
        template: dict, bindings: dict | None = None
    ) -> "N8nWorkflowCreateIn":
        workflow = template.get("workflow_json") or {}
        nodes = workflow.get("nodes") or []
        if bindings:
            # Re-point every node credential the user has bound to their
            # own n8n credential; unbound types pass through untouched.
            nodes, _applied = apply_bindings_to_nodes(nodes, bindings)
        return N8nWorkflowCreateIn(
            name=WorkflowSyncService._display_name(template),
            nodes=nodes,
            connections=workflow.get("connections") or {},
            settings=workflow.get("settings") or {},
        )

    async def install(self, user_id: str, template_ids: list[str]) -> InstallResultOut:
        bindings = await self.bindings.bindings_map(user_id)
        results: list[InstallResultItemOut] = []
        for template_id in template_ids:
            template = await self.templates.find_one({"_id": template_id})
            if template is None:
                results.append(
                    InstallResultItemOut(
                        template_id=template_id, status="failed", error="template_not_found"
                    )
                )
                continue
            name = self._display_name(template)
            if template.get("review_status") != "approved":
                results.append(
                    InstallResultItemOut(
                        template_id=template_id,
                        template_name=name,
                        status="failed",
                        error="template_not_approved",
                    )
                )
                continue
            rewritten, missing = self._coverage(template, bindings)
            existing = await self.installs.find_one(
                {"user_id": user_id, "template_id": template_id}
            )
            if existing is not None:
                results.append(
                    InstallResultItemOut(
                        template_id=template_id,
                        template_name=name,
                        status="already_installed",
                        n8n_workflow_id=existing.get("n8n_workflow_id"),
                        missing_credential_types=missing,
                        rewritten_credential_types=rewritten,
                    )
                )
                continue
            try:
                created = await self.platform.create_workflow(
                    self._create_payload(template, bindings)
                )
            except ProviderError as exc:
                results.append(
                    InstallResultItemOut(
                        template_id=template_id,
                        template_name=name,
                        status="failed",
                        error=exc.code,
                    )
                )
                continue
            now = _utcnow()
            doc = {
                "_id": uuid.uuid4().hex,
                "user_id": user_id,
                "template_id": template_id,
                "template_name": name,
                "n8n_workflow_id": created.id,
                "installed_version": int(template.get("version", 1)),
                "installed_at": now,
                "updated_at": now,
            }
            await self.installs.insert_one(doc)
            results.append(
                InstallResultItemOut(
                    template_id=template_id,
                    template_name=name,
                    status="installed",
                    n8n_workflow_id=created.id,
                    missing_credential_types=missing,
                    rewritten_credential_types=rewritten,
                )
            )
        return InstallResultOut(results=results)

    async def install_custom(
        self, user_id: str, template: dict, workflow_json: dict, name: str | None
    ) -> UserWorkflowOut:
        """Install a user-approved customized copy of a template (Phase 5).

        The copy lives only in the user's n8n and in this mapping; the
        shared template is never modified. Marked via the name suffix so
        the user can tell it apart from a pristine install.
        """
        # AI-generated proposals do not always match the strict create
        # schema (connections emitted as a list, non-dict node entries,
        # oversized names) — feeding them in raw used to surface as a
        # pydantic ValidationError and a bare 500. Sanitise first.
        raw_nodes = workflow_json.get("nodes")
        nodes = (
            [node for node in raw_nodes if isinstance(node, dict)]
            if isinstance(raw_nodes, list)
            else []
        )
        if not nodes:
            raise ProviderError("template_contribute_invalid")
        connections = workflow_json.get("connections")
        if not isinstance(connections, dict):
            connections = {}
        settings = workflow_json.get("settings")
        if not isinstance(settings, dict):
            settings = {}
        bindings = await self.bindings.bindings_map(user_id)
        _rewritten, missing = credential_coverage(nodes, bindings)
        if bindings:
            nodes, _applied = apply_bindings_to_nodes(nodes, bindings)
        resolved_name = (name or f"{template.get('name', 'Workflow')} (tùy chỉnh)")[:200]
        payload = N8nWorkflowCreateIn(
            name=resolved_name,
            nodes=nodes,
            connections=connections,
            settings=settings,
        )
        created = await self.platform.create_workflow(payload)
        now = _utcnow()
        doc = {
            "_id": uuid.uuid4().hex,
            "user_id": user_id,
            "template_id": str(template["_id"]),
            "template_name": payload.name,
            "n8n_workflow_id": created.id,
            "installed_version": int(template.get("version", 1)),
            "customized": True,
            "installed_at": now,
            "updated_at": now,
        }
        await self.installs.insert_one(doc)
        return self._install_out(doc, template, missing)

    async def _get_install(self, user_id: str, install_id: str) -> dict:
        doc = await self.installs.find_one({"_id": install_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("user_workflow_not_found")
        return doc

    async def update_install(self, user_id: str, install_id: str) -> UserWorkflowOut:
        doc = await self._get_install(user_id, install_id)
        template = await self.templates.find_one({"_id": doc["template_id"]})
        if template is None:
            raise ProviderError("template_not_found")
        bindings = await self.bindings.bindings_map(user_id)
        _rewritten, missing = self._coverage(template, bindings)
        await self.platform.replace_workflow(
            doc["n8n_workflow_id"], self._create_payload(template, bindings)
        )
        await self.installs.update_one(
            {"_id": install_id},
            {
                "$set": {
                    "installed_version": int(template.get("version", 1)),
                    "template_name": self._display_name(template),
                    "updated_at": _utcnow(),
                }
            },
        )
        updated = await self.installs.find_one({"_id": install_id})
        return self._install_out(updated, template, missing)

    async def remove_install(self, user_id: str, install_id: str) -> None:
        doc = await self._get_install(user_id, install_id)
        await self.platform.delete_workflow(doc["n8n_workflow_id"])
        await self.installs.delete_one({"_id": install_id})
