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
    TemplateDetailOut,
    TemplateImportLogOut,
    TemplateListOut,
    TemplateReviewIn,
    TemplateSourceCreateIn,
    TemplateSourceOut,
    TemplateStatsOut,
    TemplateSummaryOut,
)
from app.services.ai.base_provider import ProviderError

SOURCES_COLLECTION = "workflow_template_sources"
TEMPLATES_COLLECTION = "shared_workflows"
IMPORT_LOGS_COLLECTION = "workflow_import_logs"

MAX_FILE_BYTES = 2_000_000
DOWNLOAD_CONCURRENCY = 10
MAX_RECORDED_FAILURES = 100

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

    async def import_source(self, source_id: str) -> TemplateImportLogOut:
        source = await self._get_source(source_id)
        repo = source["repo"]
        branch = source.get("branch", "main")
        started = _utcnow()
        log = {
            "_id": uuid.uuid4().hex,
            "source_id": source_id,
            "source_repo": repo,
            "status": "failed",
            "found": 0,
            "downloaded": 0,
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
            "failures": [],
            "error": None,
            "started_at": started,
            "finished_at": None,
        }
        await self.logs.insert_one(dict(log))
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

            await asyncio.gather(*(process(path) for path in paths))
            log["status"] = "completed"
        except ProviderError as exc:
            log["error"] = exc.code
        log["finished_at"] = _utcnow()
        await self.logs.replace_one({"_id": log["_id"]}, log)
        await self.sources.update_one(
            {"_id": source_id}, {"$set": {"last_import_at": log["finished_at"]}}
        )
        return self._log_out(log)

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
            log["created"] += 1
            return "created"
        if existing.get("content_hash") == content_hash:
            log["unchanged"] += 1
            return "unchanged"
        fields["version"] = int(existing.get("version", 1)) + 1
        await self.templates.update_one({"_id": existing["_id"]}, {"$set": fields})
        log["updated"] += 1
        return "updated"

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
        if service:
            query["$or"] = [
                {"credential_types": service},
                {"node_types": {"$regex": re.escape(service), "$options": "i"}},
            ]
        if q:
            query["name"] = {"$regex": re.escape(q), "$options": "i"}
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
