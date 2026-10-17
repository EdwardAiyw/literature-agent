from dataclasses import replace
from email import policy
from email.parser import BytesParser

import pytest

from literature_agent import email
from literature_agent.config import Settings
from literature_agent.identifiers import export_identifiers, paper_identifier


@pytest.mark.parametrize("paper, expected", [
    ({"doi": "https://doi.org/10.1234/ABC", "pmid": "12345678"}, "10.1234/abc"),
    ({"external_ids": {"PubMed": "12345678"}}, "12345678"),
    ({"source": "arxiv", "source_id": "1234567v2", "official_url": "https://arxiv.org/abs/hep-th/1234567v2"}, "arXiv:hep-th/1234567"),
    ({"externalIds": {"ArXiv": "2401.12345v3"}}, "arXiv:2401.12345"),
    ({"isbn": "978-0-306-40615-7"}, "9780306406157"),
    ({"isbn": "0-8044-2957-X"}, "080442957X"),
    ({"bibcode": "2024ApJ...970..123A"}, "2024ApJ...970..123A"),
    ({"title": "DOI 10.1234/guessed", "source_id": "12345678"}, ""),
    ({"doi": "not a DOI", "isbn": "9780306406158"}, ""),
    ({"official_url": "https://evil.example/2401.12345"}, ""),
    ({"pmid": "123\n456", "arxiv_id": "bad", "bibcode": "bad"}, ""),
])
def test_only_real_supported_identifiers(paper, expected):
    assert paper_identifier(paper) == expected


def test_export_deduplicates_and_records_missing():
    result = export_identifiers([
        {"doi": "10.1234/ABC"}, {"doi": "doi:10.1234/abc"},
        {"title": "Missing"}, {"review": "ignore", "doi": "10.1234/skip"},
    ])
    assert result.text == "10.1234/abc\n"
    assert result.missing == ("Missing",)
    assert result.excluded == 1


def test_digest_attachment_survives_mime_round_trip(tmp_path, monkeypatch):
    sent = []
    class SMTP:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send_message(self, message): sent.append(message.as_bytes())
    monkeypatch.setattr(email, "_smtp", lambda _: SMTP())
    settings = Settings(root=tmp_path, smtp_host="test", smtp_from="test@example.org", smtp_starttls=False)
    message = email.render_digest({"topic": "研究"}, [{"doi": "10.1234/abc"}, {"title": "缺少编号"}])
    email.send_message(settings, "recipient@example.org", message, require_llm=False)
    mime = BytesParser(policy=policy.default).parsebytes(sent[0])
    attachments = list(mime.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "zotero-identifiers.txt"
    assert attachments[0].get_content_charset() == "utf-8"
    assert attachments[0].get_content().splitlines() == ["10.1234/abc"]
    assert "缺少编号" in mime.get_body(preferencelist=("plain",)).get_content()
    assert email.render_digest({}, [{"title": "Missing"}]).attachments == ()
