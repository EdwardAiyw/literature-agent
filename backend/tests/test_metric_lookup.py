import asyncio
from dataclasses import replace

import httpx
import pytest

from literature_agent.config import Settings
from literature_agent.db import Database
from literature_agent.email import render_digest
from literature_agent.metric_lookup import Lookup, Page, _enrich, enrich_run, parse_explicit_jif, permitted_url

ISSN = "2624-8212"
HOME = "https://www.frontiersin.org/journals/artificial-intelligence"
TABLE = """<p>2025 Journal Impact Factors (published in 2026)</p>
<table><tr><th>Journal</th><th>Journal Impact Factor</th><th>CiteScore</th></tr>
<tr><td><a href="/journals/artificial-intelligence">Fixture Journal</a></td><td>0</td><td>9.9</td></tr></table>"""


@pytest.mark.parametrize("content,expected", [
    ("Journal Impact Factor (2025) 1.2", (2025, "1.2")),
    ("2025 Journal Impact Factor: 0", (2025, "0")),
    ("2025 Impact Factor: 1.2", (2025, "1.2")),
    ("5-year Journal Impact Factor (2025) 9.9", None),
    ("Journal Impact Factor: &lt;0.1 (2025)", (2025, "<0.1")),
    ("CiteScore 2025: 9.9", None),
    ("Impact Factor 1.2 Copyright 2025", None),
    ("Journal Impact Factor: 1.2 Published in 2025", None),
    ("Journal Impact Factor (2099) 1.2", None),
    ("2025 Journal Impact Factor: 1.2 / 2025 Journal Impact Factor: 3.4", None),
    ("<script>2025 Journal Impact Factor: 99</script>CiteScore 1.2", None),
])
def test_explicit_metric_year_only(content, expected):
    assert parse_explicit_jif(Page(content)) == expected


@pytest.mark.parametrize("url", ["http://www.nature.com/", "https://localhost/", "https://127.0.0.1/", "https://nature.com.evil.test/", "https://user@www.nature.com/", "https://www.nature.com:8443/"])
def test_allowlist_rejects_unsafe_urls(url):
    assert not permitted_url(url)


def setup(tmp_path):
    db = Database(tmp_path / "agent.db")
    task = db.create_task({"name": "Fixture", "topic": "AI"})
    run = db.create_run(task["id"], 6)
    settings = Settings(root=tmp_path, live=True)
    return db, run["id"], settings


def mock_handler(calls, table=TABLE):
    def handler(request):
        url = str(request.url)
        calls.append(url)
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": {"DOI": "10.1234/fixture", "ISSN": [ISSN], "container-title": ["Fixture Journal"], "type": "journal-article"}})
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"issn": [ISSN], "type": "journal", "display_name": "Fixture Journal", "homepage_url": HOME})
        if request.url.path == "/about/impact":
            return httpx.Response(200, text=table)
        return httpx.Response(200, text=f"<h1>Fixture Journal</h1><p>ISSN {ISSN}</p>")
    return handler


def test_doi_enrichment_shared_journal_cache_mail_and_provenance(tmp_path):
    db, run_id, settings = setup(tmp_path)
    for i in range(2):
        db.add_paper(run_id, str(i), {"title": f"Paper {i}", "source": "crossref", "doi": "10.1234/fixture", "relevance_score": .8})
    db.add_paper(run_id, "preprint", {"title": "Preprint", "source": "arxiv"})
    calls = []
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler(calls))) as client:
            first = await _enrich(settings, db, run_id, client)
            second = await _enrich(settings, db, run_id, client)
            return first, second
    first, second = asyncio.run(run())
    assert first["matched"] == second["matched"] == 2
    assert first["not_applicable"] == 1
    assert len(calls) == 4  # one DOI, one registry, homepage, shared publisher table
    papers = db.list_papers(run_id)
    journal = next(p for p in papers if p.get("doi"))
    assert journal["venue"] == "Fixture Journal"
    assert journal["relevance_score"] == .8
    assert journal["journal_metric"]["jif"] == "0"
    assert journal["journal_metric"]["year"] == 2025
    assert journal["journal_metric"]["source_kind"] == "publisher"
    message = render_digest({}, papers)
    assert "官网公布" in message.text and "2025" in message.text
    assert "https://www.frontiersin.org/about/impact" in message.text
    assert "href='https://www.frontiersin.org/about/impact'" in message.html
    assert message.attachments[0].text == "10.1234/fixture\n"
    db.close()


