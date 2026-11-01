from __future__ import annotations

import html
import hashlib
import json
import logging
import math
import re
import shutil
import subprocess
import time
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from typing import Any, Iterator, Protocol
from urllib.parse import quote, urlencode
from xml.etree import ElementTree

import httpx


class _CredentialLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = re.sub(r"([?&](?:api_key|apikey|access_token)=)[^&\s\"]+", r"\1[redacted]", message, flags=re.I)
        record.args = ()
        return True


# Some providers require query-string keys; httpx logs full request URLs at INFO.
logging.getLogger("httpx").addFilter(_CredentialLogFilter())

SOURCE_METADATA = {
    "fixture": {"label": "Fixture", "requires_credentials": False, "live": False},
    "semantic_scholar": {"label": "Semantic Scholar", "requires_credentials": False, "live": True},
    "openalex": {"label": "OpenAlex", "requires_credentials": False, "live": True},
    "crossref": {"label": "Crossref", "requires_credentials": False, "live": True},
    "arxiv": {"label": "arXiv", "requires_credentials": False, "live": True},
    "pubmed": {"label": "PubMed", "requires_credentials": False, "live": True},
    "doaj": {"label": "DOAJ", "description": "跨学科开放获取期刊文章", "requires_credentials": False, "live": True},
    "datacite": {"label": "DataCite", "description": "机构仓储、预印本、学位论文及其他文字类学术成果", "requires_credentials": False, "live": True},
    "hal": {"label": "HAL", "description": "跨学科机构仓储、会议论文和学位论文", "requires_credentials": False, "live": True},
    "europe_pmc": {"label": "Europe PMC", "description": "生命科学与医学文献，含预印本和开放全文链接", "requires_credentials": False, "live": True},
    "google_scholar": {"label": "Google Scholar", "description": "通过 SerpApi 检索谷歌学术；按服务额度计费，通常返回检索片段。", "requires_credentials": True, "live": True, "added_by_default": False,
        "credential_field": "serpapi_api_key", "credential_label": "SerpApi API Key", "access_mode": "第三方服务 · SerpApi", "docs_url": "https://serpapi.com/google-scholar-api"},
    "core": {"label": "CORE", "description": "跨学科开放获取仓储，提供论文元数据及可用摘要。需注册申请 API Key。", "requires_credentials": True, "live": True, "added_by_default": False,
        "credential_field": "core_api_key", "credential_label": "CORE API Key", "access_mode": "官方 API · 需密钥", "docs_url": "https://core.ac.uk/services/api"},
}
for _name, _description, _docs in (
    ("semantic_scholar", "跨学科论文、摘要与引用信息；可选密钥可改善额度。", "https://www.semanticscholar.org/product/api"),
    ("openalex", "跨学科学术元数据和开放获取链接，支持 API Key。", "https://docs.openalex.org/"),
    ("crossref", "期刊与会议出版物的 DOI 元数据。", "https://www.crossref.org/documentation/retrieve-metadata/rest-api/"),
    ("arxiv", "计算机、数学、物理等领域预印本。", "https://info.arxiv.org/help/api/index.html"),
    ("pubmed", "医学、生命科学与健康研究；支持联系邮箱和可选密钥。", "https://www.ncbi.nlm.nih.gov/books/NBK25501/"),
    ("doaj", "跨学科开放获取期刊文章。", "https://doaj.org/api/docs"),
    ("datacite", "机构仓储、学位论文和文字类学术成果。", "https://support.datacite.org/docs/api"),
    ("hal", "跨学科机构仓储、会议论文和学位论文。", "https://api.archives-ouvertes.fr/docs/search"),
    ("europe_pmc", "生命科学与医学文献，含预印本及开放全文链接。", "https://europepmc.org/RestfulWebService"),
):
    SOURCE_METADATA[_name].update(description=_description, docs_url=_docs, access_mode="官方开放接口")
for _name in ("semantic_scholar", "openalex", "pubmed"):
    SOURCE_METADATA[_name].update(credential_field=f"{_name}_api_key", credential_label="API Key（可选）")
SUPPORTED_SOURCES = tuple(SOURCE_METADATA)
DEFAULT_SOURCES = [name for name, metadata in SOURCE_METADATA.items() if metadata["live"] and metadata.get("added_by_default", True)]


def source_configuration(settings: Any, name: str) -> dict:
    metadata = SOURCE_METADATA[name]
    saved = getattr(settings, "source_configs", {}).get(name, {})
    added = saved.get("added", metadata.get("added_by_default", True))
    credential = getattr(settings, metadata.get("credential_field", ""), "")
    configured = not metadata["requires_credentials"] or bool(credential)
    enabled = added and saved.get("enabled", metadata.get("added_by_default", True))
    return {
        "added": added, "enabled": enabled, "configured": configured,
        "credential_configured": bool(credential), "selectable": bool(added and enabled and configured),
        "default_enabled": bool(enabled and configured and saved.get("default_enabled", metadata.get("added_by_default", True))),
        "daily_request_budget": saved.get("daily_request_budget") or settings.source_daily_request_budget,
        "budget_override": saved.get("daily_request_budget"),
        "last_test": saved.get("last_test"),
    }


def source_catalogue(settings: Any) -> list[dict]:
    return [{"id": name, **metadata, **source_configuration(settings, name),
        **({"contact_email": settings.pubmed_email} if name == "pubmed" else {})}
        for name, metadata in SOURCE_METADATA.items() if metadata["live"]]


