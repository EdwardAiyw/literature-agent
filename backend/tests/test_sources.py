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
