from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    root: Path
    live: bool = False
    db_path: Path = Path("data/literature_agent_v2.db")
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    openalex_api_key: str = ""
    semantic_scholar_api_key: str = ""
    pubmed_api_key: str = ""
    pubmed_email: str = ""
    source_cache_ttl_hours: int = 24
    source_daily_request_budget: int = 200
    jev_enabled: bool = False
    jev_shadow_mode: bool = True
    jev_api_key: str = ""
    jev_model: str = "jev-1.13.0"
    jev_timeout_seconds: float = 15.0
    jev_auto_threshold: float = 0.82
    jev_review_threshold: float = 0.55
    jev_cache_ttl_hours: int = 168
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    famou_enabled: bool = False

    @classmethod
    def from_env(cls, root: Path | None = None) -> "Settings":
        project_root = root or Path(__file__).resolve().parents[2]
        load_dotenv(project_root / ".env")
        db = Path(os.getenv("LITERATURE_AGENT_DB", "data/literature_agent_v2.db"))
        if not db.is_absolute():
            db = project_root / db
        return cls(
            root=project_root,
            live=os.getenv("LITERATURE_AGENT_LIVE", "false").lower() in {"1", "true", "yes"},
            db_path=db,
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            openalex_api_key=os.getenv("OPENALEX_API_KEY", ""),
            semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""),
            pubmed_api_key=os.getenv("PUBMED_API_KEY", ""),
            pubmed_email=os.getenv("PUBMED_EMAIL", ""),
            source_cache_ttl_hours=max(1, int(os.getenv("SOURCE_CACHE_TTL_HOURS", "24"))),
            source_daily_request_budget=max(1, int(os.getenv("SOURCE_DAILY_REQUEST_BUDGET", "200"))),
            jev_enabled=os.getenv("JEV_ENABLED", "false").lower() in {"1", "true", "yes"},
            jev_shadow_mode=os.getenv("JEV_SHADOW_MODE", "true").lower() in {"1", "true", "yes"},
            jev_api_key=os.getenv("TYPESAFE_API_KEY", ""),
            jev_model=os.getenv("JEV_MODEL", "jev-1.13.0"),
            jev_timeout_seconds=max(1.0, float(os.getenv("JEV_TIMEOUT_SECONDS", "15"))),
            jev_auto_threshold=min(1.0, max(0.0, float(os.getenv("JEV_AUTO_THRESHOLD", "0.82")))),
            jev_review_threshold=min(1.0, max(0.0, float(os.getenv("JEV_REVIEW_THRESHOLD", "0.55")))),
            jev_cache_ttl_hours=max(1, int(os.getenv("JEV_CACHE_TTL_HOURS", "168"))),
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_username=os.getenv("SMTP_USERNAME", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            smtp_from=os.getenv("SMTP_FROM", ""),
            smtp_starttls=os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"},
            smtp_ssl=os.getenv("SMTP_SSL", "false").lower() in {"1", "true", "yes"},
            famou_enabled=os.getenv("FAMOU_ENABLED", "false").lower() in {"1", "true", "yes"},
        )
