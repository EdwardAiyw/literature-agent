from __future__ import annotations

import html
import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Protocol
from xml.etree import ElementTree

import httpx

SUPPORTED_SOURCES = ("fixture", "semantic_scholar", "openalex", "crossref", "arxiv", "pubmed")
SOURCE_METADATA = {
    "fixture": {"label": "Fixture", "requires_credentials": False, "live": False},
    "semantic_scholar": {"label": "Semantic Scholar", "requires_credentials": False, "live": True},
    "openalex": {"label": "OpenAlex", "requires_credentials": False, "live": True},
    "crossref": {"label": "Crossref", "requires_credentials": False, "live": True},
    "arxiv": {"label": "arXiv", "requires_credentials": False, "live": True},
    "pubmed": {"label": "PubMed", "requires_credentials": False, "live": True},
}


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
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return True, bool(date_from or date_to)
    if date_from and parsed < date.fromisoformat(date_from[:10]):
        return False, False
    if date_to and parsed > date.fromisoformat(date_to[:10]):
        return False, False
    return True, False


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


class BaseSource:
    name = "source"

    def __init__(self, client: httpx.Client, api_key: str = "", email: str = "") -> None:
        self.client = client
        self.api_key = api_key
        self.email = email

    def estimated_requests(self, queries: tuple[str, ...], limit: int) -> int:
        return len(queries)


class SemanticScholarSource(BaseSource):
    name = "semantic_scholar"
    fields = "paperId,title,abstract,authors,year,publicationDate,citationCount,externalIds,url,openAccessPdf,venue,fieldsOfStudy,publicationTypes"

    def estimated_requests(self, queries: tuple[str, ...], limit: int) -> int:
        return len(queries) * max(1, math.ceil(limit / 100))

    def search(self, queries: tuple[str, ...], limit: int, date_from: str, date_to: str) -> list[dict]:
        records = []
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        for query in queries:
            offset, remaining = 0, limit
            while remaining > 0:
                page_size = min(100, remaining)
                response = self.client.get("https://api.semanticscholar.org/graph/v1/paper/search",
                    params={"query": query, "offset": offset, "limit": page_size, "fields": self.fields}, headers=headers)
                response.raise_for_status()
                payload = response.json(); items = payload.get("data", [])
                for item in items:
                    ids = item.get("externalIds") or {}; paper_id = _text(item.get("paperId")); oa = item.get("openAccessPdf") or {}
                    record = {"title": _text(item.get("title")),
                        "authors": [_text(a.get("name")) for a in item.get("authors", []) if a.get("name")],
                        "author_ids": [_text(a.get("authorId")) for a in item.get("authors", []) if a.get("authorId")],
                        "abstract": _text(item.get("abstract")),
                        "published_date": _date(item.get("publicationDate") or (f"{item['year']}-01-01" if item.get("year") else "")),
                        "source": self.name, "source_id": paper_id, "semantic_scholar_id": paper_id,
                        "doi": _normalize_doi(ids.get("DOI")), "venue": _text(item.get("venue")),
                        "official_url": item.get("url") or (f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""),
                        "open_access_url": oa.get("url", "") or "", "citation_count": item.get("citationCount"),
                        "language": "unknown", "topics": item.get("fieldsOfStudy") or [],
                        "publication_types": item.get("publicationTypes") or []}
                    filtered = _with_date_status(record, date_from, date_to)
                    if filtered: records.append(filtered)
                if len(items) < page_size or payload.get("next") is None: break
                offset = int(payload["next"]); remaining -= len(items)
        return records


class OpenAlexSource(BaseSource):
    name = "openalex"

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
                    "venue": _text(venue.get("display_name")),
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

    def search(self, queries: tuple[str, ...], limit: int, date_from: str, date_to: str) -> list[dict]:
        records = []
        for query in queries:
            params = {"query": query, "rows": min(limit, 100), "select": "DOI,title,author,published,container-title,URL,abstract"}
            response = self.client.get("https://api.crossref.org/works", params=params)
            response.raise_for_status()
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
                    "official_url": item.get("URL", "") or (f"https://doi.org/{doi}" if doi else ""),
                    "open_access_url": "",
                    "language": "unknown",
                }
                filtered = _with_date_status(record, date_from, date_to)
                if filtered:
                    records.append(filtered)
        return records


class ArxivSource(BaseSource):
    name = "arxiv"
    namespace = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

    def search(self, queries: tuple[str, ...], limit: int, date_from: str, date_to: str) -> list[dict]:
        records = []
        for query in queries:
            response = self.client.get(
                "https://export.arxiv.org/api/query",
                params={"search_query": f"all:{query}", "start": 0, "max_results": min(limit, 100), "sortBy": "relevance", "sortOrder": "descending"},
                headers={"Accept": "application/atom+xml", "User-Agent": "LiteratureAgent/0.3 (academic literature retrieval)"},
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
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
        return records


class PubMedSource(BaseSource):
    name = "pubmed"

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


def build_sources(client: httpx.Client, settings: Any) -> dict[str, SourceAdapter]:
    return {
        "semantic_scholar": SemanticScholarSource(client, settings.semantic_scholar_api_key),
        "openalex": OpenAlexSource(client, settings.openalex_api_key),
        "crossref": CrossrefSource(client),
        "arxiv": ArxivSource(client),
        "pubmed": PubMedSource(client, settings.pubmed_api_key, settings.pubmed_email),
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
    def retrieve(name: str):
        cache_key = hashlib.sha256(json.dumps({"provider": name, "queries": queries, "limit": limit,
            "date_from": date_from, "date_to": date_to}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if cache:
            cached = cache.get_source_cache(cache_key)
            if cached is not None:
                return cached, {"status": "cached", "count": len(cached), "error": "", "cache_hit": True, "requests_reserved": 0}
        adapter = adapters[name]; request_count = adapter.estimated_requests(queries, limit)
        if cache and not cache.reserve_source_requests(name, request_count, settings.source_daily_request_budget):
            raise RuntimeError(f"Daily request budget exhausted ({settings.source_daily_request_budget} requests)")
        source_records = adapter.search(queries, limit, date_from, date_to)
        if cache: cache.save_source_cache(cache_key, name, source_records, settings.source_cache_ttl_hours)
        return source_records, {"status": "ok", "count": len(source_records), "error": "", "cache_hit": False, "requests_reserved": request_count}

    with ThreadPoolExecutor(max_workers=max(1, len(requested))) as pool:
        futures = {pool.submit(retrieve, name): name for name in requested}
        for future in as_completed(futures):
            name = futures[future]
            try:
                source_records, diagnostic = future.result()
                records.extend(source_records)
                diagnostics[name] = diagnostic
            except Exception as exc:
                diagnostics[name] = {"status": "failed", "count": 0, "error": f"{type(exc).__name__}: {exc}", "cache_hit": False, "requests_reserved": 0}
    return records, diagnostics
