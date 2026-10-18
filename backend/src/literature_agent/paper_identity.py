"""Shared conservative identity matching for retrieval and delivered-paper history."""
from __future__ import annotations

import copy
import re
import unicodedata
from urllib.parse import unquote, urlparse


def compact(value: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", str(value)).casefold())


def member(paper: dict) -> dict:
    return {k: copy.deepcopy(paper[k]) for k in (
        "title", "authors", "doi", "pmid", "arxiv_id", "external_ids", "externalIds",
        "source", "source_id", "official_url",
    ) if paper.get(k)}


def members(paper: dict) -> list[dict]:
    return [member(paper), *(paper.get("identity_members") or [])]


def strong_ids(paper: dict) -> set[str]:
    result: set[str] = set()
    for p in members(paper):
        external = p.get("external_ids") or p.get("externalIds") or {}
        if not isinstance(external, dict):
            external = {}
        doi = unquote(str(p.get("doi") or external.get("DOI") or "")).strip().lower()
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi)
        if re.fullmatch(r"10\.\d{4,9}/[^\s<>]+", doi):
            result.add("doi:" + doi)
        source = p.get("source", "")
        url = urlparse(str(p.get("official_url") or ""))
        pmid = str(p.get("pmid") or external.get("PubMed") or (p.get("source_id") if source == "pubmed" else "") or "").strip()
        if not pmid and url.hostname == "pubmed.ncbi.nlm.nih.gov":
            pmid = url.path.strip("/")
        if re.fullmatch(r"[1-9]\d{0,8}", pmid):
            result.add("pmid:" + pmid)
        arxiv = str(p.get("arxiv_id") or external.get("ArXiv") or (p.get("source_id") if source == "arxiv" else "") or "").strip()
        if url.hostname in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            arxiv = re.sub(r"^/(?:abs|pdf)/", "", unquote(url.path)).removesuffix(".pdf")
        arxiv = re.sub(r"^arxiv:\s*", "", arxiv, flags=re.I)
        if re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-zA-Z][a-zA-Z.\-]+/\d{7})(?:v\d+)?", arxiv):
            result.add("arxiv:" + re.sub(r"v\d+$", "", arxiv).lower())
        if source and p.get("source_id") and source != "arxiv":
            result.add("source:" + source + ":" + str(p["source_id"]).strip().lower())
    return result


def title_key(paper: dict) -> str:
    title = str(paper.get("title") or "")
    key = compact(title)
    return key if len(key) >= 32 or len(re.findall(r"[\u3400-\u9fff]", title)) >= 16 else ""


def matches(left: dict, right: dict) -> bool:
    a, b = strong_ids(left), strong_ids(right)
    if a & b:
        return True
    # Conflicting reliable IDs are not bridged by a coincidentally equal title.
    for kind in ("doi:", "pmid:", "arxiv:"):
        x, y = {i for i in a if i.startswith(kind)}, {i for i in b if i.startswith(kind)}
        if x and y and not x & y:
            return False
    for x in members(left):
        key = title_key(x)
        if not key:
            continue
        authors = {compact(v) for v in x.get("authors", []) if compact(v)}
        for y in members(right):
            if key == title_key(y) and authors & {compact(v) for v in y.get("authors", []) if compact(v)}:
                return True
    return False


class PaperIndex:
    def __init__(self, papers=()):
        self.strong: dict[str, list[dict]] = {}
        self.titles: dict[str, list[dict]] = {}
        for paper in papers:
            self.add(paper)

    def add(self, paper: dict) -> None:
        for key in strong_ids(paper):
            self.strong.setdefault(key, []).append(paper)
        for p in members(paper):
            if key := title_key(p):
                self.titles.setdefault(key, []).append(paper)

    def find(self, paper: dict) -> list[dict]:
        candidates = {}
        for key in strong_ids(paper):
            for p in self.strong.get(key, []):
                candidates[id(p)] = p
        for p in members(paper):
            for candidate in self.titles.get(title_key(p), []):
                candidates[id(candidate)] = candidate
        return [p for p in candidates.values() if matches(p, paper)]


def merge_records(records: list[dict]) -> list[dict]:
    from .journal_metrics import merge_journal_metadata
    index = PaperIndex()
    result: list[dict] = []
    retired: set[int] = set()
    owners: dict[int, dict] = {}
    for original in records:
        record = copy.deepcopy(original)
        found = {id(owners.get(id(p), p)): owners.get(id(p), p) for p in index.find(record)}
        if not found:
            result.append(record)
            index.add(record)
            continue
        target = next(iter(found.values()))
        for other in [record, *list(found.values())[1:]]:
            if other is not record and not matches(target, other):
                continue
            aliases = members(target) + members(other)
            unique = {repr(sorted(p.items())): p for p in aliases}
            target["identity_members"] = list(unique.values())
            merge_journal_metadata(target, other)
            for field in ("doi", "pmid", "arxiv_id", "abstract", "authors", "official_url", "published_date"):
                if not target.get(field) and other.get(field):
                    target[field] = copy.deepcopy(other[field])
            if other is not record:
                retired.add(id(other))
                for key, value in list(owners.items()):
                    if value is other:
                        owners[key] = target
                owners[id(other)] = target
        index.add(target)
    return [p for p in result if id(p) not in retired]
