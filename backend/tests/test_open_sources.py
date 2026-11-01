import httpx
import pytest
from fastapi.testclient import TestClient

from literature_agent import api, sources
from literature_agent.config import Settings
from literature_agent.db import Database
from literature_agent.paper_identity import merge_records, strong_ids
from literature_agent.schemas import SubscriptionCreate, TaskCreate, TaskUpdate


PROVIDERS = ("doaj", "datacite", "hal", "europe_pmc")
DOI = "10.1234/shared"


@pytest.fixture(autouse=True)
def isolated_request_gates(monkeypatch):
    sources._REQUEST_GATES.clear()
    monkeypatch.setattr(sources.time, "sleep", lambda _: None)
    yield
    sources._REQUEST_GATES.clear()


def payload(provider, published="2025-02-15"):
    if provider == "doaj":
        return {"results": [{"id": "doaj-1", "bibjson": {
            "title": "A shared paper about machine learning", "abstract": "<p>Evidence &amp; results</p>",
            "author": [{"name": "Ada Lovelace"}], "year": published[:4], "month": "February",
            "identifier": [{"type": "doi", "id": DOI}, {"type": "pissn", "id": "1234-5678"}],
            "journal": {"title": "Test Journal", "language": ["EN"]},
            "link": [{"type": "fulltext", "url": "https://example.org/fulltext"}],
        }}]}
    if provider == "datacite":
        return {"data": [{"id": DOI, "attributes": {
            "doi": DOI.upper(), "titles": [{"title": "A shared paper about machine learning"}],
            "creators": [{"name": "Ada Lovelace"}], "types": {"resourceTypeGeneral": "Dissertation"},
            "descriptions": [{"descriptionType": "Abstract", "description": "<p>Evidence &amp; results</p>"}],
            "dates": [{"dateType": "Issued", "date": published}], "publicationYear": int(published[:4]),
            "url": "https://example.org/thesis", "rightsList": [{"rightsUri": "https://creativecommons.org/licenses/by/4.0/"}],
        }}]}
    if provider == "hal":
        return {"response": {"docs": [{
            "halId_s": "hal-1", "title_s": ["A shared paper about machine learning"],
            "authFullName_s": ["Ada Lovelace"], "abstract_s": ["<p>Evidence &amp; results</p>"],
            "producedDate_s": published, "doiId_s": DOI, "uri_s": "https://hal.science/hal-1v1",
            "fileMain_s": "https://hal.science/hal-1/document", "journalTitle_s": "Test Journal",
            "journalIssn_s": "1234-5678", "language_s": ["en"], "docType_s": "ART", "arxivId_s": "2502.12345",
        }]}}
    return {"resultList": {"result": [{
        "id": "12345", "source": "MED", "pmid": "12345", "doi": DOI,
        "title": "A shared paper about machine learning", "abstractText": "<p>Evidence &amp; results</p>",
        "authorList": {"author": [{"fullName": "Ada Lovelace"}]}, "firstPublicationDate": published,
        "journalInfo": {"journal": {"title": "Test Journal", "issn": "1234-5678"}},
        "fullTextUrlList": {"fullTextUrl": [{"availabilityCode": "OA", "url": "https://example.org/pmc"}]},
    }]}}


@pytest.mark.parametrize("provider", PROVIDERS)
def test_open_sources_preserve_metadata_and_apply_date_filters(tmp_path, provider):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload(provider))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        records, diagnostics = sources.search_sources([provider], ("machine learning",), 2,
            "2025-02-01", "2025-02-28", client, Settings(root=tmp_path))
        outside, _ = sources.search_sources([provider], ("machine learning",), 2,
            "2026-01-01", "2026-12-31", client, Settings(root=tmp_path))
    assert outside == []
    record = records[0]
    assert record["doi"] == DOI
    assert record["authors"] == ["Ada Lovelace"]
    assert record["abstract"] == "Evidence & results"
    assert record["official_url"].startswith("https://")
    assert record["open_access_url"].startswith("https://")
    assert diagnostics[provider]["attempts"] == 1
    assert diagnostics[provider]["status"] == "ok"
    assert "2025" in str(requests[0].url)
    if provider == "doaj":
        assert record["published_date"] == "2025-02"
        assert record["date_unknown"] is True
        assert "bibjson.year" in str(requests[0].url)
    elif provider == "datacite":
        assert "types.resourceTypeGeneral" in requests[0].url.params["query"]
        assert requests[0].url.params["page[size]"] == "2"
    elif provider == "hal":
        assert record["arxiv_id"] == "2502.12345"
        assert len(requests[0].url.params.get_list("fq")) == 2
    else:
        assert record["pmid"] == "12345"
        assert record["source_id"] == "MED:12345"
        assert requests[0].url.params["resultType"] == "core"