@pytest.mark.parametrize("table", [
    TABLE.replace("2025 Journal Impact Factors (published in 2026)", "Metrics published in 2026"),
    TABLE.replace("Journal Impact Factor</th><th>CiteScore", "CiteScore</th><th>Journal Impact Factor"),
    TABLE.replace("/journals/artificial-intelligence", "/journals/other-journal"),
    TABLE.replace("<td>0</td>", "<td>-</td>"),
])
def test_frontiers_requires_year_correct_column_and_exact_journal_link(tmp_path, table):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler([], table))) as client:
            return await Lookup(Settings(root=tmp_path), client).journal(ISSN)
    assert asyncio.run(run())["status"] == "not_found"


@pytest.mark.parametrize("status,text", [(200, "<title>Client Challenge</title>"), (429, "limited"), (403, "blocked")])
def test_failed_refresh_preserves_prior_metric_and_caches_failure(tmp_path, status, text):
    db, run_id, settings = setup(tmp_path)
    db.add_paper(run_id, "one", {"source": "crossref", "venue_type": "journal", "issns": [ISSN]})
    db.import_journal_metrics([{"issn": ISSN, "journal": "Fixture Journal", "year": 2024, "jif": "1.2", "source": "Publisher", "source_url": HOME, "source_kind": "publisher"}])
    calls = []
    good = mock_handler(calls)
    def handler(request):
        if request.url.host == "api.openalex.org":
            return good(request)
        calls.append(str(request.url))
        return httpx.Response(status, text=text)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await _enrich(settings, db, run_id, client)
            await _enrich(settings, db, run_id, client)
    asyncio.run(run())
    assert len(calls) == 2
    assert db.get_metric_lookup("issn:" + ISSN)["status"] == "failed"
    assert db.list_papers(run_id)[0]["journal_metric"]["year"] == 2024
    db.close()


def test_deadline_cancels_network_and_digest_can_still_render(tmp_path):
    db, run_id, settings = setup(tmp_path)
    db.add_paper(run_id, "one", {"title": "Still sent", "source": "crossref", "venue_type": "journal", "issns": [ISSN]})
    async def handler(request):
        await asyncio.sleep(10)
        return httpx.Response(500)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await _enrich(settings, db, run_id, client, budget=.02)
    result = asyncio.run(run())
    assert result["timed_out"]
    assert "Still sent" in render_digest({}, db.list_papers(run_id)).text
    db.close()


def test_manual_same_year_wins_automatic_but_newer_year_is_used(tmp_path):
    db, run_id, _ = setup(tmp_path)
    record = {"issn": ISSN, "journal": "Fixture Journal", "year": 2024, "jif": "1.2", "source": "Manual", "source_url": ""}
    db.import_journal_metrics([record])
    db.import_journal_metrics([{**record, "jif": "99", "source_kind": "publisher"}], automatic=True)
    assert db.with_journal_metric({"issns": [ISSN]})["journal_metric"]["jif"] == "1.2"
    db.import_journal_metrics([{**record, "year": 2025, "jif": "0", "source_kind": "publisher"}], automatic=True)
    assert db.with_journal_metric({"issns": [ISSN]})["journal_metric"]["jif"] == "0"
    db.close()


