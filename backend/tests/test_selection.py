from literature_agent.graph import select_diverse_records


def paper(title: str, source: str, score: float) -> dict:
    return {"title": title, "source": source, "relevance_score": score}


def test_selection_includes_a_second_qualified_source():
    records = [
        paper("A1", "crossref", 0.95),
        paper("A2", "crossref", 0.94),
        paper("A3", "crossref", 0.93),
        paper("A4", "crossref", 0.92),
        paper("A5", "crossref", 0.91),
        paper("B1", "arxiv", 0.80),
    ]
    selected, diagnostic = select_diverse_records(records, 5)
    assert len(selected) == 5
    assert {item["source"] for item in selected} == {"crossref", "arxiv"}
    assert diagnostic["diversity_required"] is True
    assert diagnostic["diversity_satisfied"] is True
    assert diagnostic["selected_source_counts"] == {"crossref": 4, "arxiv": 1}


def test_selection_does_not_force_a_low_relevance_source():
    records = [paper("A1", "crossref", 0.95), paper("A2", "crossref", 0.90), paper("B1", "arxiv", 0.54)]
    selected, diagnostic = select_diverse_records(records, 2)
    assert [item["title"] for item in selected] == ["A1", "A2"]
    assert diagnostic["diversity_required"] is False
    assert "Fewer than two sources" in diagnostic["diversity_reason"]