def test_new_sources_merge_with_existing_doi_and_pmid_identities(tmp_path):
    papers = [{"source": "pubmed", "source_id": "12345", "pmid": "12345"}]
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload("europe_pmc")))) as client:
        papers += sources.build_sources(client, Settings(root=tmp_path))["europe_pmc"].search(("topic",), 1, "", "")
    for provider in PROVIDERS[:-1]:
        with httpx.Client(transport=httpx.MockTransport(lambda request, p=provider: httpx.Response(200, json=payload(p)))) as client:
            papers += sources.build_sources(client, Settings(root=tmp_path))[provider].search(("topic",), 1, "", "")
    merged = merge_records(papers)
    assert len(merged) == 1
    assert merged[0]["doi"] == DOI
    assert {"doi:" + DOI, "pmid:12345", "arxiv:2502.12345"} <= strong_ids(merged[0])
    assert {p["source"] for p in merged[0]["identity_members"]} == {"pubmed", *PROVIDERS}


@pytest.mark.parametrize("provider", PROVIDERS)
def test_new_sources_keep_partial_results_cache_and_count_actual_attempts(tmp_path, provider):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 2:
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json=payload(provider))

    database = Database(tmp_path / "cache.db")
    try:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            settings = Settings(root=tmp_path, source_daily_request_budget=2)
            first, diagnostics = sources.search_sources([provider], ("first", "second", "third"), 1,
                "", "", client, settings, cache=database)
            second, cached_diagnostics = sources.search_sources([provider], ("first", "second", "third"), 1,
                "", "", client, settings, cache=database)
        assert len(first) == 1 and first == second
        assert diagnostics[provider]["status"] == "partial"
        assert diagnostics[provider]["rate_limited"] is True
        assert diagnostics[provider]["attempts"] == diagnostics[provider]["requests_reserved"] == 2
        assert cached_diagnostics[provider]["query_cache_hits"] == 1
        assert cached_diagnostics[provider]["attempts"] == 0
        assert len(calls) == database.source_usage_total() == 2
    finally:
        database.close()


@pytest.mark.parametrize("provider", PROVIDERS)
def test_new_sources_whole_search_cache_and_budget_exhaustion(tmp_path, provider):
    calls = []
    database = Database(tmp_path / "budget.db")
    try:
        with httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200, json=payload(provider)))) as client:
            settings = Settings(root=tmp_path, source_daily_request_budget=1)
            records, _ = sources.search_sources([provider], ("topic",), 1, "", "", client, settings, cache=database)
            cached, diagnostic = sources.search_sources([provider], ("topic",), 1, "", "", client, settings, cache=database)
            _, blocked = sources.search_sources([provider], ("different topic",), 1, "", "", client, settings, cache=database)
        assert records == cached
        assert diagnostic[provider]["status"] == "cached"
        assert len(calls) == database.source_usage_total() == 1
        assert blocked[provider]["status"] == "failed"
        assert "budget exhausted" in blocked[provider]["error"]
    finally:
        database.close()


def test_datacite_excludes_non_literature_and_never_infers_open_access(tmp_path):
    data = payload("datacite")
    article = data["data"][0]["attributes"]
    article.pop("rightsList")
    article["dates"] = [{"dateType": "Created", "date": "2026-10-01"}]
    data["data"].append({"id": "10.1234/data", "attributes": {"types": {"resourceTypeGeneral": "Dataset"}}})
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))) as client:
        records = sources.DataCiteSource(client).search(("topic",), 10, "2025-06-01", "2025-12-31")
    assert len(records) == 1
    assert records[0]["published_date"] == "2025"
    assert records[0]["date_unknown"] is True
    assert records[0]["open_access_url"] == ""


@pytest.mark.parametrize("value,start,end,included,unknown", [
    ("2025", "2025-06-01", "2025-06-30", True, True),
    ("2024", "2025-01-01", "", False, False),
    ("2025-02", "2025-03-01", "", False, False),
    ("2025-02", "", "2025-01-31", False, False),
    ("2025-02", "2025-02-28", "2025-03-01", True, True),
    ("2025-02-15", "2025-02-01", "2025-02-28", True, False),
    ("", "2025-01-01", "", True, True),
    ("2025-13", "2025-01-01", "", True, True),
])
def test_partial_publication_dates_keep_original_precision(value, start, end, included, unknown):
    assert sources._date_status(value, start, end) == (included, unknown)


def test_api_catalogue_and_task_subscription_validation_include_new_sources():
    with TestClient(api.app) as client:
        catalogue = {item["id"]: item for item in client.get("/api/settings").json()["sources"]}
    assert len([item for item in catalogue.values() if item["live"]]) == 11
    for provider in PROVIDERS:
        assert catalogue[provider]["requires_credentials"] is False
        assert provider in TaskCreate(name="Test", topic="topic").sources
        assert TaskUpdate(sources=[provider]).sources == [provider]
    subscription = SubscriptionCreate(name="Test", topic="topic", recipient="reader@example.org", schedule_time="09:00", target_count=5)
    assert subscription.sources == sources.DEFAULT_SOURCES
