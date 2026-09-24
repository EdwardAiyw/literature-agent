import httpx

from literature_agent.config import Settings
from literature_agent.sources import search_sources


def test_all_sources_are_normalized_and_partially_failure_tolerant(tmp_path):
    pubmed_xml = """
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation><PMID>12345</PMID><Article>
          <ArticleTitle>PubMed paper</ArticleTitle>
          <Abstract><AbstractText Label="METHODS">A method.</AbstractText></Abstract>
          <Journal><Title>Journal of Tests</Title><JournalIssue><PubDate><Year>2025</Year><Month>Jan</Month><Day>02</Day></PubDate></JournalIssue></Journal>
          <AuthorList><Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author></AuthorList>
          <Language>eng</Language>
        </Article></MedlineCitation>
        <PubmedData><ArticleIdList><ArticleId IdType="doi">10.1000/pubmed.1</ArticleId></ArticleIdList></PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    arxiv_xml = """
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry><id>http://arxiv.org/abs/2501.00001</id><title>arXiv paper</title>
        <published>2025-01-03T00:00:00Z</published><summary>An abstract.</summary>
        <author><name>Grace Hopper</name></author><arxiv:primary_category term="cs.AI" />
      </entry>
    </feed>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.openalex.org" in url:
            return httpx.Response(200, json={"results": [{"id": "https://openalex.org/W1", "title": "OpenAlex paper", "publication_date": "2025-01-01", "authorships": [{"author": {"display_name": "Alan Turing"}}], "doi": "https://doi.org/10.1000/shared", "abstract_inverted_index": {"Abstract": [0], "text": [1]}}]})
        if "api.crossref.org" in url:
            return httpx.Response(200, json={"message": {"items": [{"DOI": "10.1000/shared", "title": ["Crossref duplicate"], "author": [{"given": "K", "family": "Example"}], "published": {"date-parts": [[2025, 1, 4]]}, "container-title": ["Tests"], "URL": "https://doi.org/10.1000/shared"}]}})
        if "export.arxiv.org" in url:
            return httpx.Response(200, text=arxiv_xml)
        if "esearch.fcgi" in url:
            return httpx.Response(200, json={"esearchresult": {"idlist": ["12345"]}})
        if "efetch.fcgi" in url:
            return httpx.Response(200, text=pubmed_xml)
        return httpx.Response(500)

    settings = Settings(root=tmp_path, live=True)
    records, diagnostics = search_sources(
        ["openalex", "crossref", "arxiv", "pubmed"],
        ("agentic retrieval",),
        10,
        "2025-01-01",
        "2025-12-31",
        httpx.Client(transport=httpx.MockTransport(handler)),
        settings,
    )
    assert {item["source"] for item in records} == {"openalex", "arxiv", "pubmed", "crossref"}
    assert next(item for item in records if item["source"] == "pubmed")["doi"] == "10.1000/pubmed.1"
    assert diagnostics["openalex"]["status"] == "ok"
    assert diagnostics["pubmed"]["count"] == 1


