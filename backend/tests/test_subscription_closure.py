from dataclasses import asdict, replace
from datetime import datetime, timezone
import json

from fastapi.testclient import TestClient
import pytest

from literature_agent import api, graph, runner, subscription_closure as closure
from literature_agent.daily import due_subscriptions
from literature_agent.llm import ModelProvider
from literature_agent.worker import LocalRunWorker
from test_digest_history import paper, run_day, runtime  # Shared live-shaped, fully mocked pipeline.


def test_zero_pauses_only_this_subscription_and_sends_two_distinct_messages(runtime, monkeypatch):
    db, task, sub, settings = runtime
    messages = []
    monkeypatch.setattr(runner, "send_message", lambda _s, recipient, message: messages.append((recipient, message)))
    run_day(db, sub, settings, 16)
    other_task = db.create_task({**task, "name": "Another topic"})
    other = db.create_subscription(other_task["id"], {**sub, "name": "Other"})
    result = run_day(db, sub, settings, 17)
    assert result["auto_paused"] and result["closure_status"] == "completed"
    saved = db.get_subscription(sub["id"])
    assert not saved["enabled"] and saved["auto_pause"]["reason"] == "all_delivered"
    assert saved["auto_pause"]["paper_count"] == 1 and saved["auto_pause"]["report_ready"]
    assert db.get_subscription(other["id"])["enabled"]
    assert len(messages) == 3
    assert "自动暂停" in messages[1][1].subject
    assert "历史文献汇总" in messages[2][1].subject
    assert "0 篇文献" not in "\n".join(m.subject for _, m in messages)
    report = messages[2][1].attachments[0]
    assert report.filename == "literature-history-report.md"
    assert "[P0001]" in report.text and "A study of retrieval" in report.text
    assert "未读取论文全文" in report.text
    assert len(db.delivered_papers(sub["id"])[0]) == 1
    assert sub["id"] not in [s["id"] for s in due_subscriptions(db, db.list_subscriptions(enabled_only=True), datetime.now(timezone.utc))]
    closure.process_closure(settings, db, result["id"], sender=lambda *a: pytest.fail("duplicate send"))
    assert len(messages) == 3


@pytest.mark.parametrize("status", ["failed", "partial", "rate_limited", "disabled", "not_configured", "unknown", "missing"])
def test_source_problems_do_not_pause(runtime, monkeypatch, status):
    db, task, sub, settings = runtime
    diagnostics = {} if status == "missing" else {"openalex": {"status": status, "count": 0, "error": "unavailable"}}
    monkeypatch.setattr(graph, "search_sources", lambda *a, **k: ([], diagnostics))
    result = run_day(db, sub, settings, 16)
    assert db.get_subscription(sub["id"])["enabled"]
    assert not result.get("auto_paused")
    assert not db.list_subscription_closures()


def test_screening_failure_is_not_evidence_of_exhaustion(runtime, monkeypatch):
    db, task, sub, settings = runtime
    def fail(*args):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(ModelProvider, "screen", fail)
    result = run_day(db, sub, settings, 16)
    assert result["paper_count"] == 0
    assert db.get_run_artifact(result["id"], "result_manifest")["payload"]["errors"]
    assert db.get_subscription(sub["id"])["enabled"]


@pytest.mark.parametrize("send", [True, False])
def test_healthy_empty_retrieval_and_no_send(runtime, monkeypatch, send):
    db, task, sub, settings = runtime
    monkeypatch.setattr(graph, "search_sources", lambda *a, **k: ([], {"openalex": {"status": "ok", "count": 0}}))
    result = run_day(db, sub, settings, 16, send=send)
    assert db.get_subscription(sub["id"])["enabled"] is (not send)
    if send:
        assert result["closure_status"] == "completed"
        job = db.get_run_artifact(result["id"], closure.NODE)["payload"]
        assert job["reason"] == "no_relevant_papers"
        assert "尚无成功推送" in job["report"]
    else:
        assert not db.list_subscription_closures() and not db.list_deliveries()


def test_successful_rejection_pauses_but_fixture_does_not(runtime, monkeypatch):
    db, task, sub, settings = runtime
    monkeypatch.setattr(ModelProvider, "screen", lambda *args: {"relevance_score": .01, "priority": "P2", "recommended_action": "ignore", "relevance_reason": "unrelated", "engine": "test"})
    result = run_day(db, sub, settings, 16)
    assert result["auto_paused"]
    assert db.get_subscription(sub["id"])["auto_pause"]["reason"] == "no_relevant_papers"
    assert not closure.should_pause(db, result, {**task, "sources": ["fixture"]}, [])


