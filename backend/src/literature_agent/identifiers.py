"""Conservative identifiers for Zotero's Add Item by Identifier dialog."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from .zotero import normalize_doi


@dataclass(frozen=True)
class IdentifierExport:
    identifiers: tuple[str, ...]
    missing: tuple[str, ...]
    excluded: int

    @property
    def text(self) -> str:
        return "\n".join(self.identifiers) + ("\n" if self.identifiers else "")


def _isbn(value: str) -> str:
    value = re.sub(r"[\s-]", "", value).upper()
    if re.fullmatch(r"\d{9}[\dX]", value):
        return value if sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(value)) % 11 == 0 else ""
    if re.fullmatch(r"97[89]\d{10}", value):
        return value if sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(value)) % 10 == 0 else ""
    return ""


def paper_identifier(paper: dict) -> str:
    external = paper.get("external_ids") or paper.get("externalIds") or {}
    if not isinstance(external, dict):
        external = {}
    doi = normalize_doi(str(paper.get("doi") or external.get("DOI") or ""))
    if re.fullmatch(r"10\.\d{4,9}/[^\s<>]+", doi):
        return doi
    source = str(paper.get("source", "")).lower()
    url = urlparse(str(paper.get("official_url") or ""))
    pmid = str(paper.get("pmid") or external.get("PubMed") or (paper.get("source_id") if source == "pubmed" else "") or "").strip()
    if not pmid and url.hostname == "pubmed.ncbi.nlm.nih.gov":
        pmid = url.path.strip("/")
    if re.fullmatch(r"[1-9]\d{0,8}", pmid):
        return pmid
    arxiv = str(paper.get("arxiv_id") or external.get("ArXiv") or (paper.get("source_id") if source == "arxiv" else "") or "").strip()
    # Prefer the complete official URL for legacy category/number IDs.
    if url.hostname in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        arxiv = re.sub(r"^/(?:abs|pdf)/", "", unquote(url.path)).removesuffix(".pdf")
    arxiv = re.sub(r"^arxiv:\s*", "", arxiv, flags=re.I)
    if re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-zA-Z][a-zA-Z.\-]+/\d{7})(?:v\d+)?", arxiv):
        return "arXiv:" + re.sub(r"v\d+$", "", arxiv)
    values = paper.get("isbn") or paper.get("ISBN") or external.get("ISBN") or []
    for value in values if isinstance(values, list) else [values]:
        isbn = _isbn(str(value))
        if isbn:
            return isbn
    bibcode = str(paper.get("ads_bibcode") or paper.get("bibcode") or external.get("ADS") or "").strip()
    if re.fullmatch(r"\d{4}[A-Za-z.]{5}[A-Za-z0-9.]{4}[A-Za-z.][A-Za-z0-9.]{4}[A-Za-z]", bibcode):
        return bibcode
    return ""


def export_identifiers(papers: list[dict]) -> IdentifierExport:
    identifiers: dict[str, None] = {}
    missing = []
    excluded = 0
    for paper in papers:
        if paper.get("review") == "ignore":
            excluded += 1
            continue
        identifier = paper_identifier(paper)
        if identifier:
            identifiers[identifier] = None
        else:
            missing.append(str(paper.get("title") or "Untitled"))
    return IdentifierExport(tuple(identifiers), tuple(missing), excluded)