def test_disabled_and_unexpected_failure_do_not_break_run(tmp_path, monkeypatch):
    from literature_agent import metric_lookup
    db, run_id, settings = setup(tmp_path)
    assert enrich_run(replace(settings, journal_metrics_auto=False), db, run_id) == {"enabled": False}
    async def fail(*args):
        raise RuntimeError("secret detail must not leak")
    monkeypatch.setattr(metric_lookup, "_enrich", fail)
    assert enrich_run(settings, db, run_id) == {"enabled": True, "error": "RuntimeError"}
    assert db.get_run_artifact(run_id, "journal_metrics")["payload"]["error"] == "RuntimeError"
    db.close()


def test_redirect_to_unapproved_host_is_not_followed(tmp_path):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/secrets"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match="unsupported_host"):
                await Lookup(Settings(root=tmp_path), client).fetch(HOME)
    asyncio.run(run())
    assert calls == [HOME]


@pytest.mark.parametrize("publisher_fails", [False, True])
def test_live_subscription_enriches_before_email_and_keeps_import_order(tmp_path, monkeypatch, publisher_fails):
    from literature_agent import graph, runner, metric_lookup
    from literature_agent.llm import ModelProvider, fallback_query_plan
    from literature_agent.prompts import BUILTIN_PROMPTS
    from literature_agent.schemas import TaskCreate
    db, _, settings = setup(tmp_path)
    db.seed_builtin_prompts(BUILTIN_PROMPTS)
    task = db.create_task(TaskCreate(name="Daily", topic="AI retrieval", sources=["crossref"]).model_dump())
    sub = db.create_subscription(task["id"], {"name": "Daily", "topic": "AI retrieval", "recipient": "fixture@example.org", "timezone": "Asia/Hong_Kong", "schedule_time": "07:00"})
    monkeypatch.setattr(ModelProvider, "plan_queries", lambda *_: fallback_query_plan(task))
    monkeypatch.setattr(graph, "search_sources", lambda *_args, **_kwargs: ([{
        "title": "Fixture retrieval method", "abstract": "A study of retrieval.", "source": "crossref", "doi": "10.1234/fixture", "authors": [],
    }], {"crossref": {"status": "ok", "count": 1}}))
    monkeypatch.setattr(ModelProvider, "screen", lambda *_: {"relevance_score": .9, "priority": "P0", "recommended_action": "read", "relevance_reason": "Relevant", "engine": "test-model"})
    monkeypatch.setattr(ModelProvider, "summarize", lambda *_args, **_kwargs: {"research_problem": "Retrieval", "main_findings": ["Fixture finding"]})
    factory = httpx.AsyncClient
    good = mock_handler([])
    def handler(request):
        if publisher_fails and request.url.host == "www.frontiersin.org":
            return httpx.Response(429)
        return good(request)
    monkeypatch.setattr(metric_lookup.httpx, "AsyncClient", lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs))
    order = []
    def reserve(database, run_id):
        papers = database.list_papers(run_id)
        assert bool(papers[0]["journal_metric"]) is not publisher_fails
        return {"id": "fixture-batch"}
    monkeypatch.setattr(runner, "reserve_automatic", reserve)
    def mail(_settings, _recipient, message):
        order.append("email")
        if publisher_fails:
            assert "暂未查到" in message.text
        else:
            assert "JIF：0（2025" in message.text
            assert "官网公布" in message.html and "影响因子来源" in message.html
    monkeypatch.setattr(runner, "send_message", mail)
    monkeypatch.setattr(runner, "process_batch", lambda *_: order.append("zotero"))
    result = runner.run_subscription(replace(settings, llm_model="fixture", llm_api_key="fixture"), db, sub)
    assert result["status"] == "completed"
    assert result["delivery"]["status"] == "sent"
    assert order == ["email", "zotero"]
    assert db.get_run_artifact(result["id"], "journal_metrics")["payload"]["matched"] == int(not publisher_fails)
    db.close()


