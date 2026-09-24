from __future__ import annotations

import os
import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def bootstrap_path() -> Path:
    override = os.getenv("LITERATURE_AGENT_BOOTSTRAP", "")
    if override:
        return Path(override)
    local = os.getenv("LOCALAPPDATA", "")
    return Path(local) / "LiteratureAgent" / "bootstrap.json" if local else Path.home() / ".literature-agent" / "bootstrap.json"


def bootstrap_data_dir() -> Path | None:
    path = bootstrap_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("data_directory") if isinstance(payload, dict) else None
        return Path(value) if value else None
    except (OSError, ValueError, TypeError):
        return None


def save_bootstrap_data_dir(path: Path) -> None:
    target = bootstrap_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"data_directory": str(path.resolve())}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path = Path("data")
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
        bundled_root = Path(getattr(sys, "_MEIPASS")) / "backend" if getattr(sys, "frozen", False) else None
        project_root = root or bundled_root or Path(__file__).resolve().parents[2]
        load_dotenv(project_root / ".env")
        configured_data_dir = os.getenv("LITERATURE_AGENT_DATA_DIR", "")
        data_dir = Path(configured_data_dir) if configured_data_dir else (bootstrap_data_dir() or Path("data"))
        if not data_dir.is_absolute():
            data_dir = project_root / data_dir
        configured_db = os.getenv("LITERATURE_AGENT_DB", "")
        db = Path(configured_db) if configured_db else data_dir / "literature_agent_v2.db"
        if not db.is_absolute():
            db = (project_root / db) if configured_data_dir else data_dir / db.name
        return cls(
            root=project_root,
            data_dir=data_dir,
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


SECRET_FIELDS = {
    "llm_api_key": "LLM_API_KEY",
    "openalex_api_key": "OPENALEX_API_KEY",
    "semantic_scholar_api_key": "SEMANTIC_SCHOLAR_API_KEY",
    "pubmed_api_key": "PUBMED_API_KEY",
    "jev_api_key": "TYPESAFE_API_KEY",
    "smtp_password": "SMTP_PASSWORD",
}

SETTING_FIELDS = {
    "live", "llm_base_url", "llm_model", "pubmed_email",
    "source_cache_ttl_hours", "source_daily_request_budget",
    "jev_enabled", "jev_shadow_mode", "jev_model", "jev_timeout_seconds",
    "jev_auto_threshold", "jev_review_threshold", "jev_cache_ttl_hours",
    "smtp_host", "smtp_port", "smtp_username", "smtp_from",
    "smtp_starttls", "smtp_ssl", "famou_enabled",
}


class SecretStore(Protocol):
    def get(self, key: str) -> str: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class WindowsCredentialStore:
    """Small ctypes adapter for generic credentials owned by the current user."""

    service = "LiteratureAgent"

    def _target(self, key: str) -> str:
        return f"{self.service}/{key}"

    @staticmethod
    def _api():
        if os.name != "nt":
            raise RuntimeError("Windows Credential Manager is only available on Windows")
        import ctypes
        from ctypes import wintypes

        class Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", wintypes.LPVOID),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
            ]
        return ctypes, wintypes, Credential, ctypes.windll.advapi32

    def get(self, key: str) -> str:
        ctypes, _, Credential, advapi = self._api()
        pointer = ctypes.POINTER(Credential)()
        if not advapi.CredReadW(self._target(key), 1, 0, ctypes.byref(pointer)):
            return ""
        try:
            credential = pointer.contents
            if not credential.CredentialBlob or not credential.CredentialBlobSize:
                return ""
            raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            advapi.CredFree(pointer)

    def set(self, key: str, value: str) -> None:
        ctypes, _, Credential, advapi = self._api()
        raw = value.encode("utf-16-le")
        blob = (ctypes.c_byte * len(raw)).from_buffer_copy(raw)
        credential = Credential()
        credential.Type = 1
        credential.TargetName = self._target(key)
        credential.CredentialBlobSize = len(raw)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte))
        credential.Persist = 2
        credential.UserName = self.service
        if not advapi.CredWriteW(ctypes.byref(credential), 0):
            raise ctypes.WinError()

    def delete(self, key: str) -> None:
        _, _, _, advapi = self._api()
        if not advapi.CredDeleteW(self._target(key), 1, 0):
            import ctypes
            if ctypes.windll.kernel32.GetLastError() != 1168:
                raise ctypes.WinError()


class MemorySecretStore:
    """Non-persistent store for tests and non-Windows development."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def get(self, key: str) -> str:
        return self.values.get(key, "")

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class ConfigManager:
    """Owns persisted product settings and provides atomic runtime snapshots."""

    def __init__(self, base: Settings, secret_store: SecretStore | None = None) -> None:
        self.base = base
        self.data_dir = base.data_dir.resolve()
        self.path = self.data_dir / "settings.json"
        self.secret_store = secret_store or (WindowsCredentialStore() if os.name == "nt" else MemorySecretStore())
        self._lock = threading.RLock()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._values = self._read_values()
        self._settings = self._build()

    def _read_values(self) -> dict:
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError(f"Invalid settings file: {self.path}")
        result = {key: item for key, item in value.items() if key in SETTING_FIELDS}
        result["_cleared_secrets"] = [key for key in value.get("_cleared_secrets", []) if key in SECRET_FIELDS]
        return result

    def _build(self) -> Settings:
        from dataclasses import replace
        values = {key: value for key, value in self._values.items() if key in SETTING_FIELDS}
        cleared = set(self._values.get("_cleared_secrets", []))
        for field, env_name in SECRET_FIELDS.items():
            values[field] = "" if field in cleared else (self.secret_store.get(field) or os.getenv(env_name, "") or getattr(self.base, field))
        values["data_dir"] = self.data_dir
        values["db_path"] = self.data_dir / "literature_agent_v2.db"
        return replace(self.base, **values)

    def get(self) -> Settings:
        with self._lock:
            return self._settings

    def update(self, values: dict, secrets: dict[str, str | None] | None = None) -> Settings:
        unknown = set(values) - SETTING_FIELDS
        if unknown:
            raise ValueError(f"Unsupported setting(s): {', '.join(sorted(unknown))}")
        with self._lock:
            next_values = {**self._values, **values}
            cleared = set(next_values.get("_cleared_secrets", []))
            for key, value in (secrets or {}).items():
                if key not in SECRET_FIELDS:
                    raise ValueError(f"Unsupported secret: {key}")
                if value is None:
                    continue
                if value:
                    self.secret_store.set(key, value)
                    cleared.discard(key)
                else:
                    self.secret_store.delete(key)
                    cleared.add(key)
            next_values["_cleared_secrets"] = sorted(cleared)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(next_values, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
            self._values = next_values
            self._settings = self._build()
            return self._settings

    def public(self) -> dict:
        current = self.get()
        result = {key: getattr(current, key) for key in SETTING_FIELDS}
        result["data_dir"] = str(self.data_dir)
        result["secrets"] = {key: bool(getattr(current, key)) for key in SECRET_FIELDS}
        return result
