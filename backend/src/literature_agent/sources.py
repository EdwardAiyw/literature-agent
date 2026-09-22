from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Protocol
from xml.etree import ElementTree

import httpx

SUPPORTED_SOURCES = ("fixture", "openalex", "crossref", "arxiv", "pubmed")
SOURCE_METADATA = {
    "fixture": {"label": "Fixture", "requires_credentials": False, "live": False},
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


class BaseSource:
    name = "source"

    def __init__(self, client: httpx.Client, api_key: str = "", email: str = "") -> None:
        self.client = client
        self.api_key = api_key
        self.email = email


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
) -> tuple[list[dict], dict[str, dict]]:
    adapters = build_sources(client, settings)
    requested = [name for name in dict.fromkeys(source_names) if name in adapters]
    # LLM planners can return many paraphrases; cap provider fan-out to keep free APIs below rate limits.
    queries = tuple(dict.fromkeys(query.strip() for query in queries if query.strip()))[:4]
    records: list[dict] = []
    diagnostics: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(requested))) as pool:
        futures = {pool.submit(adapters[name].search, queries, limit, date_from, date_to): name for name in requested}
        for future in as_completed(futures):
            name = futures[future]
            try:
                source_records = future.result()
                records.extend(source_records)
                diagnostics[name] = {"status": "ok", "count": len(source_records), "error": ""}
            except Exception as exc:
                diagnostics[name] = {"status": "failed", "count": 0, "error": f"{type(exc).__name__}: {exc}"}
    return records, diagnostics
