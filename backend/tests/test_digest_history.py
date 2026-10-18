import json

import pytest
from fastapi.testclient import TestClient

from literature_agent import api, graph, runner
from literature_agent.config import Settings
from literature_agent.db import Database
from literature_agent.email import render_digest
from literature_agent.llm import ModelProvider, fallback, fallback_query_plan
from literature_agent.paper_identity import matches, merge_records, PaperIndex
from literature_agent.prompts import BUILTIN_PROMPTS
from literature_agent.schemas import TaskCreate, SubscriptionCreate


TITLE = 'A systematic survey of agentic retrieval augmented generation'


def paper(**kwargs):
    return {"title": TITLE, "authors": ["Alice Chen"], "source": "openalex", "source_id": "W1",
            "abstract": "A study of retrieval.", "published_date": "2026-10-01", **kwargs}


def test_shared_identity_aliases_versions_and_conservative_title_matching():
    preprint = paper(source='arxiv', source_id='2601.12345v1', doi='', arxiv_id='2601.12345v1')
    published = paper(doi='https://doi.org/10.1234/PUBLISHED')
    assert matches(preprint, published)
    merged = merge_records([preprint, published, paper(source='crossref', source_id='10.1234/published', doi='10.1234/published')])
    assert len(merged) == 1
    assert merged[0]['doi'] == published['doi']
    assert PaperIndex(merged).find(paper(title='Completely changed title', source='arxiv', source_id='2601.12345v3', arxiv_id='2601.12345v3'))
    assert not matches(paper(doi='10.1234/a'), paper(source_id='W2', doi='10.1234/b'))
    assert not matches(paper(title='RAG'), paper(title='RAG', source_id='W2'))
    assert not matches(paper(), paper(source_id='W2', authors=['Bob Jones']))
    assert not matches(paper(authors=[]), paper(source_id='W2', authors=[]))
    assert not matches(paper(title=''), paper(source_id='W2', title=''))
    # A late bridging record merges two already-indexed representations.
    bridged = merge_records([paper(doi='10.1234/a'), paper(source='arxiv', source_id='2601.12345', title='An unrelated display title', arxiv_id='2601.12345'),
                            paper(source='semantic_scholar', source_id='S1', doi='10.1234/a', external_ids={'ArXiv': '2601.12345'})])
    assert len(bridged) == 1
    conflicting = merge_records([paper(doi='10.1234/a', source_id='A'),
                                 paper(doi='10.1234/b', source_id='B'),
                                 paper(source='semantic_scholar', source_id='S1')])
    assert len(conflicting) == 2


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    db = Database(tmp_path / 'daily.db')
    db.seed_builtin_prompts(BUILTIN_PROMPTS)
    task = db.create_task(TaskCreate(name='Daily research', topic='agentic retrieval', sources=['openalex'], target_count=50, date_from='2023-01-01').model_dump())
    sub = db.create_subscription(task['id'], SubscriptionCreate(**{k: v for k, v in task.items() if k in SubscriptionCreate.model_fields}, recipient='reader@example.org', schedule_time='07:00').model_dump())
    settings = Settings(root=tmp_path, live=True, llm_api_key='test', llm_model='test', journal_metrics_auto=False)
    monkeypatch.setattr(ModelProvider, 'plan_queries', lambda *args: fallback_query_plan(args[1]))
    monkeypatch.setattr(ModelProvider, 'screen', lambda *args: {'relevance_score': .9, 'priority': 'P0', 'recommended_action': 'read', 'relevance_reason': 'Related', 'engine': 'test'})
    monkeypatch.setattr(ModelProvider, 'summarize', lambda _self, record, topic, *args, **kwargs: fallback(record, topic))
    monkeypatch.setattr(graph, 'search_sources', lambda *args, **kwargs: ([paper()], {'openalex': {'status': 'ok', 'count': 1}}))
    monkeypatch.setattr(runner, 'send_message', lambda *args: None)
    yield db, task, sub, settings
    db.close()


def run_day(db, sub, settings, day, send=True):
    run = db.create_run(sub['task_id'], 6, trigger_kind='subscription', subscription_id=sub['id'])
    db.update_run(run['id'], started_at=f'2026-10-{day:02d}T23:00:00+00:00')
    return runner.run_subscription(settings, db, sub, send_email=send, run_id=run['id'])


