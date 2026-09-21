from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import TypedDict

import httpx
from langgraph.graph import END, StateGraph

from .config import Settings
from .db import Database
from .llm import ModelProvider, fallback


class GraphState(TypedDict, total=False):
    task: dict
    run_id: str
    node: str
    records: list[dict]
    errors: list[str]


def fixture_records(topic: str) -> list[dict]:
    key = hashlib.sha1(topic.encode()).hexdigest()[:8]
    return [
        {"title": f"Evidence-grounded retrieval for {topic}", "authors": ["Fixture Author"], "abstract": f"This fixture record demonstrates retrieval and evidence evaluation for {topic}.", "published_date": str(date.today()), "source": "fixture", "source_id": f"fixture-{key}-1", "official_url": "https://example.org/paper-1", "open_access_url": "", "doi": "", "language": "en"},
        {"title": f"A review of methods related to {topic}", "authors": ["Fixture Researcher"], "abstract": f"This fixture record reviews methods, limitations, and evaluation settings related to {topic}.", "published_date": "2024-01-01", "source": "fixture", "source_id": f"fixture-{key}-2", "official_url": "https://example.org/paper-2", "open_access_url": "", "doi": "", "language": "en"},
    ]


def canonical(record: dict) -> str:
    if record.get("doi"):
        return "doi:" + record["doi"].lower().strip()
    if record.get("source_id"):
        return record["source"] + ":" + record["source_id"].lower().strip()
    return "title:" + re.sub(r"[^a-z0-9]+", "", record.get("title", "").lower())


def build_graph(settings: Settings, database: Database):
    provider = ModelProvider(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    def plan(state: GraphState) -> GraphState:
        database.update_run(state["run_id"], status="running", current_node="query_planner", started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
        task = state["task"]
        state["task"]["queries"] = [task["topic"], *task.get("research_questions", [])]
        return {"node": "query_planner", "task": state["task"], "errors": []}

    def retrieve(state: GraphState) -> GraphState:
        database.update_run(state["run_id"], current_node="retrieval")
        task = state["task"]
        records = fixture_records(task["topic"])
        if settings.live:
            try:
                response = httpx.get("https://api.openalex.org/works", params={"search": task["topic"], "per-page": task["target_count"]}, timeout=30)
                response.raise_for_status()
                records = [{"title": item.get("title", ""), "authors": [x.get("author", {}).get("display_name", "") for x in item.get("authorships", [])], "abstract": "", "published_date": item.get("publication_date", ""), "source": "openalex", "source_id": item.get("id", "").rsplit("/", 1)[-1], "official_url": item.get("doi") or item.get("id", ""), "open_access_url": (item.get("open_access") or {}).get("oa_url", "") or "", "doi": (item.get("doi") or "").replace("https://doi.org/", ""), "language": "unknown"} for item in response.json().get("results", [])]
            except Exception as exc:
                state.setdefault("errors", []).append(f"OpenAlex: {type(exc).__name__}: {exc}")
        return {"node": "retrieval", "records": records, "errors": state.get("errors", [])}

    def screen(state: GraphState) -> GraphState:
        database.update_run(state["run_id"], current_node="screening")
        topic = state["task"]["topic"].lower()
        seen: set[str] = set()
        records = []
        for record in state.get("records", []):
            cid = canonical(record)
            if cid in seen:
                continue
            seen.add(cid)
            text = f"{record.get('title', '')} {record.get('abstract', '')}".lower()
            score = 0.8 if any(token in text for token in topic.split()[:3]) else 0.35
            record["canonical_id"] = cid
            record["relevance_score"] = score
            record["priority"] = "P0" if score >= 0.7 else "P1" if score >= 0.4 else "P2"
            records.append(record)
        return {"node": "screening", "records": sorted(records, key=lambda item: item["relevance_score"], reverse=True)[: state["task"]["target_count"]], "errors": state.get("errors", [])}

    def summarize(state: GraphState) -> GraphState:
        database.update_run(state["run_id"], current_node="summarization")
        for record in state.get("records", []):
            try:
                record["summary"] = provider.summarize(record, state["task"]["topic"])
            except Exception as exc:
                state.setdefault("errors", []).append(f"LLM: {type(exc).__name__}: {exc}")
                record["summary"] = fallback(record, state["task"]["topic"])
            database.add_paper(state["run_id"], record["canonical_id"], record)
        database.update_run(state["run_id"], status="completed", current_node="completed", paper_count=len(state.get("records", [])), finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
        return {"node": "completed", "records": state.get("records", []), "errors": state.get("errors", [])}

    graph = StateGraph(GraphState)
    graph.add_node("plan", plan)
    graph.add_node("retrieve", retrieve)
    graph.add_node("screen", screen)
    graph.add_node("summarize", summarize)
    graph.set_entry_point("plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "screen")
    graph.add_edge("screen", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()
