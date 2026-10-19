"""Desktop product controls for Obsidian; independent of search/mail scheduling."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import server_mode
from .obsidian import atomic_write, config_lock, safe_path, sync
from .system_ops import scheduler_status

TASK_NAME = "Literature Agent Obsidian Sync"


class ObsidianConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vault: str = Field(min_length=1, max_length=512)
    folder: str = Field(default="Literature Agent", min_length=1, max_length=100)
    mode: Literal["ssh", "local"] = "ssh"
    ssh_target: str = Field(default="", max_length=200, pattern=r"^[a-zA-Z0-9_.@:-]*$")
    database: str = Field(min_length=1, max_length=512)
    subscription_id: str = Field(min_length=1, max_length=100)
    since: str
    timezone: str = "Asia/Hong_Kong"

    @model_validator(mode="after")
    def validate_destination(self):
        vault = Path(self.vault)
        if not vault.is_absolute() or not (vault / ".obsidian").is_dir():
            raise ValueError("请选择已有的 Obsidian 文库（包含 .obsidian 目录）")
        if any(c in self.folder for c in '[]|#^<>:"?*\\\r\n'):
            raise ValueError("导出文件夹名称含不支持的字符")
        safe_path(vault, self.folder)
        if self.mode == "ssh" and (not self.ssh_target or self.ssh_target.startswith("-")):
            raise ValueError("请填写有效 SSH 地址，例如 user@server")
        date = datetime.fromisoformat(self.since)
        if date.tzinfo is None:
            raise ValueError("导入起始时间必须包含时区")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("归档时区无效") from exc
        return self


def supported():
    return os.name == "nt" and not server_mode()


def config_path(data_dir: Path):
    override = os.getenv("LITERATURE_AGENT_OBSIDIAN_CONFIG")
    return Path(override) if override else data_dir / "obsidian" / "config.json"


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default


def discover_vaults():
    path = Path(os.getenv("APPDATA", "")) / "obsidian" / "obsidian.json"
    try:
        config = read_json(path, {})
        return [{"path": v["path"], "name": Path(v["path"]).name, "open": bool(v.get("open"))}
                for v in config.get("vaults", {}).values() if (Path(v.get("path", "")) / ".obsidian").is_dir()]
    except (OSError, ValueError, TypeError, KeyError):
        return []


def status(data_dir: Path):
    if not supported():
        return {"supported": False, "config": None, "vaults": [], "last_sync": None, "scheduler": {"tasks": []}}
    path = config_path(data_dir)
    return {"supported": True, "config": read_json(path), "vaults": discover_vaults(),
            "last_sync": read_json(path.parent / "last-sync.json"), "scheduler": scheduler_status((TASK_NAME,))}


def save(data_dir: Path, config: ObsidianConfig):
    path = config_path(data_dir)
    with config_lock(path):
        atomic_write(path, config.model_dump_json(indent=2))


def schedule(data_dir: Path, action: str):
    path = config_path(data_dir)
    if action not in {"register", "disable"}:
        raise ValueError("Unsupported Obsidian schedule action")
    if action == "register" and not path.is_file():
        raise ValueError("请先保存 Obsidian 配置")
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
    script = root / "scripts" / "register-obsidian-sync.ps1"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                             "-Config", str(path), *(["-Unregister"] if action == "disable" else [])],
                            capture_output=True, text=True, timeout=60, check=False,
                            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "无法更新 Obsidian 自动同步任务")


def open_index(data_dir: Path):
    config = read_json(config_path(data_dir))
    if not config:
        raise ValueError("请先保存 Obsidian 配置")
    path = Path(config["vault"]) / config.get("folder", "Literature Agent") / "论文索引.md"
    if not path.is_file():
        raise ValueError("请先同步一次以生成论文索引")
    uri = "obsidian://open?path=" + quote(str(path.resolve()), safe="")
    os.startfile(uri)


def sync_now(data_dir: Path):
    path = config_path(data_dir)
    if not path.is_file():
        raise ValueError("请先保存 Obsidian 配置")
    try:
        return sync(path)
    except sqlite3.Error as exc:
        raise ValueError(f"无法读取本机文献数据库：{exc}") from exc