def test_next_day_excludes_sent_before_screening_and_keeps_unseen_history(runtime, monkeypatch):
    db, task, sub, settings = runtime
    first = run_day(db, sub, settings, 16)
    assert first['paper_count'] == 1 and first['delivery']['status'] == 'sent'
    assert db.get_run_artifact(first['id'], 'query_planner')['payload']['date_to'] == '2026-10-17'
    candidates = [paper(source='arxiv', source_id='2601.12345v2', arxiv_id='2601.12345v2'),
                  paper(title='Previously unseen historical research on retrieval', source_id='W2', published_date='2023-04-01')]
    monkeypatch.setattr(graph, 'search_sources', lambda *a, **k: (candidates, {'openalex': {'status': 'cached', 'count': 2}}))
    second = run_day(db, sub, settings, 17)
    assert second['paper_count'] == 1
    assert db.list_papers(second['id'])[0]['source_id'] == 'W2'
    assert db.get_run_artifact(second['id'], 'relevance_screener')['payload']['evaluated_count'] == 1
    assert db.get_run_artifact(second['id'], 'dedupe')['payload']['history_excluded_count'] == 1
    # Retaining the same subscription with another recipient retains its history.
    third = run_day(db, {**sub, 'recipient': 'changed@example.org'}, settings, 18)
    assert third['paper_count'] == 0
    assert len(db.delivered_papers(sub['id'])[0]) == 2
    # An independent subscription may receive the same research.
    independent = db.create_subscription(task['id'], {**sub, 'recipient': 'different@example.org'})
    assert run_day(db, independent, settings, 19)['paper_count'] == 2


@pytest.mark.parametrize('mode', ['failed', 'no-send'])
def test_failed_delivery_and_no_send_do_not_consume_papers(runtime, monkeypatch, mode):
    db, task, sub, settings = runtime
    if mode == 'failed':
        def fail(*args):
            raise RuntimeError('SMTP failed')
        monkeypatch.setattr(runner, 'send_message', fail)
    first = run_day(db, sub, settings, 16, send=mode != 'no-send')
    assert first['paper_count'] == 1
    assert db.delivered_papers(sub['id']) == ([], 0)
    monkeypatch.setattr(runner, 'send_message', lambda *args: None)
    assert run_day(db, sub, settings, 17)['paper_count'] == 1


def test_manual_task_unaffected_and_merged_result_matches_mail_and_zotero(runtime, monkeypatch):
    db, task, sub, settings = runtime
    run_day(db, sub, settings, 16)
    monkeypatch.setattr(graph, 'search_sources', lambda *a, **k: ([paper(), paper(source='arxiv', source_id='2601.12345v1')], {}))
    manual = db.create_run(task['id'], 6)
    assert runner.execute_run(settings, db, manual['id'], task)['paper_count'] == 1
    assert db.get_run_artifact(manual['id'], 'dedupe')['payload']['merged_count'] == 1


def test_snapshot_recovers_original_date_timezone_and_recipient(runtime):
    db, task, sub, settings = runtime
    run = db.create_run(task['id'], 6, trigger_kind='subscription', subscription_id=sub['id'])
    db.update_run(run['id'], started_at='2026-10-17T23:59:00+00:00')
    run = db.get_run(run['id'])
    original_sub, original_task = runner.subscription_snapshot(db, run, sub, task)
    assert original_task['date_to'] == '2026-10-18'
    assert task['date_to'] == ''
    changed = {**sub, 'timezone': 'America/New_York', 'recipient': 'changed@example.org'}
    assert runner.subscription_snapshot(db, run, changed, {**task, 'date_to': '2001-01-01'}) == (original_sub, original_task)
    another = db.create_run(task['id'], 6)
    assert runner.subscription_snapshot(db, another, {**sub, 'date_to_mode': 'fixed'}, {**task, 'date_to': '2026-10-15'})[1]['date_to'] == '2026-10-15'