def test_source_failure_is_reported_without_losing_other_results(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "api.openalex.org" in str(request.url):
            return httpx.Response(503, text="temporarily unavailable")
        if "api.crossref.org" in str(request.url):
            return httpx.Response(200, json={"message": {"items": [{"DOI": "10.1000/ok", "title": ["Available paper"], "published": {"date-parts": [[2024]]}}]}})
        return httpx.Response(200, text='<feed xmlns="http://www.w3.org/2005/Atom" />')

    records, diagnostics = search_sources(
        ["openalex", "crossref"],
        ("topic",),
        5,
        "",
        "",
        httpx.Client(transport=httpx.MockTransport(handler)),
        Settings(root=tmp_path, live=True),
    )
    assert diagnostics["openalex"]["status"] == "failed"
    assert diagnostics["crossref"]["status"] == "ok"
    assert records[0]["doi"] == "10.1000/ok"


def test_semantic_scholar_cache_and_global_budget(tmp_path):
    from literature_agent.db import Database
    calls = 0
    def handler(request):
        nonlocal calls; calls += 1
        return httpx.Response(200, json={"data":[{"paperId":"S2-1","title":"Semantic paper","year":2025,
            "authors":[{"authorId":"A1","name":"Ada"}],"externalIds":{"DOI":"10.1/s2"}}],"next":None})
    database = Database(tmp_path / "cache.db")
    settings = Settings(root=tmp_path, live=True, source_daily_request_budget=1)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    first, _ = search_sources(["semantic_scholar"], ("agents",), 1, "", "", client, settings, cache=database)
    second, diagnostics = search_sources(["semantic_scholar"], ("agents",), 1, "", "", client, settings, cache=database)
    assert first == second and calls == 1
    assert diagnostics["semantic_scholar"]["status"] == "cached"
    assert database.source_usage_total() == 1
    database.close()


def test_arxiv_uses_percent_encoded_field_query(tmp_path):
    seen_url = ""
    def handler(request):
        nonlocal seen_url
        seen_url = str(request.url)
        return httpx.Response(200, text='<feed xmlns="http://www.w3.org/2005/Atom" />')

    _, diagnostics = search_sources(
        ["arxiv"], ("agentic retrieval augmented generation",), 5, "", "",
        httpx.Client(transport=httpx.MockTransport(handler)),
        Settings(root=tmp_path, live=True, smtp_from="researcher@example.org"),
    )
    assert diagnostics["arxiv"]["status"] == "ok"
    assert "%20" in seen_url
    assert "+" not in seen_url.split("?", 1)[1]
    assert "all%3A%22agentic%22" in seen_url


def test_arxiv_uses_system_curl_after_transport_failure(monkeypatch, tmp_path):
    calls = []
    xml = b'<feed xmlns="http://www.w3.org/2005/Atom" />'
    monkeypatch.setattr("literature_agent.sources.shutil.which", lambda name: "curl.exe")
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"returncode": 0, "stdout": xml, "stderr": b""})()
    monkeypatch.setattr("literature_agent.sources.subprocess.run", run)
    def handler(request):
        raise httpx.ConnectError("certificate mismatch", request=request)

    _, diagnostics = search_sources(
        ["arxiv"], ("agentic RAG",), 2, "", "",
        httpx.Client(transport=httpx.MockTransport(handler)), Settings(root=tmp_path, live=True),
    )
    assert diagnostics["arxiv"]["status"] == "ok"
    assert diagnostics["arxiv"]["transport"] == "system_curl"
    assert diagnostics["arxiv"]["attempts"] == 1
    assert calls[0][1]["timeout"] == 35
    assert "%20" in calls[0][0][-1]


def test_arxiv_keeps_successful_results_when_a_later_query_fails(tmp_path):
    xml = """
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry><id>http://arxiv.org/abs/2501.00001</id><title>Agentic RAG</title>
        <published>2025-01-03T00:00:00Z</published><summary>An abstract.</summary>
      </entry>
    </feed>
    """
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, text=xml)
        return httpx.Response(406)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    from literature_agent.sources import ArxivSource
    source = ArxivSource(client)
    source._system_curl = lambda url, user_agent: (_ for _ in ()).throw(RuntimeError("timeout"))
    records = source.search(("agentic RAG", "RAG evaluation"), 2, "", "")
    assert len(records) == 1
    assert source.errors == ["RuntimeError: timeout"]


def test_semantic_scholar_retries_429(monkeypatch, tmp_path):
    calls = 0
    sleeps = []
    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"data": [], "next": None})
    monkeypatch.setattr("literature_agent.sources.time.sleep", sleeps.append)

    _, diagnostics = search_sources(
        ["semantic_scholar"], ("agents",), 1, "", "",
        httpx.Client(transport=httpx.MockTransport(handler)),
        Settings(root=tmp_path, live=True),
    )
    diagnostic = diagnostics["semantic_scholar"]
    assert calls == 2
    assert diagnostic["status"] == "ok"
    assert diagnostic["attempts"] == 2
    assert diagnostic["retry_count"] == 1
    assert diagnostic["final_http_status"] == 200


def test_semantic_scholar_retry_exhaustion_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr("literature_agent.sources.time.sleep", lambda _: None)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429)))
    _, diagnostics = search_sources(
        ["semantic_scholar"], ("agents",), 1, "", "", client, Settings(root=tmp_path, live=True)
    )
    diagnostic = diagnostics["semantic_scholar"]
    assert diagnostic["status"] == "failed"
    assert diagnostic["attempts"] == 4
    assert diagnostic["retry_count"] == 3
    assert diagnostic["final_http_status"] == 429
