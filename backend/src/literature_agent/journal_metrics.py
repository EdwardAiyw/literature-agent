"""Journal impact factors with explicit year and provenance."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal


def normalize_issn(value: str) -> str:
    compact = re.sub(r"[\s-]", "", value).upper()
    if not re.fullmatch(r"\d{7}[\dX]", compact):
        return ""
    if sum((8-i) * (10 if c == "X" else int(c)) for i, c in enumerate(compact)) % 11:
        return ""
    return compact[:4] + "-" + compact[4:]


def parse_metrics_csv(content: str, source: str, source_url: str) -> list[dict]:
    source = source.strip()
    if not source or len(source) > 200 or "\n" in source or "\r" in source:
        raise ValueError("请填写有效的数据来源名称（最多 200 字）。")
    if source_url and not re.fullmatch(r"https?://[^\s]+", source_url):
        raise ValueError("来源链接必须是 http/https 地址。")
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    required = {"journal", "issn", "year", "jif"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("CSV 需要 journal,issn,year,jif 列；可另加 eissn 列。")
    records: dict[tuple[str, int], dict] = {}
    current_year = datetime.now(timezone.utc).year
    for line, row in enumerate(reader, start=2):
        if line > 100001:
            raise ValueError("单次最多导入 100000 行。")
        journal = (row.get("journal") or "").strip()
        raw_issns = [(row.get("issn") or "").strip(), (row.get("eissn") or "").strip()]
        issns = [normalize_issn(value) for value in raw_issns if value]
        year = (row.get("year") or "").strip()
        jif = (row.get("jif") or "").strip()
        if not journal or len(journal) > 500 or any(c in journal for c in "\r\n"):
            raise ValueError(f"第 {line} 行期刊名称无效。")
        if not issns or not all(issns):
            raise ValueError(f"第 {line} 行 ISSN/eISSN 无效或校验位错误。")
        if not year.isdigit() or not 1975 <= int(year) <= current_year:
            raise ValueError(f"第 {line} 行指标年份无效。")
        if not re.fullmatch(r"(?:\d{1,4}(?:\.\d{1,4})?|<0\.1)", jif) or (jif != "<0.1" and Decimal(jif) > 1000):
            raise ValueError(f"第 {line} 行 JIF 无效；接受非负数或 <0.1。")
        for issn in issns:
            record = {"issn": issn, "journal": journal, "year": int(year), "jif": jif, "source": source, "source_url": source_url}
            key = (issn, int(year))
            if key in records and records[key] != record:
                raise ValueError(f"第 {line} 行与相同 ISSN/年份的其他记录冲突。")
            records[key] = record
    if not records:
        raise ValueError("CSV 没有可导入的指标记录。")
    return list(records.values())


def metrics_applicable(paper: dict) -> bool:
    if paper.get("venue") in {"arXiv", "arXiv (Cornell University)"} and paper.get("venue_type") not in {"journal", "journal-article"}:
        return False
    return (paper.get("source") != "arxiv" or paper.get("venue_type") in {"journal", "journal-article"}) and paper.get("venue_type") not in {
        "repository", "conference", "proceedings-article", "book", "book-chapter", "posted-content",
    }


def merge_journal_metadata(primary: dict, duplicate: dict) -> None:
    """Retain ISSNs from another source for the same canonical citation."""
    values = []
    for record in (primary, duplicate):
        issns = record.get("issns") or []
        values.extend([issns] if isinstance(issns, str) else issns)
    primary["issns"] = list(dict.fromkeys(filter(None, (normalize_issn(str(v)) for v in values))))
    for key in ("venue", "venue_type"):
        if not primary.get(key) and duplicate.get(key):
            primary[key] = duplicate[key]


def format_jif(paper: dict) -> str:
    if not metrics_applicable(paper):
        return "期刊影响因子：不适用（预印本或非期刊文献）"
    metric = paper.get("journal_metric")
    if not metric:
        if paper.get("journal_metric_status") == "insufficient_metadata":
            return "期刊影响因子：期刊信息不足"
        return "期刊影响因子：暂未查到"
    provenance = "官网公布" if metric.get("source_kind") == "publisher" else "用户导入"
    return f"期刊影响因子 JIF：{metric['jif']}（{metric['year']}；来源：{metric['source']}；{provenance}）"