def test_history_snapshot_survives_record_changes_and_deletion_and_is_atomic(runtime):
    db, task, sub, settings = runtime
    result = run_day(db, sub, settings, 16)
    db.connection.execute('DELETE FROM papers WHERE run_id=?', (result['id'],))
    db.connection.execute('DELETE FROM runs WHERE id=?', (result['id'],))
    db.connection.commit()
    assert PaperIndex(db.delivered_papers(sub['id'])[0]).find(paper())
    d = db.create_delivery(sub['id'], None, 'digest', sub['recipient'], 'test')
    db.connection.execute("CREATE TRIGGER reject_history BEFORE INSERT ON digest_history BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
    db.connection.commit()
    with pytest.raises(Exception, match='test rollback'):
        db.mark_digest_sent(d['id'], [paper()])
    assert db.get_delivery(d['id'])['status'] == 'pending'
    db.connection.execute('DROP TRIGGER reject_history')
    db.connection.commit()
    assert db.delete_subscription(sub['id'])
    assert db.connection.execute('SELECT COUNT(*) FROM digest_history').fetchone()[0] == 0


def test_migration_backfills_all_sent_digests_without_history_limit(tmp_path):
    path = tmp_path / 'upgrade.db'
    db = Database(path)
    task = db.create_task({'name': 'Migration', 'topic': 'Research'})
    sub = db.create_subscription(task['id'], {'name': 'Old', 'date_to': '2026-10-15'})
    run = db.create_run(task['id'], 6)
    db.update_run(run['id'], status='completed', paper_count=1)
    db.add_paper(run['id'], 'W1', paper())
    for _ in range(55):
        db.create_delivery(sub['id'], run['id'], 'digest', 'reader@example.org', 'test', status='sent')
    db.create_delivery(sub['id'], run['id'], 'digest', 'reader@example.org', 'failed', status='failed')
    db.create_delivery(sub['id'], run['id'], 'test', 'reader@example.org', 'smtp', status='sent')
    db.create_delivery(sub['id'], 'missing-run', 'digest', 'reader@example.org', 'missing', status='sent')
    db.connection.execute('DROP TABLE digest_history')
    db.connection.execute("UPDATE alembic_version SET version_num='20261017_0005'")
    db.connection.commit()
    db.close()
    for _ in range(2):
        db = Database(path)
        papers, missing = db.delivered_papers(sub['id'])
        assert len(papers) == 55 and missing == 1
        assert db.get_subscription(sub['id'])['date_to_mode'] == 'fixed'
        assert db.connection.execute('SELECT count(*) FROM digest_history').fetchone()[0] == 56
        db.close()


def test_subscription_api_date_policy_defaults_and_patch_preservation(runtime, monkeypatch):
    db, task, sub, settings = runtime
    monkeypatch.setattr(api, 'database', db)
    with TestClient(api.app) as client:
        assert client.get('/api/subscriptions/' + sub['id']).json()['date_to_mode'] == 'today'
        response = client.patch('/api/subscriptions/' + sub['id'], json={'date_to_mode': 'fixed', 'date_to': '2026-10-15'})
        assert response.status_code == 200
        assert client.patch('/api/subscriptions/' + sub['id'], json={'schedule_time': '08:00'}).json()['date_to_mode'] == 'fixed'
        assert client.patch('/api/subscriptions/' + sub['id'], json={'date_to_mode': 'invalid'}).status_code == 422
        response = client.patch('/api/subscriptions/' + sub['id'], json={'date_to_mode': 'today', 'date_from': '2026-10-16'})
        assert response.status_code == 200
        task_read = client.get('/api/tasks/' + task['id'])
        assert task_read.status_code == 200 and task_read.json()['date_to'] == ''


def test_zero_fresh_mail_distinguishes_seen_relevance_and_source_failure():
    stats = {'unique_count': 4, 'remaining_count': 0, 'history_excluded_count': 4, 'merged_count': 2}
    message = render_digest({}, [], {'openalex': {'status': 'ok', 'count': 4}}, stats)
    assert '均已' in message.text and '本次无新增' in message.html
    message = render_digest({}, [], {'openalex': {'status': 'failed', 'error': 'HTTP 429'}}, stats)
    assert '检索异常' in message.text and 'HTTP 429' in message.html
    assert '没有找到符合相关性要求' in render_digest({}, [], {}, {'remaining_count': 4}).text