def default_source_ids(settings: Any) -> list[str]:
    return [item["id"] for item in source_catalogue(settings) if item["selectable"] and item["default_enabled"]]


def source_error(exc: Exception, *secrets: str) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        detail = {401: "密钥无效或缺少认证", 403: "没有访问权限或服务拒绝请求", 402: "服务额度不足", 429: "请求过于频繁"}.get(code, "来源请求失败")
        message = f"HTTP {code}: {detail}"
    else:
        message = f"{type(exc).__name__}: {exc}"
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]").replace(quote(secret, safe=""), "[redacted]")
    return message


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _date(value: str | None) -> str:
    return _text(value)[:10]


def _normalize_doi(value: str | None) -> str:
    return _text(value).removeprefix("https://doi.org/").removeprefix("http://doi.org/").lower()


def _authors(raw: list[dict[str, Any]] | None) -> list[str]:
    result = []
    for item in raw or []:
        author = item.get("author", item)
        name = author.get("display_name") or author.get("name")
        if name:
            result.append(_text(name))
    return result


def _date_status(value: str, date_from: str, date_to: str) -> tuple[bool, bool]:
    if not value:
        return True, bool(date_from or date_to)
    try:
        earliest = latest = date.fromisoformat(value[:10])
    except ValueError:
        # Some repositories report only a year or month. Keep that precision and
        # exclude records only when the entire possible interval is out of range.
        try:
            if re.fullmatch(r"\d{4}", value):
                earliest, latest = date(int(value), 1, 1), date(int(value), 12, 31)
            elif re.fullmatch(r"\d{4}-\d{2}", value):
                year, month = map(int, value.split("-"))
                earliest, latest = date(year, month, 1), date(year, month, monthrange(year, month)[1])
            else:
                return True, bool(date_from or date_to)
        except ValueError:
            return True, bool(date_from or date_to)
    if date_from and latest < date.fromisoformat(date_from[:10]):
        return False, False
    if date_to and earliest > date.fromisoformat(date_to[:10]):
        return False, False
    return True, len(value) < 10 and bool(date_from or date_to)


def _with_date_status(record: dict, date_from: str, date_to: str) -> dict | None:
    included, unknown = _date_status(record.get("published_date", ""), date_from, date_to)
    if not included:
        return None
    if unknown:
        record["date_unknown"] = True
    return record


class SourceAdapter(Protocol):
    name: str

    def search(self, queries: tuple[str, ...], limit: int, date_from: str, date_to: str) -> list[dict]: ...

    def estimated_requests(self, queries: tuple[str, ...], limit: int) -> int: ...


class RetrievalStore(Protocol):
    def get_source_cache(self, cache_key: str) -> list[dict] | None: ...
    def save_source_cache(self, cache_key: str, provider: str, payload: list[dict], ttl_hours: int) -> None: ...
    def reserve_source_requests(self, provider: str, count: int, budget: int) -> bool: ...


class SourceRateLimited(RuntimeError):
    def __init__(self, retry_after: float):
        self.retry_after = max(0.0, retry_after)
        super().__init__(f"HTTP 429: source is rate limited; retry in {math.ceil(self.retry_after)} seconds")


class _RequestGate:
    def __init__(self):
        self.lock = Lock()
        self.next_request_at = 0.0
        self.cooldown_until = 0.0


_REQUEST_GATES: dict[tuple[str, str], _RequestGate] = {}
_REQUEST_GATES_LOCK = Lock()


