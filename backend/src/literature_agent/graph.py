from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import TypedDict

import httpx
from langgraph.graph import END, StateGraph

from .config import Settings
from .db import Database
from .decisions import JevDecisionProvider
from .llm import ModelProvider, fallback, fallback_evidence_review, fallback_query_plan, fallback_screen
from .prompts import prompt_for
from .sources import search_sources


class GraphState(TypedDict, total=False):
    task: dict
    run_id: str
    node: str
    query_plan: dict
    records: list[dict]
    source_diagnostics: dict[str, dict]
    errors: list[str]


def fixture_records(topic: str) -> list[dict]:
    key = hashlib.sha1(topic.encode()).hexdigest()[:8]
    return [
        {
            "title": f"Evidence-grounded retrieval for {topic}",
            "authors": ["Fixture Author"],
            "abstract": f"This fixture record demonstrates retrieval and evidence evaluation for {topic}.",
            "published_date": str(date.today()),
            "source": "fixture",
            "source_id": f"fixture-{key}-1",
            "official_url": "https://example.org/paper-1",
            "open_access_url": "",
            "doi": "",
            "language": "en",
        },
        {
            "title": f"A review of methods related to {topic}",
            "authors": ["Fixture Researcher"],
            "abstract": f"This fixture record reviews methods, limitations, and evaluation settings related to {topic}.",
            "published_date": "2024-01-01",
            "source": "fixture",
            "source_id": f"fixture-{key}-2",
            "official_url": "https://example.org/paper-2",
            "open_access_url": "",
            "doi": "",
            "language": "en",
        },
    ]


def canonical(record: dict) -> str:
    if record.get("doi"):
        return "doi:" + record["doi"].lower().strip().removeprefix("https://doi.org/")
    if record.get("source_id"):
        return record["source"] + ":" + record["source_id"].lower().strip()
    return "title:" + re.sub(r"[^\w]+", "", record.get("title", "").lower(), flags=re.UNICODE)


