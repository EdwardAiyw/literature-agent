from literature_agent.email import render_digest


def test_digest_contains_traceable_metadata_and_diagnostics():
    message = render_digest(
        {"topic": "agentic retrieval"},
        [{
            "title": "A paper",
            "authors": ["Author"],
            "source": "openalex",
            "published_date": "2026-01-01",
            "doi": "10.1000/example",
            "official_url": "https://example.org/paper",
            "summary": {"research_problem": "A problem", "main_findings": ["A finding"], "relevance_reason": "On topic"},
        }],
        {"openalex": {"status": "ok", "count": 1, "error": ""}},
    )
    assert "10.1000/example" in message.text
    assert "https://example.org/paper" in message.html
    assert "openalex" in message.text