def test_history_uses_every_sent_snapshot_and_labels_missing_old_evidence(runtime):
    db, task, sub, settings = runtime
    for i in range(61):
        run = db.create_run(task["id"], 6)
        p = paper(source_id=f"W{i}", title=f"Different historical research paper number {i}", doi=f"10.1234/{i}", summary={"method": "saved method"})
        db.add_paper(run["id"], f"W{i}", {**p, "abstract": "MODIFIED later record"})
        db.update_run(run["id"], paper_count=1, status="completed")
        delivery = db.create_delivery(sub["id"], run["id"], "digest", sub["recipient"], "old digest")
        db.save_run_artifact(run["id"], "email_digest." + delivery["id"], {"papers": [p]})
        db.mark_digest_sent(delivery["id"], [p])
    duplicate = db.create_delivery(sub["id"], run["id"], "digest", sub["recipient"], "duplicate")
    db.save_run_artifact(run["id"], "email_digest." + duplicate["id"], {"papers": [p]})
    db.mark_digest_sent(duplicate["id"], [p])
    for kind, status in (("digest", "failed"), ("test", "sent"), ("history_summary", "sent")):
        db.create_delivery(sub["id"], run["id"], kind, sub["recipient"], "excluded", status=status)
    legacy = db.create_delivery(sub["id"], "deleted-run", "digest", sub["recipient"], "legacy")
    db.mark_digest_sent(legacy["id"], [paper(source_id="legacy", doi="10.9999/legacy", title="Legacy metadata only research paper")])
    db.create_delivery(sub["id"], "unknown-run", "digest", sub["recipient"], "missing", status="sent")
    corpus = db.sent_digest_corpus(sub["id"])
    assert corpus["delivery_count"] == 64 and len(corpus["papers"]) == 62
    assert corpus["duplicate_count"] == 1 and corpus["missing_papers"] == 1
    assert corpus["reconstructed_deliveries"] == 2
    assert not any("MODIFIED" in p.get("abstract", "") for p in corpus["papers"])
    assert any(not p.get("abstract") and "持久推送历史" in p["history_provenance"] for p in corpus["papers"])


def test_pause_and_job_creation_roll_back_together(runtime):
    db, task, sub, settings = runtime
    run = db.create_run(task["id"], 6, trigger_kind="subscription", subscription_id=sub["id"])
    db.connection.execute("CREATE TRIGGER reject_closure BEFORE INSERT ON run_artifacts BEGIN SELECT RAISE(ABORT, 'rollback pause'); END")
    db.connection.commit()
    with pytest.raises(Exception, match="rollback pause"):
        db.pause_empty_subscription(run["id"], sub, task, "all_delivered")
    assert db.get_subscription(sub["id"])["enabled"]
    assert not db.list_subscription_closures()


def test_duplicate_history_combines_abstract_with_available_brief(runtime):
    db, task, sub, settings = runtime
    run = db.create_run(task["id"], 6)
    for p in (paper(abstract="Original abstract", summary={}),
              paper(abstract="", summary={"method": "Saved method", "evidence_warnings": ["Abstract only"]})):
        delivery = db.create_delivery(sub["id"], run["id"], "digest", sub["recipient"], "test")
        db.save_run_artifact(run["id"], "email_digest." + delivery["id"], {"papers": [p]})
        db.mark_digest_sent(delivery["id"], [p])
    corpus = db.sent_digest_corpus(sub["id"])
    assert len(corpus["papers"]) == 1
    p = corpus["papers"][0]
    assert p["abstract"] == "Original abstract" and p["summary"]["method"] == "Saved method"
    assert p["summary"]["evidence_warnings"] == ["Abstract only"]


def test_schedule_patch_cannot_accidentally_resume_a_concurrent_auto_pause(runtime):
    db, task, sub, settings = runtime
    stale_payload = {**sub, "schedule_time": "09:00"}
    run = db.create_run(task["id"], 6, trigger_kind="subscription", subscription_id=sub["id"])
    db.pause_empty_subscription(run["id"], sub, task, "all_delivered")
    updated = db.update_subscription(sub["id"], stale_payload, preserve_enabled=True)
    assert not updated["enabled"] and updated["auto_pause"]
    assert updated["schedule_time"] == "09:00"


