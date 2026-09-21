import httpx

from literature_agent.llm import ModelProvider, fallback


def test_unconfigured_model_uses_explicit_fallback():
    result = ModelProvider("https://example.test/v1", "", "").summarize({"title": "Paper", "abstract": "Abstract"}, "topic")
    assert result["engine"] == "fallback"
    assert "not stated in source" in result["main_findings"]


def test_model_provider_parses_structured_response():
    class Transport(httpx.BaseTransport):
        def handle_request(self, request):
            payload = '{"research_problem":"问题","method":"方法","main_findings":["发现"],"limitations":["局限"],"relevance_reason":"相关","research_use":"精读","recommended_action":"read","confidence":0.9,"evidence_warnings":[]}'
            return httpx.Response(200, json={"choices": [{"message": {"content": payload}}]})

    client = httpx.Client(transport=Transport())
    result = ModelProvider("https://example.test/v1", "key", "model", client).summarize({"title": "Paper", "abstract": "Abstract"}, "topic")
    assert result["engine"] == "model"
    assert result["confidence"] == 0.9