def _retry_after_seconds(value: str, fallback: float) -> float:
    try:
        seconds = float(value)
        if math.isfinite(seconds):
            return max(0.0, seconds)
    except ValueError:
        try:
            moment = parsedate_to_datetime(value)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return max(0.0, (moment - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            pass
    return fallback


class BaseSource:
    name = "source"
    uses_request_gate = True
    minimum_request_interval = 1.1
    maximum_attempts = 4
    maximum_inline_wait = 15.0

    def __init__(self, client: httpx.Client, api_key: str = "", email: str = "") -> None:
        self.client = client
        self.api_key = api_key
        self.email = email
        self.attempts = 0
        self.retry_count = 0
        self.final_http_status = 0
        self.transport = "httpx"
        self.errors: list[str] = []
        self.cache: RetrievalStore | None = None
        self.cache_ttl_hours = 24
        self.daily_request_budget = 200
        self.requests_reserved = 0
        self.query_cache_hits = 0
        self.rate_limited = False
        self.retry_after_seconds = 0.0

    def estimated_requests(self, queries: tuple[str, ...], limit: int) -> int:
        return len(queries)

    def _get(self, url: str, **kwargs) -> httpx.Response:
        identity = (self.name, hashlib.sha256(self.api_key.encode()).hexdigest())
        with _REQUEST_GATES_LOCK:
            gate = _REQUEST_GATES.setdefault(identity, _RequestGate())
        with gate.lock:
            for attempt in range(self.maximum_attempts):
                wait = max(gate.next_request_at, gate.cooldown_until) - time.monotonic()
                if wait > self.maximum_inline_wait:
                    self.rate_limited = True
                    self.final_http_status = 429
                    self.retry_after_seconds = max(0.0, gate.cooldown_until - time.monotonic())
                    raise SourceRateLimited(self.retry_after_seconds)
                if wait > 0:
                    time.sleep(wait)
                if self.cache:
                    if not self.cache.reserve_source_requests(self.name, 1, self.daily_request_budget):
                        raise RuntimeError(f"Daily request budget exhausted ({self.daily_request_budget} requests)")
                    self.requests_reserved += 1
                self.retry_count += int(attempt > 0)
                self.attempts += 1
                gate.next_request_at = time.monotonic() + self.minimum_request_interval
                response = self.client.get(url, **kwargs)
                self.final_http_status = response.status_code
                if response.status_code != 429:
                    gate.cooldown_until = 0.0
                    self.rate_limited = False
                    response.raise_for_status()
                    return response
                delay = _retry_after_seconds(response.headers.get("Retry-After", ""), float(2 ** (attempt + 1)))
                delay = max(self.minimum_request_interval, delay)
                gate.cooldown_until = time.monotonic() + delay
                if attempt + 1 == self.maximum_attempts or delay > self.maximum_inline_wait:
                    gate.cooldown_until = time.monotonic() + max(60.0, delay)
                    self.rate_limited = True
                    self.retry_after_seconds = max(0.0, gate.cooldown_until - time.monotonic())
                    raise SourceRateLimited(self.retry_after_seconds)
        raise AssertionError("Source request attempts exhausted")

    def _iter_query(self, query: str, limit: int, date_from: str, date_to: str) -> Iterator[dict]:
        raise NotImplementedError

    def search(self, queries: tuple[str, ...], limit: int, date_from: str, date_to: str) -> list[dict]:
        records: list[dict] = []
        for query in queries:
            cache_key = hashlib.sha256(json.dumps({"kind": "source_query.v2", "provider": self.name,
                "credential": hashlib.sha256(self.api_key.encode()).hexdigest(),
                "query": query, "limit": limit, "date_from": date_from, "date_to": date_to},
                sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if self.cache:
                cached = self.cache.get_source_cache(cache_key)
                if cached is not None:
                    self.query_cache_hits += 1
                    records.extend(cached)
                    continue
            start = len(records)
            try:
                # extend retains yielded pages if a later page raises.
                records.extend(self._iter_query(query, limit, date_from, date_to))
            except SourceRateLimited as exc:
                self.errors.append(str(exc))
                break
            except Exception as exc:
                self.errors.append(source_error(exc, self.api_key))
                if not records:
                    raise
                break
            if self.cache:
                self.cache.save_source_cache(cache_key, self.name, records[start:], self.cache_ttl_hours)
        return records


class SemanticScholarSource(BaseSource):
    name = "semantic_scholar"
    fields = "paperId,title,abstract,authors,year,publicationDate,citationCount,externalIds,url,openAccessPdf,venue,journal,fieldsOfStudy,publicationTypes"
    minimum_request_interval = 1.1
    maximum_attempts = 4

    def estimated_requests(self, queries: tuple[str, ...], limit: int) -> int:
        return len(queries) * max(1, math.ceil(limit / 100))

    def __init__(self, client: httpx.Client, api_key: str = "", email: str = "") -> None:
        super().__init__(client, api_key, email)
        if not api_key:
            self.minimum_request_interval = 3.1

    def _iter_query(self, query: str, limit: int, date_from: str, date_to: str) -> Iterator[dict]:
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        offset, remaining = 0, limit
        while remaining > 0:
            page_size = min(100, remaining)
            response = self._get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": query, "offset": offset, "limit": page_size, "fields": self.fields},
                headers=headers,
            )
            payload = response.json()
            items = payload.get("data", [])
            for item in items:
                ids = item.get("externalIds") or {}
                paper_id = _text(item.get("paperId"))
                oa = item.get("openAccessPdf") or {}
                record = {
                    "title": _text(item.get("title")),
                    "authors": [_text(a.get("name")) for a in item.get("authors", []) if a.get("name")],
                    "author_ids": [_text(a.get("authorId")) for a in item.get("authors", []) if a.get("authorId")],
                    "abstract": _text(item.get("abstract")),
                    "published_date": _date(item.get("publicationDate") or (f"{item['year']}-01-01" if item.get("year") else "")),
                    "source": self.name, "source_id": paper_id, "semantic_scholar_id": paper_id,
                    "external_ids": ids,
                    "doi": _normalize_doi(ids.get("DOI")), "venue": _text((item.get("journal") or {}).get("name") or item.get("venue")),
                    "issns": [(item.get("journal") or {}).get("issn")] if (item.get("journal") or {}).get("issn") else [],
                    "official_url": item.get("url") or (f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""),
                    "open_access_url": oa.get("url", "") or "", "citation_count": item.get("citationCount"),
                    "language": "unknown", "topics": item.get("fieldsOfStudy") or [],
                    "publication_types": item.get("publicationTypes") or [],
                }
                filtered = _with_date_status(record, date_from, date_to)
                if filtered:
                    yield filtered
            if len(items) < page_size or payload.get("next") is None:
                break
            offset = int(payload["next"])
            remaining -= len(items)


class OpenAlexSource(BaseSource):
    name = "openalex"
    uses_request_gate = False

    def search(self, queries: tuple[str, ...], limit: int, date_from: str, date_to: str) -> list[dict]:
        records = []
        for query in queries:
            params: dict[str, Any] = {"search": query, "per-page": min(limit, 100), "sort": "relevance_score:desc"}
            if self.api_key:
                params["api_key"] = self.api_key
            response = self.client.get("https://api.openalex.org/works", params=params)
            response.raise_for_status()
            for item in response.json().get("results", []):
                primary = item.get("primary_location") or {}
                venue = primary.get("source") or {}
                doi = _normalize_doi(item.get("doi"))
                record = {
                    "title": _text(item.get("title")),
                    "authors": _authors(item.get("authorships")),
                    "abstract": _abstract_from_inverted_index(item.get("abstract_inverted_index")),
                    "published_date": _date(item.get("publication_date")),
                    "source": self.name,
                    "source_id": str(item.get("id", "")).rsplit("/", 1)[-1],
                    "doi": doi,
                    "pmid": str((item.get("ids") or {}).get("pmid") or "").rstrip("/").rsplit("/", 1)[-1],
                    "venue": _text(venue.get("display_name")),
                    "issns": list(dict.fromkeys([*(venue.get("issn") or []), *([venue["issn_l"]] if venue.get("issn_l") else [])])),
                    "venue_type": _text(venue.get("type")),
                    "official_url": item.get("doi") or item.get("id", ""),
                    "open_access_url": (item.get("open_access") or {}).get("oa_url", "") or "",
                    "citation_count": item.get("cited_by_count"),
                    "language": item.get("language") or "unknown",
                }
                filtered = _with_date_status(record, date_from, date_to)
                if filtered:
                    records.append(filtered)
        return records


def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        words.extend((position, word) for position in positions)
    return _text(" ".join(word for _, word in sorted(words)))


class CrossrefSource(BaseSource):
    name = "crossref"

    def _iter_query(self, query: str, limit: int, date_from: str, date_to: str) -> Iterator[dict]:
        params = {"query": query, "rows": min(limit, 100), "select": "DOI,title,author,published,container-title,URL,abstract,ISSN,type"}
        user_agent = "LiteratureAgent/0.3"
        if self.email:
            params["mailto"] = self.email
            user_agent += f" (mailto:{self.email})"
        response = self._get("https://api.crossref.org/works", params=params, headers={"User-Agent": user_agent})
        for item in response.json().get("message", {}).get("items", []):
            title = (item.get("title") or [""])[0]
            date_parts = (item.get("published", {}).get("date-parts") or [[""]])[0]
            published_date = "-".join(str(part).zfill(2) for part in date_parts)
            abstract = re.sub(r"<[^>]+>", " ", html.unescape(item.get("abstract", "")))
            doi = _normalize_doi(item.get("DOI"))
            record = {
                "title": _text(title),
                "authors": [_text(f"{item.get('given', '')} {item.get('family', '')}") for item in item.get("author", []) if item.get("family")],
                "abstract": _text(abstract),
                "published_date": published_date,
                "source": self.name,
                "source_id": doi,
                "doi": doi,
                "venue": _text((item.get("container-title") or [""])[0]),
                "issns": item.get("ISSN") or [],
                "venue_type": _text(item.get("type")),
                "official_url": item.get("URL", "") or (f"https://doi.org/{doi}" if doi else ""),
                "open_access_url": "",
                "language": "unknown",
            }
            filtered = _with_date_status(record, date_from, date_to)
            if filtered:
                yield filtered


class ArxivSource(BaseSource):
    name = "arxiv"
    uses_request_gate = False
    namespace = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

    @staticmethod
    def _search_expression(query: str) -> str:
        terms = list(dict.fromkeys(re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*", query)))
        return " AND ".join(f'all:"{term}"' for term in terms[:8])

    def _system_curl(self, url: str, user_agent: str) -> str:
        executable = shutil.which("curl.exe") or shutil.which("curl")
        if not executable:
            raise RuntimeError("arXiv request failed and system curl is unavailable")
        result = subprocess.run(
            [
                executable,
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--max-time",
                "30",
                "--header",
                "Accept: application/atom+xml",
                "--user-agent",
                user_agent,
                url,
            ],
            capture_output=True,
            check=False,
            timeout=35,
        )
        self.attempts += 1
        if result.returncode != 0:
            error = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"arXiv system curl failed ({result.returncode}): {error}")
        self.final_http_status = 200
        self.transport = "system_curl"
        return result.stdout.decode("utf-8")

    def search(self, queries: tuple[str, ...], limit: int, date_from: str, date_to: str) -> list[dict]:
        records = []
        last_error: Exception | None = None
        for query in queries:
            expression = self._search_expression(query)
            if not expression:
                self.errors.append("Skipped arXiv query without supported English keywords; no generic query was substituted")
                continue
            params = {
                "search_query": expression,
                "start": 0,
                "max_results": min(limit, 100),
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
            query_string = urlencode(params, quote_via=quote)
            user_agent = "LiteratureAgent/0.3"
            if self.email:
                user_agent += f" (mailto:{self.email})"
            url = f"https://export.arxiv.org/api/query?{query_string}"
            try:
                try:
                    response = self.client.get(
                        url,
                        headers={"Accept": "application/atom+xml", "User-Agent": user_agent},
                    )
                    self.attempts += 1
                    self.final_http_status = response.status_code
                    if response.status_code == 406:
                        feed_text = self._system_curl(url, user_agent)
                    else:
                        response.raise_for_status()
                        feed_text = response.text
                except httpx.TransportError:
                    feed_text = self._system_curl(url, user_agent)
                root = ElementTree.fromstring(feed_text)
            except Exception as exc:
                last_error = exc
                self.errors.append(f"{type(exc).__name__}: {exc}")
                continue
            for entry in root.findall("atom:entry", self.namespace):
                entry_id = entry.findtext("atom:id", "", self.namespace)
                arxiv_id = entry_id.rsplit("/", 1)[-1]
                published = _date(entry.findtext("atom:published", "", self.namespace))
                record = {
                    "title": _text(entry.findtext("atom:title", "", self.namespace)),
                    "authors": [_text(author.findtext("atom:name", "", self.namespace)) for author in entry.findall("atom:author", self.namespace)],
                    "abstract": _text(entry.findtext("atom:summary", "", self.namespace)),
                    "published_date": published,
                    "source": self.name,
                    "source_id": arxiv_id,
                    "arxiv_id": arxiv_id,
                    "doi": "",
                    "venue": "arXiv",
                    "official_url": entry_id,
                    "open_access_url": entry_id.replace("http://", "https://").replace("abs/", "pdf/") + ".pdf",
                    "language": "en",
                    "topics": [category.attrib.get("term", "") for category in entry.findall("arxiv:primary_category", self.namespace)],
                }
                filtered = _with_date_status(record, date_from, date_to)
                if filtered:
                    records.append(filtered)
        if not records and last_error is not None:
            raise last_error
        return records


class PubMedSource(BaseSource):
    name = "pubmed"
    uses_request_gate = False

    def estimated_requests(self, queries: tuple[str, ...], limit: int) -> int:
        return len(queries) * 2

    def search(self, queries: tuple[str, ...], limit: int, date_from: str, date_to: str) -> list[dict]:
        records = []
        for query in queries:
            params: dict[str, Any] = {"db": "pubmed", "term": query, "retmax": min(limit, 100), "retmode": "json"}
            if self.api_key:
                params["api_key"] = self.api_key
            if self.email:
                params["email"] = self.email
            response = self.client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=params)
            response.raise_for_status()
            ids = response.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                continue
            fetch_params: dict[str, Any] = {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
            if self.api_key:
                fetch_params["api_key"] = self.api_key
            if self.email:
                fetch_params["email"] = self.email
            fetched = self.client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params=fetch_params)
            fetched.raise_for_status()
            root = ElementTree.fromstring(fetched.text)
            for article in root.findall(".//PubmedArticle"):
                pmid = _text(article.findtext(".//PMID"))
                citation = article.find(".//Article")
                if citation is None:
                    continue
                published_date = _pubmed_date(article)
                doi = ""
                for article_id in article.findall(".//ArticleId"):
                    if article_id.attrib.get("IdType") == "doi":
                        doi = _normalize_doi(article_id.text)
                        break
                record = {
                    "title": _text(citation.findtext(".//ArticleTitle")),
                    "authors": [_pubmed_author(author) for author in citation.findall(".//Author") if _pubmed_author(author)],
                    "abstract": _pubmed_abstract(citation),
                    "published_date": published_date,
                    "source": self.name,
                    "source_id": pmid,
                    "pmid": pmid,
                    "doi": doi,
                    "venue": _text(citation.findtext(".//Journal/Title")),
                    "issns": list(dict.fromkeys(filter(None, [citation.findtext(".//Journal/ISSN"), article.findtext(".//MedlineJournalInfo/ISSNLinking")]))),
                    "venue_type": "journal",
                    "official_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                    "open_access_url": "",
                    "language": _text(citation.findtext(".//Language")) or "unknown",
                }
                filtered = _with_date_status(record, date_from, date_to)
                if filtered:
                    records.append(filtered)
        return records


def _pubmed_author(author: ElementTree.Element) -> str:
    collective = _text(author.findtext("CollectiveName"))
    if collective:
        return collective
    given = _text(author.findtext("ForeName"))
    family = _text(author.findtext("LastName"))
    return _text(f"{given} {family}")


def _pubmed_abstract(article: ElementTree.Element) -> str:
    parts = []
    for item in article.findall(".//Abstract/AbstractText"):
        label = _text(item.attrib.get("Label"))
        value = _text("".join(item.itertext()))
        parts.append(f"{label}: {value}" if label else value)
    return _text(" ".join(parts))


def _pubmed_date(article: ElementTree.Element) -> str:
    article_date = article.find(".//ArticleDate")
    if article_date is not None:
        year = _text(article_date.findtext("Year"))
        month = _text(article_date.findtext("Month"))
        day = _text(article_date.findtext("Day"))
        if year:
            return "-".join(part.zfill(2) for part in (year, month or "01", day or "01"))
    pub_date = article.find(".//JournalIssue/PubDate")
    if pub_date is not None:
        year = _text(pub_date.findtext("Year"))
        if year:
            month = _text(pub_date.findtext("Month"))
            day = _text(pub_date.findtext("Day"))
            if not month:
                month = "01"
            if not month.isdigit():
                month = str({"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}.get(month[:3], 1))
            return "-".join(part.zfill(2) for part in (year, month, day or "01"))
    return ""


def _markup_text(value: Any) -> str:
    return _text(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))))


def _first(value: Any) -> str:
    return _text(next(iter(value), "") if isinstance(value, list) else value)


class DOAJSource(BaseSource):
    name = "doaj"

    def _iter_query(self, query: str, limit: int, date_from: str, date_to: str) -> Iterator[dict]:
        expression = query
        if date_from or date_to:
            expression = f"({query}) AND bibjson.year:[{date_from[:4] or '*'} TO {date_to[:4] or '*'}]"
        response = self._get(
            f"https://doaj.org/api/search/articles/{quote(expression, safe='')}",
            params={"pageSize": min(limit, 100), "page": 1},
        )
        for item in response.json().get("results", [])[:limit]:
            bib = item.get("bibjson") or {}
            journal = bib.get("journal") or {}
            identifiers = bib.get("identifier") or []
            doi = next((_normalize_doi(i.get("id")) for i in identifiers if i.get("type") == "doi"), "")
            fulltext = next((_text(link.get("url")) for link in bib.get("link", []) if link.get("type") == "fulltext"), "")
            published = _text(bib.get("year"))
            month = _text(bib.get("month"))
            if published and month:
                if not month.isdigit():
                    month = str({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}.get(month[:3].lower(), ""))
                if month:
                    published += f"-{int(month):02d}"
            source_id = _text(item.get("id"))
            record = {
                "title": _markup_text(bib.get("title")), "authors": _authors(bib.get("author")),
                "abstract": _markup_text(bib.get("abstract")), "published_date": published,
                "source": self.name, "source_id": source_id, "doi": doi,
                "venue": _text(journal.get("title")), "venue_type": "journal",
                "issns": list(dict.fromkeys([*(journal.get("issns") or []),
                    *[i["id"] for i in identifiers if i.get("type") in {"pissn", "eissn"} and i.get("id")]])),
                "official_url": f"https://doi.org/{doi}" if doi else fulltext or f"https://doaj.org/article/{source_id}",
                "open_access_url": fulltext, "language": _first(journal.get("language")).lower() or "unknown",
                "topics": bib.get("keywords") or [],
            }
            if filtered := _with_date_status(record, date_from, date_to):
                yield filtered


class DataCiteSource(BaseSource):
    name = "datacite"
    literature_types = ("Text", "Preprint", "JournalArticle", "ConferencePaper", "Dissertation", "Book", "BookChapter", "Report")

    def _iter_query(self, query: str, limit: int, date_from: str, date_to: str) -> Iterator[dict]:
        expression = f"({query}) AND types.resourceTypeGeneral:({' OR '.join(self.literature_types)})"
        if date_from or date_to:
            expression += f" AND publicationYear:[{date_from[:4] or '*'} TO {date_to[:4] or '*'}]"
        response = self._get("https://api.datacite.org/dois", params={"query": expression, "page[size]": min(limit, 100)})
        for item in response.json().get("data", [])[:limit]:
            data = item.get("attributes") or {}
            types = data.get("types") or {}
            if types.get("resourceTypeGeneral") not in self.literature_types:
                continue
            doi = _normalize_doi(data.get("doi") or item.get("id"))
            published = next((_date(d.get("date")) for d in data.get("dates", [])
                if d.get("dateType") == "Issued" and re.fullmatch(r"\d{4}(?:-\d{2})?(?:-\d{2})?", _text(d.get("date")))), "")
            published = published or _text(data.get("publicationYear"))
            official_url = _text(data.get("url")) or (f"https://doi.org/{doi}" if doi else "")
            rights = " ".join(str(r.get("rightsUri") or "") + " " + str(r.get("rights") or "") for r in data.get("rightsList", [])).lower()
            container = data.get("container") or {}
            record = {
                "title": _markup_text(next((t.get("title") for t in data.get("titles", []) if not t.get("titleType")), "")
                    or next((t.get("title") for t in data.get("titles", [])), "")),
                "authors": _authors(data.get("creators")),
                "abstract": _markup_text(" ".join(d.get("description") or "" for d in data.get("descriptions", []) if d.get("descriptionType") == "Abstract")),
                "published_date": published, "source": self.name, "source_id": doi, "doi": doi,
                "venue": _text(container.get("title")), "venue_type": _text(types.get("resourceTypeGeneral")),
                "issns": [_text(container.get("identifier"))] if container.get("identifierType") == "ISSN" else [],
                "official_url": official_url,
                "open_access_url": official_url if "creativecommons.org/" in rights or "info:eu-repo/semantics/openaccess" in rights else "",
                "language": _text(data.get("language")) or "unknown",
                "topics": [s["subject"] for s in data.get("subjects", []) if s.get("subject")],
                "publication_types": [types.get("resourceType") or types["resourceTypeGeneral"]],
            }
            if filtered := _with_date_status(record, date_from, date_to):
                yield filtered


class HALSource(BaseSource):
    name = "hal"
    fields = "halId_s,title_s,authFullName_s,abstract_s,producedDate_s,doiId_s,uri_s,fileMain_s,journalTitle_s,journalIssn_s,journalEissn_s,language_s,docType_s,arxivId_s,pubmedId_s"

    def _iter_query(self, query: str, limit: int, date_from: str, date_to: str) -> Iterator[dict]:
        filters = ["docType_s:(ART OR COMM OR PREPRINT OR THESE OR HDR OR REPORT OR OUV OR COUV)"]
        if date_from or date_to:
            # Year-wide server bounds retain records whose month/day is unknown.
            filters.append(f"producedDate_tdate:[{date_from[:4] + '-01-01T00:00:00Z' if date_from else '*'} TO {date_to[:4] + '-12-31T23:59:59Z' if date_to else '*'}]")
        response = self._get("https://api.archives-ouvertes.fr/search/", params={
            "q": query, "rows": min(limit, 100), "wt": "json", "fl": self.fields, "fq": filters,
        })
        for item in response.json().get("response", {}).get("docs", [])[:limit]:
            source_id = _first(item.get("halId_s"))
            record = {
                "title": _markup_text(_first(item.get("title_s"))), "authors": item.get("authFullName_s") or [],
                "abstract": _markup_text(_first(item.get("abstract_s"))), "published_date": _date(_first(item.get("producedDate_s"))),
                "source": self.name, "source_id": source_id, "doi": _normalize_doi(_first(item.get("doiId_s"))),
                "pmid": _first(item.get("pubmedId_s")), "arxiv_id": _first(item.get("arxivId_s")),
                "venue": _first(item.get("journalTitle_s")), "publication_types": [_first(item.get("docType_s"))],
                "issns": [value for field in ("journalIssn_s", "journalEissn_s") if (value := _first(item.get(field)))],
                "official_url": _first(item.get("uri_s")) or f"https://hal.science/{source_id}",
                "open_access_url": _first(item.get("fileMain_s")), "language": _first(item.get("language_s")) or "unknown",
            }
            if filtered := _with_date_status(record, date_from, date_to):
                yield filtered


class EuropePMCSource(BaseSource):
    name = "europe_pmc"

    def _iter_query(self, query: str, limit: int, date_from: str, date_to: str) -> Iterator[dict]:
        expression = query
        if date_from or date_to:
            expression = f"({query}) AND FIRST_PDATE:[{date_from or '*'} TO {date_to or '*'}]"
        response = self._get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params={
            "query": expression, "format": "json", "resultType": "core", "pageSize": min(limit, 100),
        })
        for item in response.json().get("resultList", {}).get("result", [])[:limit]:
            origin, source_id = _text(item.get("source")), _text(item.get("id"))
            doi = _normalize_doi(item.get("doi"))
            journal = (item.get("journalInfo") or {}).get("journal") or {}
            fulltext = next((_text(link.get("url")) for link in (item.get("fullTextUrlList") or {}).get("fullTextUrl", [])
                if link.get("availabilityCode") == "OA" or link.get("availability") == "Open access"), "")
            authors = [_text(a.get("fullName")) for a in (item.get("authorList") or {}).get("author", []) if a.get("fullName")]
            record = {
                "title": _markup_text(item.get("title")), "authors": authors or [_text(a) for a in _text(item.get("authorString")).split(",") if a.strip()],
                "abstract": _markup_text(item.get("abstractText")),
                "published_date": _date(item.get("firstPublicationDate") or item.get("pubYear")),
                "source": self.name, "source_id": f"{origin}:{source_id}",
                "pmid": _text(item.get("pmid") or (source_id if origin == "MED" else "")), "doi": doi,
                "venue": _text(journal.get("title")), "issns": [journal[k] for k in ("issn", "essn") if journal.get(k)],
                "official_url": f"https://europepmc.org/article/{quote(origin, safe='')}/{quote(source_id, safe='')}",
                "open_access_url": fulltext, "citation_count": item.get("citedByCount"),
                "language": _text(item.get("language")) or "unknown",
                "publication_types": (item.get("pubTypeList") or {}).get("pubType") or [],
            }
            if filtered := _with_date_status(record, date_from, date_to):
                yield filtered


class GoogleScholarSource(BaseSource):
    name = "google_scholar"

    def estimated_requests(self, queries: tuple[str, ...], limit: int) -> int:
        return len(queries) * max(1, math.ceil(min(limit, 100) / 20))

    def _iter_query(self, query: str, limit: int, date_from: str, date_to: str) -> Iterator[dict]:
        if not self.api_key:
            raise ValueError("请先配置 SerpApi API Key")
        offset, remaining = 0, min(limit, 100)
        while remaining > 0:
            count = min(20, remaining)
            params = {"engine": "google_scholar", "api_key": self.api_key, "q": query, "num": count, "start": offset}
            if date_from:
                params["as_ylo"] = date_from[:4]
            if date_to:
                params["as_yhi"] = date_to[:4]
            data = self._get("https://serpapi.com/search.json", params=params).json()
            if data.get("error"):
                raise RuntimeError(_text(data["error"]).replace(self.api_key, "[redacted]"))
            items = data.get("organic_results") or []
            for item in items[:remaining]:
                info = item.get("publication_info") or {}
                year = re.search(r"\b(?:18|19|20)\d{2}\b", _text(info.get("summary")))
                link = _text(item.get("link"))
                doi_match = re.search(r"https?://(?:dx\.)?doi\.org/(10\.[^?#\s]+)", link, re.I)
                record = {
                    "source": self.name, "source_id": _text(item.get("result_id")),
                    "title": _markup_text(item.get("title")), "authors": _authors(info.get("authors")),
                    # A search snippet is not an author-written abstract.
                    "abstract": "", "search_snippet": _markup_text(item.get("snippet")),
                    "published_date": year.group() if year else "", "doi": _normalize_doi(doi_match.group(1)) if doi_match else "",
                    "official_url": link, "open_access_url": "", "language": "unknown",
                    "citation_count": ((item.get("inline_links") or {}).get("cited_by") or {}).get("total"),
                }
                if filtered := _with_date_status(record, date_from, date_to):
                    yield filtered
            if len(items) < count or not (data.get("serpapi_pagination") or {}).get("next"):
                break
            offset += len(items)
            remaining -= len(items)


class CORESource(BaseSource):
    name = "core"

    def _iter_query(self, query: str, limit: int, date_from: str, date_to: str) -> Iterator[dict]:
        if not self.api_key:
            raise ValueError("请先配置 CORE API Key")
        expression = query
        if date_from or date_to:
            expression = f"({query}) AND yearPublished:[{date_from[:4] or '*'} TO {date_to[:4] or '*'}]"
        data = self._get("https://api.core.ac.uk/v3/search/works", params={"q": expression, "limit": min(limit, 100)},
            headers={"Authorization": f"Bearer {self.api_key}"}).json()
        for item in (data.get("results") or [])[:limit]:
            source_id = _text(item.get("id"))
            doi = _normalize_doi(item.get("doi"))
            record = {
                "source": self.name, "source_id": source_id, "doi": doi,
                "title": _markup_text(item.get("title")), "authors": _authors(item.get("authors")),
                "abstract": _markup_text(item.get("abstract")),
                "published_date": _date(item.get("publishedDate") or item.get("yearPublished")),
                "official_url": f"https://doi.org/{doi}" if doi else f"https://core.ac.uk/works/{source_id}",
                "open_access_url": _text(item.get("downloadUrl")),
                "language": _text((item.get("language") or {}).get("code")) if isinstance(item.get("language"), dict) else _text(item.get("language")) or "unknown",
            }
            if filtered := _with_date_status(record, date_from, date_to):
                yield filtered


def build_sources(client: httpx.Client, settings: Any) -> dict[str, SourceAdapter]:
    return {
        "semantic_scholar": SemanticScholarSource(client, settings.semantic_scholar_api_key),
        "openalex": OpenAlexSource(client, settings.openalex_api_key),
        "crossref": CrossrefSource(client, email=settings.pubmed_email or settings.smtp_from),
        "arxiv": ArxivSource(client, email=settings.pubmed_email or settings.smtp_from),
        "pubmed": PubMedSource(client, settings.pubmed_api_key, settings.pubmed_email),
        "doaj": DOAJSource(client),
        "datacite": DataCiteSource(client),
        "hal": HALSource(client),
        "europe_pmc": EuropePMCSource(client),
        "google_scholar": GoogleScholarSource(client, settings.serpapi_api_key),
        "core": CORESource(client, settings.core_api_key),
    }


def search_sources(
    source_names: list[str],
    queries: tuple[str, ...],
    limit: int,
    date_from: str,
    date_to: str,
    client: httpx.Client,
    settings: Any,
    cache: RetrievalStore | None = None,
) -> tuple[list[dict], dict[str, dict]]:
    adapters = build_sources(client, settings)
    requested = [name for name in dict.fromkeys(source_names) if name in adapters]
    # LLM planners can return many paraphrases; cap provider fan-out to keep free APIs below rate limits.
    queries = tuple(dict.fromkeys(query.strip() for query in queries if query.strip()))[:4]
    records: list[dict] = []
    diagnostics: dict[str, dict] = {}
    for name in requested[:]:
        config = source_configuration(settings, name)
        if not config["selectable"]:
            status = "not_configured" if config["enabled"] and not config["configured"] else "disabled"
            diagnostics[name] = {"status": status, "count": 0, "error": "来源未配置密钥" if status == "not_configured" else "来源已停用", "attempts": 0}
            requested.remove(name)
    def retrieve(name: str):
        adapter = adapters[name]
        config = source_configuration(settings, name)
        cache_key = hashlib.sha256(json.dumps({"provider": name, "queries": queries, "limit": limit,
            "credential": hashlib.sha256(adapter.api_key.encode()).hexdigest(),
            "date_from": date_from, "date_to": date_to}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if cache:
            cached = cache.get_source_cache(cache_key)
            if cached is not None:
                return cached, {"status": "cached", "count": len(cached), "error": "", "cache_hit": True, "requests_reserved": 0}
        request_count = adapter.estimated_requests(queries, limit)
        if adapter.uses_request_gate:
            adapter.cache = cache
            adapter.cache_ttl_hours = settings.source_cache_ttl_hours
            adapter.daily_request_budget = config["daily_request_budget"]
        elif cache:
            if not cache.reserve_source_requests(name, request_count, config["daily_request_budget"]):
                raise RuntimeError(f"Daily request budget exhausted ({config['daily_request_budget']} requests)")
            adapter.requests_reserved = request_count
        source_records = adapter.search(queries, limit, date_from, date_to)
        if cache and not adapter.errors:
            cache.save_source_cache(cache_key, name, source_records, settings.source_cache_ttl_hours)
        status = ("partial" if source_records else "rate_limited") if adapter.rate_limited else "partial" if adapter.errors else "ok"
        return source_records, {"status": status, "count": len(source_records), "error": "; ".join(adapter.errors), "cache_hit": False,
            "requests_reserved": adapter.requests_reserved, "attempts": adapter.attempts, "retry_count": adapter.retry_count,
            "final_http_status": adapter.final_http_status, "transport": adapter.transport,
            "rate_limited": adapter.rate_limited, "retry_after_seconds": math.ceil(adapter.retry_after_seconds),
            "query_cache_hits": adapter.query_cache_hits, "credentialed": bool(adapter.api_key)}

    with ThreadPoolExecutor(max_workers=max(1, len(requested))) as pool:
        futures = {pool.submit(retrieve, name): name for name in requested}
        for future in as_completed(futures):
            name = futures[future]
            try:
                source_records, diagnostic = future.result()
                records.extend(source_records)
                diagnostics[name] = diagnostic
            except Exception as exc:
                adapter = adapters[name]
                diagnostics[name] = {"status": "failed", "count": 0, "error": source_error(exc, adapter.api_key),
                    "cache_hit": False, "requests_reserved": adapter.requests_reserved, "attempts": adapter.attempts,
                    "retry_count": adapter.retry_count, "final_http_status": adapter.final_http_status,
                    "transport": adapter.transport}
    return records, diagnostics