def test_summary_send_retry_keeps_report_and_skips_successful_notice(runtime, monkeypatch):
    db, task, sub, settings = runtime
    run_day(db, sub, settings, 16)
    sent = []
    def send(_s, recipient, message):
        sent.append(message.subject)
        if "历史文献汇总" in message.subject:
            raise RuntimeError("SMTP temporarily unavailable")
    monkeypatch.setattr(runner, "send_message", send)
    result = run_day(db, sub, settings, 17)
    assert result["closure_status"] == "failed"
    assert db.get_subscription(sub["id"])["auto_pause"]["report_ready"]
    assert not db.get_subscription(sub["id"])["enabled"]
    report = db.get_run_artifact(result["id"], closure.NODE)["payload"]["report"]
    monkeypatch.setattr(ModelProvider, "synthesize_history", lambda *a: pytest.fail("must reuse report"))
    assert db.transition_closure(result["id"], {"failed"}, "queued")
    finished = closure.process_closure(settings, db, result["id"], sender=lambda _s, _r, message: sent.append(message.subject))
    assert finished["status"] == "completed" and finished["report"] == report
    assert sum("自动暂停" in subject for subject in sent) == 1
    assert len([d for d in db.list_deliveries() if d["kind"] == "history_summary"]) == 1
    assert len(db.delivered_papers(sub["id"])[0]) == 1


def test_generation_retry_and_restart_recover_without_retrieval(runtime, monkeypatch):
    db, task, sub, settings = runtime
    run_day(db, sub, settings, 16)
    original = ModelProvider.synthesize_history
    def fail(*a):
        raise ValueError("invalid model response")
    monkeypatch.setattr(ModelProvider, "synthesize_history", fail)
    result = run_day(db, sub, settings, 17)
    assert result["closure_status"] == "failed"
    assert not db.get_subscription(sub["id"])["auto_pause"]["report_ready"]
    monkeypatch.setattr(ModelProvider, "synthesize_history", original)
    monkeypatch.setattr(graph, "search_sources", lambda *a, **k: pytest.fail("must not retrieve"))
    sent = []
    monkeypatch.setattr(closure, "send_message", lambda _s, _r, message: sent.append(message.subject))
    # Simulate interruption after the retry was claimed but before it generated the report.
    db.transition_closure(result["id"], {"failed"}, "running")
    worker = LocalRunWorker(settings, db)
    assert worker.recover() == 1
    worker.close()
    assert db.get_subscription(sub["id"])["auto_pause"]["status"] == "completed"
    assert len(sent) == 1 and "历史文献汇总" in sent[0]
    assert not db.get_subscription(sub["id"])["enabled"]


def test_large_history_batches_all_papers_and_resumes_cached_chunks(runtime, monkeypatch):
    db, task, sub, settings = runtime
    run = db.create_run(task["id"], 6, trigger_kind="subscription", subscription_id=sub["id"])
    job = db.pause_empty_subscription(run["id"], sub, task, "all_delivered")
    job["papers"] = [{**paper(source_id=str(i), abstract=(f"Evidence for {i}. " * 900)), "ref": f"P{i:04d}",
                      "history_provenance": "发送时邮件快照"} for i in range(1, 35)]
    seen = set()
    sizes = []
    def synthesize(_self, topic, language, materials, refs):
        seen.update(refs)
        sizes.append(len(json.dumps(materials, ensure_ascii=False)))
        return {key: [{"text": "Bounded synthesis", "refs": refs}] for key in closure.SECTIONS}
    monkeypatch.setattr(ModelProvider, "synthesize_history", synthesize)
    analysis = closure.synthesize(settings, db, job)
    assert seen == {p["ref"] for p in job["papers"]}
    assert len(sizes) > 2 and max(sizes) <= closure.INPUT_BUDGET
    assert analysis["themes"]
    monkeypatch.setattr(ModelProvider, "synthesize_history", lambda *a: pytest.fail("cached chunks must survive"))
    assert closure.synthesize(settings, db, job) == analysis
    # The appendix preserves complete abstracts even when evidence required several chunks.
    assert job["papers"][0]["abstract"] in closure.report_text(job, analysis)


@pytest.mark.parametrize("invalid", ["unknown_ref", "empty", "oversized", "wrong_sections"])
def test_model_output_rejects_invalid_synthesis(runtime, monkeypatch, invalid):
    db, task, sub, settings = runtime
    provider = ModelProvider("https://invalid.local", "test", "test")
    value = {key: [{"text": "A supported point", "refs": ["P0001"]}] for key in closure.SECTIONS}
    if invalid == "unknown_ref":
        value["themes"][0]["refs"] = ["P9999"]
    elif invalid == "empty":
        value = {key: [] for key in closure.SECTIONS}
    elif invalid == "oversized":
        value["themes"][0]["text"] = "x" * 8000
    else:
        value = {"themes": []}
    monkeypatch.setattr(provider, "_complete_json", lambda *a: value)
    # runtime replaces the pipeline method; exercise the actual validator explicitly.
    with pytest.raises(ValueError):
        REAL_SYNTHESIZE(provider, sub["topic"], "zh", [], ["P0001"])