def test_legacy_frontiers_links_match_same_journal(tmp_path):
    table = TABLE.replace('/journals/artificial-intelligence', 'http://journal.frontiersin.org/journal/artificial-intelligence')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler([], table))) as client:
            return await Lookup(Settings(root=tmp_path), client).journal(ISSN)
    assert asyncio.run(run())["status"] == "matched"


def test_arxiv_doi_and_venue_are_not_journal_metrics(tmp_path):
    db, run_id, settings = setup(tmp_path)
    db.add_paper(run_id, "one", {"title": "Preprint", "source": "openalex", "doi": "10.48550/arxiv.1234.56789"})
    db.add_paper(run_id, "two", {"title": "Another preprint", "source": "openalex", "venue": "arXiv (Cornell University)"})
    def handler(request):
        pytest.fail("Known preprint must not spend network requests")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await _enrich(settings, db, run_id, client)
    assert asyncio.run(run())["not_applicable"] == 2
    db.close()


def test_fetch_concurrency_is_capped_at_two(tmp_path):
    inflight = 0
    peak = 0
    async def handler(request):
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(.01)
        inflight -= 1
        return httpx.Response(200, text="Fixture")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            lookup = Lookup(Settings(root=tmp_path), client)
            await asyncio.gather(*(lookup.fetch(HOME + str(i)) for i in range(6)))
    asyncio.run(run())
    assert peak == 2


def test_auto_setting_persists_and_api_preserves_import_interfaces(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from literature_agent import api
    from literature_agent.config import ConfigManager, MemorySecretStore
    db, _, settings = setup(tmp_path)
    base = replace(settings, data_dir=tmp_path, live=False)
    store = MemorySecretStore()
    manager = ConfigManager(base, store)
    monkeypatch.setattr(api, "database", db)
    monkeypatch.setattr(api, "config_manager", manager)
    monkeypatch.setattr(api, "settings", manager.get())
    with TestClient(api.app) as client:
        assert client.get('/api/journal-metrics').json()['auto_enabled'] is True
        assert client.put('/api/settings/journal_metrics', json={'journal_metrics_auto': False}).status_code == 200
        assert client.get('/api/journal-metrics').json()['auto_enabled'] is False
        assert ConfigManager(base, store).get().journal_metrics_auto is False
        assert client.put('/api/settings/journal_metrics', json={'llm_model': 'wrong-section'}).status_code == 422
        assert client.get('/api/journal-metrics/template').text.startswith('journal,issn,eissn,year,jif')
    db.close()


def test_expired_failure_retries_and_migration_preserves_imports(tmp_path):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    import sqlite3
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / 'agent.db'
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'alembic'))
    config.set_main_option('sqlalchemy.url', 'sqlite:///' + path.as_posix())
    command.upgrade(config, '20261017_0004')
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO journal_metrics VALUES (?, ?, ?, ?)", (ISSN, 2024, '{"issn":"2624-8212","journal":"Fixture Journal","year":2024,"jif":"1.2","source":"Manual","source_url":""}', 'before'))
    db = Database(path)
    assert db.with_journal_metric({'issns': [ISSN]})['journal_metric']['jif'] == '1.2'
    assert list((tmp_path / 'backups').glob('pre-migration-*.db'))
    task = db.create_task({'name': 'Retry', 'topic': 'AI'})
    run_id = db.create_run(task['id'], 6)['id']
    db.add_paper(run_id, 'one', {'source': 'crossref', 'venue_type': 'journal', 'issns': [ISSN]})
    db.save_metric_lookup('issn:' + ISSN, {'status': 'failed'}, days=-1)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler([]))) as client:
            return await _enrich(Settings(root=tmp_path, live=True), db, run_id, client)
    assert asyncio.run(run())['matched'] == 1
    assert db.list_papers(run_id)[0]['journal_metric']['year'] == 2025
    db.close()
