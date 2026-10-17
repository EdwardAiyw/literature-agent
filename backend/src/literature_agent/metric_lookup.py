"""Bounded, non-LLM lookup of JIF explicitly published by journal owners.

Only allowlisted HTTPS publishers are fetched. HTTP success alone is not evidence:
identity, metric label, value and metric year must all be established.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import httpx

from .journal_metrics import metrics_applicable, normalize_issn

PUBLISHERS = (
    "frontiersin.org", "nature.com", "link.springer.com", "springer.com",
    "mdpi.com", "journals.plos.org", "onlinelibrary.wiley.com",
    "sciencedirect.com", "academic.oup.com", "cambridge.org",
    "tandfonline.com", "journals.sagepub.com", "ieee.org", "acm.org",
)
APIS = {"api.crossref.org", "api.openalex.org"}
BUDGET_SECONDS = 60


def permitted_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return (parts.scheme == "https" and not parts.username and not parts.password
            and parts.port in (None, 443) and (host in APIS or any(host == p or host.endswith("." + p) for p in PUBLISHERS)))


class Page(HTMLParser):
    """Visible text and table cells; scripts are never executed or used as evidence."""
    def __init__(self, content: str):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.href = ""
        self.anchor: list[str] = []
        self.skip = 0
        self.heading: list[str] | None = None
        self.headings: list[str] = []
        self.feed(content)
        self.text = re.sub(r"\s+", " ", " ".join(self.parts)).strip()

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "noscript"}:
            self.skip += 1
        if self.skip:
            return
        values = dict(attrs)
        if tag == "a":
            self.href, self.anchor = values.get("href", ""), []
        if tag == "tr":
            self.row = []
        if tag in {"h1", "title"}:
            self.heading = []
        if tag in {"td", "th"}:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg", "noscript"}:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in {"h1", "title"} and self.heading is not None:
            self.headings.append(re.sub(r"\s+", " ", " ".join(self.heading)).strip())
            self.heading = None
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join(self.anchor).strip()))
            self.href = ""
        if tag in {"td", "th"} and self.cell is not None:
            if self.row is not None:
                self.row.append(re.sub(r"\s+", " ", " ".join(self.cell)).strip())
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
            if self.href:
                self.anchor.append(data)
            if self.cell is not None:
                self.cell.append(data)
            if self.heading is not None:
                self.heading.append(data)


def parse_explicit_jif(page: Page) -> tuple[int, str] | None:
    """Accept only an adjacent explicit metric-year/value pair, never release dates."""
    label = r"(?:(?:Journal\s+)?Impact\s+Factor|\bJIF\b)"
    value = r"(<0\.1|\d{1,3}(?:\.\d{1,4})?)"
    year = r"(20\d{2})"
    pairs = set()
    for pattern, order in [
        (label + r"\s*[:(\-]?\s*" + year + r"\s*[):\-]?\s*" + value + r"(?![\d.])", (0, 1)),
        (label + r"\s*:\s*" + value + r"\s*\(\s*" + year + r"\s*\)", (1, 0)),
        (year + r"\s+" + label + r"\s*[:\-]?\s*" + value + r"(?![\d.])", (0, 1)),
    ]:
        for match in re.finditer(pattern, page.text, re.I):
            if re.search(r"(?:5|five)[\s-]*year\s*$", page.text[max(0, match.start()-24):match.start()], re.I):
                continue
            groups = match.groups()
            y, v = int(groups[order[0]]), groups[order[1]]
            if y <= datetime.now(timezone.utc).year:
                pairs.add((y, v))
    if not pairs:
        return None
    latest = max(y for y, _ in pairs)
    current = {(y, v) for y, v in pairs if y == latest}
    return next(iter(current)) if len(current) == 1 else None


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", ""))


def journal_home_url(url: str) -> str:
    """Canonicalize documented Frontiers legacy paths, without fuzzy title matching."""
    p = urlsplit(url)
    if (p.hostname or "") in {"www.frontiersin.org", "journal.frontiersin.org"}:
        match = re.fullmatch(r"/(?:(?:journal|journals)/)?([a-z][a-z-]+)/?", p.path)
        if match:
            return "https://www.frontiersin.org/journals/" + match[1]
    return url


class Lookup:
    def __init__(self, settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client
        self.gate = asyncio.Semaphore(2)
        self.pages: dict[str, asyncio.Task] = {}

    async def fetch(self, url: str) -> tuple[str, str]:
        for _ in range(4):
            if not permitted_url(url):
                raise ValueError("unsupported_host")
            async with self.gate:
                async with self.client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if response.status_code != 200:
                        raise ValueError(f"http_{response.status_code}")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 4_000_000:
                            raise ValueError("response_too_large")
                    content = body.decode("utf-8", errors="replace")
                    if re.search(r"<title>\s*(?:Client Challenge|Just a moment)|enable JavaScript to proceed", content, re.I):
                        raise ValueError("challenge_page")
                    return url, content
        raise ValueError("redirect_limit")

    async def page(self, url: str) -> tuple[str, Page]:
        key = canonical_url(url)
        if key not in self.pages:
            async def load():
                final, content = await self.fetch(url)
                return final, Page(content)
            self.pages[key] = asyncio.create_task(load())
        return await self.pages[key]

    async def metadata(self, paper: dict) -> dict:
        doi = re.sub(r"^https?://(?:dx\.)?doi.org/", "", paper.get("doi") or "", flags=re.I).strip()
        if not re.fullmatch(r"10\.\d{4,9}/\S+", doi, re.I):
            return {"status": "not_found"}
        try:
            import json
            _, body = await self.fetch("https://api.crossref.org/works/" + quote(doi, safe=""))
            item = json.loads(body)["message"]
            if str(item.get("DOI", "")).lower() != doi.lower():
                raise ValueError("doi_mismatch")
            issns = list(dict.fromkeys(filter(None, [normalize_issn(v) for v in item.get("ISSN", [])])))
            return {"status": "matched", "venue": next(iter(item.get("container-title") or []), ""),
                    "venue_type": item.get("type", ""), "issns": issns}
        except (ValueError, KeyError, TypeError, httpx.HTTPError):
            return {"status": "failed"}

    async def journal(self, issn: str) -> dict:
        try:
            import json
            url = "https://api.openalex.org/sources/issn:" + issn
            if self.settings.openalex_api_key:
                url += "?api_key=" + quote(self.settings.openalex_api_key, safe="")
            _, body = await self.fetch(url)
            source = json.loads(body)
            aliases = list(dict.fromkeys(filter(None, [normalize_issn(v) for v in source.get("issn", [])])))
            if issn not in aliases or source.get("type") != "journal":
                return {"status": "not_found", "reason": "unverified_journal"}
            home = source.get("homepage_url") or ""
            if home.startswith("http://"):
                home = "https://" + home[7:]
            home = journal_home_url(home)
            if not permitted_url(home) or urlsplit(home).hostname in APIS:
                return {"status": "not_found", "reason": "unsupported_publisher"}
            home, page = await self.page(home)
            name = source.get("display_name", "")
            # Registry identity is confirmed against actual publisher page text.
            compact = page.text.replace("-", "")
            identity_heading = any(h.casefold() == name.casefold() or h.casefold().startswith((name.casefold() + " |", name.casefold() + " -")) for h in page.headings) if name else False
            if not any(v.replace("-", "") in compact for v in aliases) and not identity_heading:
                return {"status": "not_found", "reason": "journal_identity_mismatch"}
            metric_url, pair = home, parse_explicit_jif(page)
            evidence_url = ""
            if (urlsplit(home).hostname or "").endswith("frontiersin.org"):
                metric_url, table = await self.page("https://www.frontiersin.org/about/impact")
                years = set(re.findall(r"\b(20\d{2}) Journal Impact Factors\s*\(published in", table.text))
                linked_names = {text.casefold() for href, text in table.links if canonical_url(journal_home_url(urljoin(metric_url, href))) == canonical_url(home)}
                # Fixed table columns are verified before interpreting a numeric cell.
                header_ok = any(row[:3] == ["Journal", "Journal Impact Factor", "CiteScore"] for row in table.rows)
                candidates = {row[1] for row in table.rows if len(row) >= 3 and row[0].casefold() in linked_names and re.fullmatch(r"<0\.1|\d{1,3}(?:\.\d{1,4})?", row[1])}
                if len(years) == 1 and len(candidates) == 1 and header_ok:
                    y = int(next(iter(years)))
                    pair = (y, next(iter(candidates))) if y <= datetime.now(timezone.utc).year else None
                    evidence_url = home
                else:
                    pair = None
            elif not pair:
                # Only direct metric links under this journal's own path are followed.
                base = canonical_url(home)
                for href, text in page.links:
                    candidate = urljoin(home, href)
                    if not canonical_url(candidate).startswith(base + "/") or not re.search(r"impact|metrics", text + " " + urlsplit(candidate).path, re.I):
                        continue
                    metric_url, metric_page = await self.page(candidate)
                    pair = parse_explicit_jif(metric_page)
                    if pair:
                        break
                    # Bound link traversal even when a publisher has many links.
                    return {"status": "not_found", "reason": "no_explicit_jif_year"}
            if not pair:
                return {"status": "not_found", "reason": "no_explicit_jif_year"}
            year, value = pair
            return {"status": "matched", "metric": {"journal": name, "year": year, "jif": value,
                    "source": urlsplit(metric_url).hostname, "source_url": metric_url,
                    "identity_url": evidence_url or home, "source_kind": "publisher",
                    "fetched_at": datetime.now(timezone.utc).isoformat()}, "issns": aliases}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return {"status": "failed", "reason": "publisher_or_registry_unavailable"}


async def _enrich(settings, database, run_id: str, client=None, budget: float = BUDGET_SECONDS):
    papers = database.list_papers(run_id)
    owned = client is None
    client = client or httpx.AsyncClient(timeout=12, follow_redirects=False, headers={"User-Agent": "LiteratureAgent/0.3 (journal-metrics)"})
    lookup = Lookup(settings, client)
    tasks: list[asyncio.Task] = []
    attempted: set[str] = set()

    async def work():
        # Work by DOI first, then journal. Cache writes happen on this event-loop thread.
        missing: dict[str, list[dict]] = {}
        for paper in papers:
            if paper.get("doi") and (not paper.get("issns") or not paper.get("venue_type")):
                missing.setdefault(paper["doi"].lower(), []).append(paper)

        async def metadata(doi, entries):
            key = "doi:" + doi
            cached = database.get_metric_lookup(key)
            if re.search(r"(?:^|doi.org/)10\.48550/arxiv\.", doi, re.I):
                result = {"status": "matched", "venue": "arXiv", "venue_type": "posted-content", "issns": []}
            else:
                result = cached or await lookup.metadata(entries[0])
            if not cached:
                database.save_metric_lookup(key, result, 30 if result["status"] == "matched" else 1)
            if result["status"] == "matched":
                for paper in entries:
                    merged = {k: result.get(k) or paper.get(k) for k in ("venue", "venue_type")}
                    merged["issns"] = list(dict.fromkeys([*(paper.get("issns") or []), *result.get("issns", [])]))
                    paper.update(merged)
                    database.enrich_paper_journal(paper["id"], merged)

        tasks.extend(asyncio.create_task(metadata(k, v)) for k, v in missing.items())
        if tasks:
            await asyncio.gather(*tasks)
        groups: dict[str, list[str]] = {}
        for paper in papers:
            if metrics_applicable(paper):
                aliases = list(dict.fromkeys(filter(None, (normalize_issn(v) for v in paper.get("issns") or []))))
                if aliases:
                    # Reuse a shared representative across print/electronic ISSNs.
                    representative = next((k for k, vs in groups.items() if set(vs) & set(aliases)), aliases[0])
                    groups[representative] = list(dict.fromkeys([*groups.get(representative, []), *aliases]))

        async def journal(issn, aliases):
            attempted.add(issn)
            cached = next((v for a in aliases if (v := database.get_metric_lookup("issn:" + a))), None)
            result = cached or await lookup.journal(issn)
            if result["status"] == "matched":
                # Only registry-confirmed aliases receive this metric.
                database.import_journal_metrics([{**result["metric"], "issn": a} for a in result["issns"]], automatic=True)
            if not cached:
                for alias in result.get("issns", [issn]):
                    database.save_metric_lookup("issn:" + alias, result, 30 if result["status"] == "matched" else 1)

        tasks.extend(asyncio.create_task(journal(k, v)) for k, v in groups.items())
        if tasks:
            await asyncio.gather(*tasks)

    timed_out = False
    try:
        await asyncio.wait_for(work(), timeout=budget)
    except TimeoutError:
        timed_out = True
    finally:
        for task in [*tasks, *lookup.pages.values()]:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, *lookup.pages.values(), return_exceptions=True)
        if owned:
            await client.aclose()
    if timed_out:
        for issn in attempted:
            if not database.get_metric_lookup("issn:" + issn):
                database.save_metric_lookup("issn:" + issn, {"status": "failed", "reason": "run_time_budget"})
    counts = {"matched": 0, "not_found": 0, "failed": 0, "not_applicable": 0, "insufficient_metadata": 0, "conflict": 0}
    for paper in database.list_papers(run_id):
        counts[paper["journal_metric_status"]] += 1
    lookup_failed = sum(1 for issn in attempted if (database.get_metric_lookup("issn:" + issn) or {}).get("status") == "failed")
    return {**counts, "lookup_failed": lookup_failed, "total": len(papers), "timed_out": timed_out}


def enrich_run(settings, database, run_id: str) -> dict:
    if not settings.live or not settings.journal_metrics_auto:
        result = {"enabled": False}
    else:
        database.add_run_event(run_id, "journal_metrics", "started", "正在查询期刊影响因子；查询失败仍会推送文献。")
        try:
            result = {"enabled": True, **asyncio.run(_enrich(settings, database, run_id))}
        except Exception as exc:
            # Metrics are optional; a failing lookup must never suppress a digest.
            result = {"enabled": True, "error": type(exc).__name__}
    database.save_run_artifact(run_id, "journal_metrics", result)
    if not result["enabled"]:
        message = "已跳过自动影响因子查询。"
    elif result.get("error"):
        message = "影响因子查询未完成，已有指标仍可展示，文献照常推送。"
    else:
        message = f"影响因子已匹配 {result['matched']} 篇；不适用 {result['not_applicable']} 篇；信息不足 {result['insufficient_metadata']} 篇；查询失败 {result['lookup_failed']} 本期刊。"
        if result["timed_out"]:
            message += "已达查询时间上限，文献照常推送。"
    database.add_run_event(run_id, "journal_metrics", "completed" if result["enabled"] else "skipped", message, artifact_type="journal_metrics")
    return result