REAL_SYNTHESIZE = ModelProvider.synthesize_history


def test_api_reports_retry_and_resume_preserve_history(runtime, monkeypatch):
    db, task, sub, settings = runtime
    run_day(db, sub, settings, 16)
    def fail(*a):
        raise RuntimeError("SMTP down")
    monkeypatch.setattr(runner, "send_message", fail)
    result = run_day(db, sub, settings, 17)
    monkeypatch.setattr(api, "database", db)
    monkeypatch.setattr(api, "settings", replace(settings, live=False))
    with TestClient(api.app) as client:
        assert client.get(f"/api/subscriptions/{sub['id']}/closure/report").status_code == 404
        queued = []
        monkeypatch.setattr(api.run_worker, "submit_closure", queued.append)
        response = client.post(f"/api/subscriptions/{sub['id']}/closure/retry")
        assert response.status_code == 202 and queued == [result["id"]]
        assert client.post(f"/api/subscriptions/{sub['id']}/closure/retry").status_code == 409
        assert client.delete(f"/api/subscriptions/{sub['id']}").status_code == 409
        assert db.create_run_if_idle(task["id"], 6) is None
        closure.process_closure(settings, db, result["id"], sender=lambda *a: None)
        response = client.get(f"/api/subscriptions/{sub['id']}/closure/report")
        assert response.status_code == 200 and "P0001" in response.text
        assert "attachment" in response.headers["content-disposition"]
        response = client.patch(f"/api/subscriptions/{sub['id']}", json={"schedule_time": "09:00"})
        assert response.status_code == 200 and response.json()["auto_pause"]["status"] == "completed"
        assert not response.json()["enabled"]
        response = client.patch(f"/api/subscriptions/{sub['id']}", json={"enabled": True})
        assert response.status_code == 200 and response.json()["enabled"]
        assert len(db.delivered_papers(sub["id"])[0]) == 1
        kinds = {d["kind"] for d in client.get("/api/deliveries").json()}
        assert {"digest", "pause_notice", "history_summary"} <= kinds
        assert client.post("/api/subscriptions/missing/closure/retry").status_code == 404
        assert client.delete(f"/api/subscriptions/{sub['id']}").status_code == 200


def test_notice_escapes_html_and_keeps_no_empty_identifier_attachment(runtime):
    db, task, sub, settings = runtime
    run = db.create_run(task["id"], 6, trigger_kind="subscription", subscription_id=sub["id"])
    job = db.pause_empty_subscription(run["id"], {**sub, "topic": "<script>topic</script>"}, task, "no_relevant_papers")
    message = closure.pause_notice(job)
    assert "<script>" not in message.html and "&lt;script&gt;" in message.html
    assert not asdict(message)["attachments"]


def test_explicit_close_adopts_existing_partial_zero_without_rerunning(runtime, monkeypatch):
    db, task, sub, settings = runtime
    monkeypatch.setattr(graph, "search_sources", lambda *a, **k: ([], {
        "openalex": {"status": "partial", "count": 0, "error": "One query was skipped"}}))
    result = run_day(db, sub, settings, 16)
    assert db.get_subscription(sub["id"])["enabled"]
    monkeypatch.setattr(api, "database", db)
    monkeypatch.setattr(api, "settings", replace(settings, live=False))
    with TestClient(api.app) as client:
        queued = []
        monkeypatch.setattr(api.run_worker, "submit_closure", queued.append)
        response = client.post(f"/api/subscriptions/{sub['id']}/closure/start")
        assert response.status_code == 202 and not response.json()["enabled"]
        assert response.json()["auto_pause"]["reason"] == "user_requested"
        assert queued == [result["id"]]
        assert client.post(f"/api/subscriptions/{sub['id']}/closure/start").status_code == 202
        assert queued == [result["id"]]
        job = db.get_run_artifact(result["id"], closure.NODE)["payload"]
        message = closure.pause_notice(job)
        assert "按用户要求" in message.text and "One query was skipped" in message.text
        assert "正常检索和筛选" not in message.text
        assert len(db.list_runs(task["id"])) == 1
        assert client.post("/api/subscriptions/missing/closure/start").status_code == 404


def test_explicit_close_rejects_nonzero_latest_run(runtime, monkeypatch):
    db, task, sub, settings = runtime
    run_day(db, sub, settings, 16)
    monkeypatch.setattr(api, "database", db)
    with TestClient(api.app) as client:
        assert client.post(f"/api/subscriptions/{sub['id']}/closure/start").status_code == 409
        assert db.get_subscription(sub["id"])["enabled"]
        assert not db.list_subscription_closures()
