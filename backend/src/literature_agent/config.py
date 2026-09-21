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
    db_path: Path = Path("data/literature_agent.db")
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    openalex_api_key: str = ""

    @classmethod
    def from_env(cls, root: Path | None = None) -> "Settings":
        project_root = root or Path(__file__).resolve().parents[2]
        load_dotenv(project_root / ".env")
        db = Path(os.getenv("LITERATURE_AGENT_DB", "data/literature_agent.db"))
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
        )
