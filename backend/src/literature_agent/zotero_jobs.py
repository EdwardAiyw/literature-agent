"""Durable run-scoped Zotero imports. Never retrieve literature or send mail."""
from __future__ import annotations

import json
from dataclasses import replace

import httpx

from .config import Settings
from .db import Database, now
from .zotero import IMPORT_LOCK, ZoteroClient, ZoteroError, destination_for, task_settings


def remember_target(settings: Settings, database: Database, run_id: str, task: dict) -> None:
    if task.get("zotero_auto_import") and not database.get_run_artifact(run_id, "zotero_target"):
        if not task.get("zotero_collection_key"):
            return
        database.save_run_artifact(run_id, "zotero_target", {"destination": destination_for(task_settings(settings, task))})


def reserve_automatic(database: Database, run_id: str) -> dict | None:
    target = database.get_run_artifact(run_id, "zotero_target")
    if target and (database.get_run(run_id) or {}).get("status") == "completed":
        return database.reserve_zotero_batch(run_id, target["payload"]["destination"])
    return None


def process_batch(settings: Settings, database: Database, run_id: str, batch_id: str) -> dict:
    # Shared with manual imports and database replacement. No SQLite lock is
    # held across network I/O. Pending jobs also block maintenance/deletion.
    with IMPORT_LOCK:
        artifact = database.get_run_artifact(run_id, batch_id)
        if not artifact:
            raise ValueError("Import batch not found")
        batch = artifact["payload"]
        if batch["status"] not in {"queued", "running"}:
            return batch

        def save() -> None:
            batch["updated_at"] = now()
            batch["counts"] = {status: sum(r["status"] == status for r in batch["results"].values())
                               for status in ("imported", "existing", "failed", "skipped", "pending")}
            database.save_run_artifact(run_id, batch_id, batch)

        batch.update(status="running", error="")
        for paper_id, result in batch["results"].items():
            paper = database.get_paper(paper_id)
            if result["status"] == "pending" and (not paper or paper.get("review") == "ignore"):
                batch["results"][paper_id] = {"status": "skipped", "error": "论文已忽略或不存在。"}
        save()
        if not any(r["status"] == "pending" for r in batch["results"].values()):
            batch["status"] = "completed"
            save()
            return batch
        try:
            library_type, library_id, collection_key = json.loads(batch["destination"])
            if (library_type, library_id) != (settings.zotero_library_type, settings.zotero_library_id):
                raise ZoteroError("当前 Zotero 文献库与批次目标不同；恢复原文献库配置后再重试。")
            target_settings = replace(settings, zotero_collection_key=collection_key)
            with httpx.Client(timeout=30) as client:
                zotero = ZoteroClient(target_settings, client)
                zotero.prepare_batch()
                for paper_id, previous in batch["results"].items():
                    if previous["status"] != "pending":
                        continue
                    paper = database.get_paper(paper_id)
                    if not paper or paper.get("review") == "ignore":
                        batch["results"][paper_id] = {"status": "skipped", "error": "论文已忽略或不存在。"}
                        save()
                        continue
                    try:
                        result = zotero.import_paper(paper)
                    except ZoteroError as exc:
                        result = {"status": "failed", "error": str(exc)}
                        database.save_zotero_import(paper_id, batch["destination"], result)
                        batch["results"][paper_id] = result
                        # An uncertain write invalidates the index. End this
                        # attempt; retry starts with a fresh remote scan.
                        raise
                    database.save_zotero_import(paper_id, batch["destination"], result)
                    batch["results"][paper_id] = result
                    save()
        except Exception as exc:
            # Provider bodies/credentials are deliberately excluded.
            error = str(exc) if isinstance(exc, ZoteroError) else "导入遇到内部错误，请重试或检查服务日志。"
            batch["error"] = error
            for paper_id, result in batch["results"].items():
                if result["status"] == "pending":
                    batch["results"][paper_id] = {"status": "failed", "error": error}
            batch["status"] = "failed"
        else:
            batch["status"] = "completed"
        save()
        return batch