def build_graph(settings: Settings, database: Database, prompts: list[dict]):
    provider = ModelProvider(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    decisions = JevDecisionProvider(settings, database)

    def errors_for(state: GraphState, node: str, exc: Exception) -> list[str]:
        errors = list(state.get("errors", []))
        errors.append(f"{node}: {type(exc).__name__}: {exc}")
        return errors

    def started(state: GraphState, node: str, message: str) -> None:
        database.update_run(state["run_id"], status="running", current_node=node)
        database.add_run_event(state["run_id"], node, "started", message)

    def completed(state: GraphState, node: str, message: str, step: int, artifact: dict) -> None:
        database.save_run_artifact(state["run_id"], node, artifact)
        database.update_run(state["run_id"], current_node=node, progress=step)
        database.add_run_event(state["run_id"], node, "completed", message, artifact_type=node)

    def plan(state: GraphState) -> GraphState:
        started(state, "query_planner", "Building the research task contract")
        task = state["task"]
        try:
            query_plan = provider.plan_queries(task, prompt_for(prompts, "query_planner")["body"])
            errors = list(state.get("errors", []))
        except Exception as exc:
            query_plan = fallback_query_plan(task)
            errors = errors_for(state, "query_planner", exc)
        contract = {
            "topic": task["topic"],
            "research_questions": task.get("research_questions", []),
            "language": task["language"],
            "output_language": task["output_language"],
            "sources": task.get("sources", []),
            "target_count": task["target_count"],
            "evidence_review": task["evidence_review"],
            "decision_policy": {"jev_enabled": decisions.configured, "mode": decisions.mode,
                                "model": settings.jev_model, "auto_threshold": settings.jev_auto_threshold,
                                "review_threshold": settings.jev_review_threshold},
            "query_plan": query_plan,
            "prompt_snapshot": {prompt["role"]: {"id": prompt["id"], "version": prompt["version"]} for prompt in prompts},
        }
        completed(state, "query_planner", f"Prepared {len(query_plan['queries'])} query route(s)", 1, contract)
        return {"node": "query_planner", "query_plan": query_plan, "errors": errors}

    def retrieve(state: GraphState) -> GraphState:
        started(state, "retrieval", "Retrieving candidate records")
        task = state["task"]
        errors = list(state.get("errors", []))
        requested_sources = task.get("sources") or state["query_plan"].get("source_routing", [])
        records: list[dict] = []
        diagnostics: dict[str, dict] = {}
        source_mode = "fixture"
        if not settings.live or requested_sources == ["fixture"]:
            records = fixture_records(task["topic"])
            diagnostics = {"fixture": {"status": "ok", "count": len(records), "error": ""}}
        else:
            source_mode = "live"
            with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "literature-agent/0.2"}) as client:
                records, diagnostics = search_sources(
                    requested_sources,
                    tuple(state["query_plan"].get("queries") or [task["topic"]]),
                    task["target_count"],
                    task.get("date_from", ""),
                    task.get("date_to", ""),
                    client,
                    settings,
                    cache=database,
                )
            for name, result in diagnostics.items():
                if result["status"] == "failed":
                    errors.append(f"retrieval/{name}: {result['error']}")
            if not records:
                records = fixture_records(task["topic"])
                source_mode = "fixture_fallback"
                diagnostics["fixture"] = {"status": "fallback", "count": len(records), "error": "No live source returned records"}
        artifact = {"source_mode": source_mode, "sources": diagnostics, "retrieved_count": len(records), "errors": errors[-10:]}
        completed(state, "retrieval", f"Retrieved {len(records)} candidate record(s)", 2, artifact)
        return {"node": "retrieval", "records": records, "source_diagnostics": diagnostics, "errors": errors}

    def dedupe(state: GraphState) -> GraphState:
        started(state, "dedupe", "Normalizing and removing duplicate records")
        seen: set[str] = set()
        records = []
        for record in state.get("records", []):
            identifier = canonical(record)
            if identifier in seen:
                continue
            seen.add(identifier)
            record["canonical_id"] = identifier
            records.append(record)
        completed(state, "dedupe", f"Kept {len(records)} unique record(s)", 3, {"unique_count": len(records)})
        return {"node": "dedupe", "records": records, "errors": state.get("errors", [])}

    def screen(state: GraphState) -> GraphState:
        started(state, "relevance_screener", "Assessing relevance against the task contract")
        task = state["task"]
        errors = list(state.get("errors", []))
        screened = []
        jev_evaluated = 0
        jev_auto = 0
        prompt = prompt_for(prompts, "relevance_screener")["body"]
        for record in state.get("records", []):
            jev_decision = None
            if decisions.configured:
                try:
                    jev_decision = decisions.screen_paper(state["run_id"], record, task)
                    jev_evaluated += 1
                    jev_auto += int(jev_decision["auto_eligible"])
                except Exception as exc:
                    errors = errors_for({"errors": errors}, "jev_relevance_screener", exc)
            if jev_decision and not settings.jev_shadow_mode and jev_decision["auto_eligible"]:
                decision = jev_decision
            else:
                try:
                    decision = provider.screen(record, task, prompt)
                except Exception as exc:
                    decision = fallback_screen(record, task["topic"])
                    errors = errors_for({"errors": errors}, "relevance_screener", exc)
            if jev_decision:
                decision["jev"] = {"mode": decisions.mode, "engine": jev_decision["engine"],
                    "relevance_score": jev_decision["relevance_score"],
                    "decision_confidence": jev_decision["decision_confidence"],
                    "auto_eligible": jev_decision["auto_eligible"]}
                decision["requires_human_review"] = jev_decision["decision_confidence"] < settings.jev_review_threshold
            record["screening"] = decision
            record["relevance_score"] = decision["relevance_score"]
            record["priority"] = decision["priority"]
            screened.append(record)
        screened.sort(key=lambda item: item["relevance_score"], reverse=True)
        screened = screened[: task["target_count"]]
        completed(
            state,
            "relevance_screener",
            f"Ranked {len(screened)} record(s)",
            4,
            {"evaluated_count": len(screened), "top_titles": [record["title"] for record in screened[:3]],
             "jev": {"configured": decisions.configured, "mode": decisions.mode,
                     "evaluated_count": jev_evaluated, "auto_eligible_count": jev_auto}},
        )
        return {"node": "relevance_screener", "records": screened, "errors": errors}

    def summarize(state: GraphState) -> GraphState:
        started(state, "literature_summarizer", "Creating evidence-bounded research briefs")
        errors = list(state.get("errors", []))
        prompt = prompt_for(prompts, "literature_summarizer")["body"]
        for record in state.get("records", []):
            try:
                summary = provider.summarize(record, state["task"]["topic"], prompt)
            except Exception as exc:
                summary = fallback(record, state["task"]["topic"])
                errors = errors_for({"errors": errors}, "literature_summarizer", exc)
            summary["relevance_reason"] = record["screening"]["relevance_reason"]
            summary["recommended_action"] = record["screening"]["recommended_action"]
            record["summary"] = summary
        completed(state, "literature_summarizer", f"Prepared {len(state.get('records', []))} research brief(s)", 5, {"brief_count": len(state.get("records", []))})
        return {"node": "literature_summarizer", "records": state.get("records", []), "errors": errors}

    def evidence_review(state: GraphState) -> GraphState:
        started(state, "evidence_reviewer", "Checking summary claims against supplied evidence")
        errors = list(state.get("errors", []))
        prompt = prompt_for(prompts, "evidence_reviewer")["body"]
        for record in state.get("records", []):
            jev_review = None
            if decisions.configured:
                try:
                    jev_review = decisions.review_evidence(state["run_id"], record, record["summary"])
                except Exception as exc:
                    errors = errors_for({"errors": errors}, "jev_evidence_reviewer", exc)
            if jev_review and not settings.jev_shadow_mode and jev_review["auto_eligible"]:
                review = jev_review
            else:
                try:
                    review = provider.review_evidence(record, record["summary"], prompt)
                except Exception as exc:
                    review = fallback_evidence_review(record, record["summary"])
                    errors = errors_for({"errors": errors}, "evidence_reviewer", exc)
            summary = record["summary"]
            summary["evidence_warnings"] = list(dict.fromkeys([*summary.get("evidence_warnings", []), *review["evidence_warnings"]]))
            summary["confidence"] = min(float(summary.get("confidence", 0.35)), float(review["confidence"]))
            summary["evidence_review_engine"] = review["engine"]
            if jev_review:
                summary["jev_evidence_review"] = {"mode": decisions.mode, "engine": jev_review["engine"],
                    "confidence": jev_review["decision_confidence"], "auto_eligible": jev_review["auto_eligible"],
                    "warnings": jev_review["evidence_warnings"]}
        completed(state, "evidence_reviewer", "Completed evidence review", 6, {"reviewed_count": len(state.get("records", []))})
        return {"node": "evidence_reviewer", "records": state.get("records", []), "errors": errors}

    def complete(state: GraphState) -> GraphState:
        started(state, "complete", "Persisting reviewed literature records")
        for record in state.get("records", []):
            database.add_paper(state["run_id"], record["canonical_id"], record)
        total_steps = 7 if state["task"].get("evidence_review") else 6
        database.save_run_artifact(
            state["run_id"],
            "result_manifest",
            {"paper_count": len(state.get("records", [])),
             "decision_count": len(database.list_decision_calls(state["run_id"])),
             "errors": state.get("errors", []), "completed_at": datetime.now(timezone.utc).isoformat()},
        )
        database.update_run(
            state["run_id"],
            status="completed",
            current_node="completed",
            paper_count=len(state.get("records", [])),
            progress=total_steps,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        database.add_run_event(state["run_id"], "complete", "completed", f"Saved {len(state.get('records', []))} paper record(s)", artifact_type="result_manifest")
        return {"node": "completed", "records": state.get("records", []), "errors": state.get("errors", [])}

    def should_review(state: GraphState) -> str:
        return "evidence_reviewer" if state["task"].get("evidence_review") else "complete"

    graph = StateGraph(GraphState)
    graph.add_node("plan", plan)
    graph.add_node("retrieve", retrieve)
    graph.add_node("dedupe", dedupe)
    graph.add_node("screen", screen)
    graph.add_node("summarize", summarize)
    graph.add_node("evidence_reviewer", evidence_review)
    graph.add_node("complete", complete)
    graph.set_entry_point("plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "dedupe")
    graph.add_edge("dedupe", "screen")
    graph.add_edge("screen", "summarize")
    graph.add_conditional_edges("summarize", should_review, {"evidence_reviewer": "evidence_reviewer", "complete": "complete"})
    graph.add_edge("evidence_reviewer", "complete")
    graph.add_edge("complete", END)
    return graph.compile()
