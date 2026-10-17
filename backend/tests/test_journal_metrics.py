import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from literature_agent import api
from literature_agent.config import Settings
from literature_agent.db import Database
from literature_agent.email import render_digest
from literature_agent.journal_metrics import format_jif, normalize_issn, parse_metrics_csv, merge_journal_metadata
from literature_agent.zotero import ZoteroClient


HEADER = "journal,issn,eissn,year,jif\n"
CSV = HEADER + "Fixture Journal,0028-0836,1476-4687,2024,1.2\nFixture Journal,0028-0836,1476-4687,2025,0\n"


@pytest.mark.parametrize("raw, expected", [("00280836", "0028-0836"), ("0028-0836", "0028-0836"), ("2434-561x", "2434-561X"), ("0028-0837", ""), ("Nature", "")])
def test_issn_normalization_checks_checksum(raw, expected):
    assert normalize_issn(raw) == expected


@pytest.mark.parametrize("row", [
    "Fixture,0028-0837,,2025,1.2", "Fixture,0028-0836,,9999,1.2",
    "Fixture,0028-0836,,2025,NaN", "Fixture,0028-0836,,2025,-1",
    "Fixture,0028-0836,,2025,1001", "Fixture,0028-0836,,2025,N/A",
])
def test_reject_invalid_metrics(row):
    with pytest.raises(ValueError):
        parse_metrics_csv(HEADER + row, "Synthetic test source", "")


def test_csv_bom_less_than_and_conflicts():
    records = parse_metrics_csv("\ufeff" + HEADER + "Fixture,0028-0836,,2025,<0.1\n", "Fixture source", "https://example.org/jcr")
    assert records[0]["jif"] == "<0.1"
    with pytest.raises(ValueError, match="冲突"):
        parse_metrics_csv(CSV + "Different,0028-0836,,2025,2\n", "Fixture", "")
    with pytest.raises(ValueError):
        parse_metrics_csv(CSV, "Fixture", "javascript:alert(1)")
    with pytest.raises(ValueError):
        parse_metrics_csv(CSV, "\n", "")


def test_duplicate_sources_retain_later_issns_without_overwriting_evidence():
    first = {"title": "First title", "abstract": "First abstract", "venue": "Fixture", "source": "semantic_scholar"}
    merge_journal_metadata(first, {"issns": ["00280836", "1476-4687"], "venue": "Other name", "venue_type": "journal", "source": "openalex", "abstract": "Other abstract"})
    assert first["issns"] == ["0028-0836", "1476-4687"]
    assert first["abstract"] == "First abstract"
    assert first["venue"] == "Fixture"
    assert first["source"] == "semantic_scholar"
    assert first["venue_type"] == "journal"


def test_match_latest_issn_without_rewriting_history_or_ranking(tmp_path):
    db = Database(tmp_path / "agent.db")
    task = db.create_task({"name": "Study", "topic": "RAG"})
    run = db.create_run(task["id"], 6)
    payload = {"title": "Paper", "venue": "Fixture Journal", "issns": ["00280836"], "source": "crossref", "relevance_score": 0.45}
    db.add_paper(run["id"], "test", payload)
    raw = db.connection.execute("SELECT payload FROM papers").fetchone()[0]
    assert db.list_papers(run["id"])[0]["journal_metric"] is None
    assert db.import_journal_metrics(parse_metrics_csv(CSV, "Synthetic JCR fixture", "https://example.org/jcr")) == 4
    paper = db.list_papers(run["id"])[0]
    assert paper["journal_metric"]["jif"] == "0"
    assert paper["journal_metric"]["year"] == 2025
    assert paper["relevance_score"] == 0.45
    assert "JIF：0" in format_jif(paper)
    assert db.connection.execute("SELECT payload FROM papers").fetchone()[0] == raw
    assert db.with_journal_metric({**payload, "issns": [], "journal_metric": {"jif": "999"}})["journal_metric"] is None
    assert db.with_journal_metric({**payload, "source": "arxiv"})["journal_metric"] is None
    assert db.with_journal_metric({**payload, "venue_type": "proceedings-article"})["journal_metric"] is None
    assert "不适用" in format_jif({"source": "arxiv"})
    # Conflicting electronic/print mappings are rejected for display.
    db.import_journal_metrics(parse_metrics_csv(HEADER + "Different,1476-4687,,2025,2\n", "Fixture", ""))
    assert db.with_journal_metric({**payload, "issns": ["0028-0836", "1476-4687"]})["journal_metric"] is None
    db.close()


