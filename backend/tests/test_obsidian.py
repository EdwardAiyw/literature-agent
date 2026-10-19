import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from literature_agent.obsidian import END, START, export_snapshot
from literature_agent.email import render_digest
from literature_agent.journal_metrics import with_metric_records


def delivery(papers, **extra):
    return {"deliveries": [{"id": "delivery-1", "run_id": "run-1", "sent_at": "2026-10-18T23:10:00+00:00", "subject": "Daily", "papers": papers, **extra}]}


def test_export_catches_up_preserves_annotations_and_deduplicates(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    state = tmp_path / "state.json"
    paper = {"id": "p1", "title": "A sufficiently long title about new research methods", "authors": ["Alice"], "doi": "10.1234/abc", "summary": {"method": "Old method"}}
    first = export_snapshot(delivery([paper]), vault, "Literature Agent", state)
    assert first["unique_notes"] == 1
    note = next((vault / "Literature Agent/Papers").glob("*.md"))
    note.write_text(note.read_text(encoding="utf-8").replace("## 我的阅读笔记", "## 我的阅读笔记\n\nMy own comments"), encoding="utf-8")
    updated = {**paper, "id": "p2", "doi": "https://doi.org/10.1234/ABC", "summary": {"method": "Updated method"}}
    second = export_snapshot(delivery([updated], id="delivery-2"), vault, "Literature Agent", state)
    assert second == {"deliveries": 1, "paper_visits": 1, "unique_notes": 1, "days": 1}
    content = note.read_text(encoding="utf-8")
    assert "My own comments" in content and "Updated method" in content and "Old method" not in content
    daily = (vault / "Literature Agent/Daily/2026-10-19.md").read_text(encoding="utf-8")
    assert daily.count("[[Literature Agent/Papers/") == 2
    before = note.stat().st_mtime_ns
    export_snapshot(delivery([updated], id="delivery-2"), vault, "Literature Agent", state)
    assert note.stat().st_mtime_ns == before


def test_export_refuses_escape_and_user_file_conflicts(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    with pytest.raises(ValueError):
        export_snapshot(delivery([]), vault, "../outside", tmp_path / "state.json")
    folder = vault / "Literature Agent"
    folder.mkdir()
    existing = folder / "论文索引.md"
    existing.write_text("Personal index", encoding="utf-8")
    with pytest.raises(ValueError, match="preserved file"):
        export_snapshot(delivery([]), vault, "Literature Agent", tmp_path / "state.json")
    assert existing.read_text(encoding="utf-8") == "Personal index"


def test_marker_content_cannot_break_preservation(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    paper = {"id": "p1", "title": "../../A [bad|title]", "abstract": START + " bad " + END}
    export_snapshot(delivery([paper]), vault, "Literature Agent", tmp_path / "state.json")
    note = next((vault / "Literature Agent/Papers").glob("*.md"))
    content = note.read_text(encoding="utf-8")
    assert content.count(START) == content.count(END) == 1
    assert note.resolve().is_relative_to(vault.resolve())


def test_remote_snapshot_filters_sent_digest_and_has_no_history_limit(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/obsidian-snapshot.py"
    spec = importlib.util.spec_from_file_location("obsidian_snapshot", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db = tmp_path / "test.db"
    connection = sqlite3.connect(db)
    connection.executescript("CREATE TABLE deliveries(id,run_id,subject,sent_at,subscription_id,kind,status); CREATE TABLE papers(id,run_id,payload); CREATE TABLE zotero_imports(paper_id,destination,payload,updated_at);")
    for i in range(105):
        connection.execute("INSERT INTO deliveries VALUES (?,?,?,?,?,?,?)", (str(i), "run", "Digest", "2026-10-19T00:00:00+00:00", "s1", "digest", "sent"))
    for kind, status, sub in [("test", "sent", "s1"), ("digest", "failed", "s1"), ("digest", "sent", "s2")]:
        connection.execute("INSERT INTO deliveries VALUES ('excluded','run','Other','2026-10-19',?,?,?)", (sub, kind, status))
    connection.execute("INSERT INTO papers VALUES ('p1','run',?)", (json.dumps({"title": "Paper"}),))
    connection.commit()
    connection.close()
    before = db.read_bytes()
    result = module.snapshot(db, "s1", "2026-10-18T16:00:00+00:00")
    assert len(result["deliveries"]) == 105
    assert result["deliveries"][0]["papers"][0]["title"] == "Paper"
    assert db.read_bytes() == before


def test_email_content_metrics_diagnostics_and_attachments_are_exported(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    state = tmp_path / "state.json"
    paper = {"id": "p1", "title": "Journal article", "authors": ["Alice"], "doi": "10.1234/a", "issns": ["0028-0836"], "venue_type": "journal", "summary": {"research_problem": "Problem", "main_findings": ["Finding"], "confidence": 0}, "screening": {"relevance_reason": "Screened reason"}}
    metric = {"issn": "0028-0836", "journal": "Test journal", "year": 2025, "jif": "0", "source": "Publisher", "source_kind": "publisher", "source_url": "https://example.org/metric"}
    snapshot = delivery([paper])
    snapshot["journal_metrics"] = [metric]
    snapshot["deliveries"][0].update(subscription={"topic": "My topic"}, diagnostics={"openalex": {"status": "partial", "count": 12, "error": "Rate limit"}}, dedupe={"merged_count": 3, "history_excluded_count": 7})
    expected = render_digest({"topic": "My topic"}, [with_metric_records(paper, [metric])], snapshot["deliveries"][0]["diagnostics"], snapshot["deliveries"][0]["dedupe"])
    export_snapshot(snapshot, vault, "Literature Agent", state)
    root = vault / "Literature Agent"
    assert next((root / "Attachments").glob("* -- email.txt")).read_bytes() == expected.text.encode("utf-8")
    assert next((root / "Attachments").glob("* -- attachment-1.txt")).read_bytes() == expected.attachments[0].text.encode("utf-8")
    note = next((root / "Papers").glob("*.md")).read_text(encoding="utf-8")
    assert "2025" in note and "https://example.org/metric" in note and "## 摘要置信度\n\n0" in note
    assert "Screened reason" in note
    email = next((root / "Emails").glob("*.md")).read_text(encoding="utf-8")
    assert "按历史运行记录重建" in email and "Rate limit" in email
    assert "邮件正文与附件" in (root / "Daily/2026-10-19.md").read_text(encoding="utf-8")
    export_snapshot(snapshot, vault, "Literature Agent", state)
    assert len(list((root / "Attachments").glob("*.txt"))) == 2


def test_sent_email_snapshot_survives_later_changes_and_preserves_personal_notes(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    state = tmp_path / "state.json"
    snapshot = delivery([])
    snapshot["deliveries"][0]["email_archive"] = {"subject": "Original mail", "text": "Original body\n```\n", "attachments": [{"filename": "../../identifier.txt", "text": "10.1234/sent\n"}]}
    export_snapshot(snapshot, vault, "Literature Agent", state)
    root = vault / "Literature Agent"
    email = next((root / "Emails").glob("*.md"))
    email.write_text(email.read_text(encoding="utf-8") + "\nPersonal mail annotation\n", encoding="utf-8")
    snapshot["deliveries"][0]["subscription"] = {"topic": "Changed topic"}
    export_snapshot(snapshot, vault, "Literature Agent", state)
    content = email.read_text(encoding="utf-8")
    assert "发送时正文快照" in content and "Original body" in content and "Personal mail annotation" in content
    assert not (vault / "identifier.txt").exists()
    attachment = next((root / "Attachments").glob("* -- attachment-1.txt"))
    attachment.write_text("Personal attachment edits", encoding="utf-8")
    with pytest.raises(ValueError, match="personal changes"):
        export_snapshot(snapshot, vault, "Literature Agent", state)
    assert attachment.read_text() == "Personal attachment edits"
