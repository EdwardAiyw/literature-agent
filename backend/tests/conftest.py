from dataclasses import replace

import pytest

from literature_agent import api


@pytest.fixture(autouse=True)
def offline_runtime(monkeypatch):
    """Keep repository tests deterministic even when a developer has live .env credentials."""
    monkeypatch.setattr(
        api,
        "settings",
        replace(
            api.settings,
            live=False,
            llm_api_key="",
            llm_model="",
            smtp_host="",
            smtp_from="",
            jev_enabled=False,
        ),
    )