def test_api_import_is_atomic_and_papers_expose_metrics(tmp_path, monkeypatch):
    db = Database(tmp_path / "agent.db")
    monkeypatch.setattr(api, "database", db)
    task = db.create_task({"name": "Study", "topic": "RAG"})
    run = db.create_run(task["id"], 6)
    db.update_run(run["id"], status="completed")
    db.add_paper(run["id"], "test", {"title": "Paper", "authors": [], "abstract": "", "published_date": "2025", "source": "crossref", "venue": "Fixture Journal", "issns": ["0028-0836"]})
    with TestClient(api.app) as client:
        assert client.get("/api/journal-metrics").json()["records"] == 0
        template = client.get("/api/journal-metrics/template")
        assert template.text == HEADER
        assert "filename=" in template.headers["content-disposition"]
        response = client.post("/api/journal-metrics/import", json={"csv": CSV + "Bad,0028-0837,,2025,9\n", "source": "Fixture"})
        assert response.status_code == 422
        assert client.get("/api/journal-metrics").json()["records"] == 0
        response = client.post("/api/journal-metrics/import", json={"csv": CSV, "source": "Fixture"})
        assert response.status_code == 200
        assert response.json()["records"] == 4
        paper = client.get(f"/api/runs/{run['id']}/papers").json()[0]
        assert paper["journal_metric"]["jif"] == "0"
        assert paper["venue"] == "Fixture Journal"
        assert client.post("/api/journal-metrics/import", json={"csv": CSV, "source": "Fixture"}).json()["records"] == 4
    db.close()


def test_mail_and_new_zotero_item_include_year_source_without_changing_identifiers(tmp_path):
    metric = {"journal": "Fixture Journal", "jif": "1.2", "year": 2025, "source": "Synthetic <JCR>", "source_url": "https://example.org/jcr"}
    paper = {"title": "Paper", "doi": "10.1234/test", "venue": "Fixture Journal", "issns": ["0028-0836"], "journal_metric": metric}
    message = render_digest({}, [paper])
    assert "1.2（2025；来源：Synthetic <JCR>；用户导入）" in message.text
    assert "Synthetic &lt;JCR&gt;" in message.html
    assert message.attachments[0].text == "10.1234/test\n"
    writes = []
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=[])
        data = json.loads(request.content)[0]
        writes.append(data)
        return httpx.Response(200, json={"successful": {"0": {"key": "COLL0001" if request.url.path.endswith("collections") else "ITEM0001"}}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ZoteroClient(Settings(root=tmp_path, zotero_library_id="123", zotero_api_key="test"), client).import_paper(paper)
    item = writes[-1]
    assert item["publicationTitle"] == "Fixture Journal"
    assert item["ISSN"] == "0028-0836"
    assert "2025" in item["extra"] and "Synthetic <JCR>" in item["extra"]
    assert "JIF source: https://example.org/jcr" in item["extra"]


def test_upgrade_preserves_old_tables_and_creates_backup(tmp_path):
    # Start from the production schema revision immediately before this change.
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    path = tmp_path / "agent.db"
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "20261014_0003")
    connection = sqlite3.connect(path)
    connection.execute("INSERT INTO tasks VALUES ('old', '{}', 'before', 'before')")
    connection.commit()
    connection.close()
    db = Database(path)
    assert db.get_task("old")["created_at"] == "before"
    assert db.journal_metrics_status()["records"] == 0
    assert list((tmp_path / "backups").glob("pre-migration-*.db"))
    db.close()
