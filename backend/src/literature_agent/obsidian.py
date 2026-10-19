"""One-way, repeatable export of sent digests to an existing Obsidian vault."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone as datetime_timezone
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from .paper_identity import matches, members, strong_ids
from .email import render_digest
from .journal_metrics import format_jif, with_metric_records

START = "<!-- literature-agent:start -->"
END = "<!-- literature-agent:end -->"


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Unsafe export path")
    if not path.resolve().is_relative_to(root.resolve()) or path.resolve() == root.resolve():
        raise ValueError("Export path escapes managed folder")
    return path


def managed_write(root: Path, relative: str, body: str, frontmatter: str = ""):
    path = safe_path(root, relative)
    block = f"{START}\n{body.rstrip()}\n{END}"
    if path.exists():
        original = path.read_text(encoding="utf-8")
        if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
            raise ValueError(f"Managed markers missing or ambiguous; preserved file: {path}")
        content = original[:original.index(START)] + block + original[original.index(END) + len(END):]
    else:
        content = frontmatter + block + "\n\n## 我的阅读笔记\n\n"
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        atomic_write(path, content)


def text(value) -> str:
    value = str(value if value is not None else "").replace(START, "").replace(END, "")
    return re.sub(r"([\\`*_{}\[\]<>|#])", r"\\\1", value)


def link(label, url):
    if urlparse(str(url)).scheme not in {"https", "http", "zotero"}:
        return ""
    return f"[{text(label)}](<{str(url).replace('>', '%3E').replace('<', '%3C').replace(chr(10), '').replace(chr(13), '')}>)"


def paper_body(paper):
    lines = [f"# {text(paper.get('title'))}", "", f"作者：{text('；'.join(paper.get('authors') or []))}",
             f"发表日期：{text(paper.get('published_date'))}", f"来源：{text(paper.get('source'))}",
             f"期刊/会议：{text(paper.get('venue') or (paper.get('journal_metric') or {}).get('journal'))}",
             f"DOI：{text(paper.get('doi') or '未提供')}", text(format_jif(paper)), ""]
    urls = [("原文", paper.get("official_url")), ("开放版本", paper.get("open_access_url"))]
    urls.append(("影响因子来源", (paper.get("journal_metric") or {}).get("source_url")))
    for identity in sorted(strong_ids(paper)):
        if identity.startswith("doi:"):
            urls.append(("DOI", "https://doi.org/" + quote(identity[4:], safe="/")))
    for imported in paper.get("obsidian_zotero", []):
        key = imported.get("item_key") or imported.get("key")
        destination = imported.get("destination", [])
        if key and len(destination) >= 2:
            library = "library" if destination[0] == "user" else "groups/" + quote(str(destination[1]), safe="")
            urls.append(("Zotero", f"zotero://select/{library}/items/{quote(str(key), safe='')}"))
    lines += [" · ".join(filter(None, (link(label, url) for label, url in urls if url))), ""]
    summary = dict(paper.get("summary") or {})
    if not summary.get("relevance_reason"):
        summary["relevance_reason"] = (paper.get("screening") or {}).get("relevance_reason")
    for key, label in [("research_problem", "研究问题"), ("method", "方法"), ("main_findings", "主要发现"),
                       ("limitations", "局限"), ("relevance_reason", "与研究主题的关系"), ("research_use", "研究用途"),
                       ("recommended_action", "建议"), ("confidence", "摘要置信度"), ("evidence_warnings", "证据提示")]:
        value = summary.get(key)
        if value is not None and value != "" and value != []:
            rendered = "\n".join("- " + text(v) for v in value) if isinstance(value, list) else text(value)
            lines.extend([f"## {label}", "", rendered, ""])
    if paper.get("abstract"):
        lines += ["## 原始摘要", "", text(paper["abstract"]), ""]
    return "\n".join(lines)


def prepare_email(delivery: dict, metrics: list[dict]):
    """Use a sent snapshot, or clearly reconstruct older mail with shared rendering."""
    if delivery.get("email_archive"):
        return {**delivery["email_archive"], "provenance": "发送时正文快照"}
    delivery["papers"] = [with_metric_records(p, metrics) if "journal_metric" not in p else p for p in delivery["papers"]]
    subscription = delivery.get("subscription") or {"topic": re.sub(r" · \d+ 篇文献$", "", delivery["subject"]).removeprefix("[Literature Agent] ")}
    return {**asdict(render_digest(subscription, delivery["papers"], delivery.get("diagnostics"), delivery.get("dedupe"))),
            "subject": delivery["subject"], "provenance": "按历史运行记录重建（原始邮件正文未留存，指标可能已更新）"}


def asset_write(root: Path, relative: str, content: str, state: dict):
    """Keep exact TXT content; refuse to replace an unrelated or edited asset."""
    path = safe_path(root, relative)
    hashes = state.setdefault("assets", {})
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if path.exists():
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        if current == checksum:
            hashes[relative] = checksum
            return
        if current != hashes.get(relative):
            raise ValueError(f"Attachment has personal changes; preserved file: {path}")
    atomic_write(path, content)
    hashes[relative] = checksum


def export_email(root: Path, folder: str, day: str, delivery: dict, archive: dict, state: dict):
    suffix = hashlib.sha256(delivery["id"].encode()).hexdigest()[:16]
    stem = f"{day} -- {suffix}"
    email_path = f"Emails/{stem}.md"
    plain_path = f"Attachments/{stem} -- email.txt"
    asset_write(root, plain_path, archive["text"], state)
    paths = [plain_path]
    lines = [f"# {text(archive['subject'])}", "", f"发送时间：{text(delivery['sent_at'])}",
             f"正文来源：{text(archive['provenance'])}", "", f"[[{folder}/{plain_path}|邮件正文 TXT]]", ""]
    for index, attachment in enumerate(archive.get("attachments") or []):
        # Original attachment names are labels only, never filesystem paths.
        path = f"Attachments/{stem} -- attachment-{index + 1}.txt"
        asset_write(root, path, attachment["text"], state)
        paths.append(path)
        lines.append(f"[[{folder}/{path}|{text(attachment['filename'])}]]")
    body = archive["text"].replace(START, "&lt;!-- literature-agent:start --&gt;").replace(END, "&lt;!-- literature-agent:end --&gt;")
    fence = "`" * max(3, 1 + max((len(m) for m in re.findall(r"`+", body)), default=0))
    lines += ["", "## 邮件正文", "", fence + "text", body, fence]
    managed_write(root, email_path, "\n".join(lines))
    return email_path, paths


def export_snapshot(snapshot, vault: Path, folder: str, state_path: Path, timezone="Asia/Hong_Kong"):
    vault = vault.resolve()
    if not (vault / ".obsidian").is_dir():
        raise ValueError("Choose an existing Obsidian vault (.obsidian directory required)")
    root = safe_path(vault, folder)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"papers": [], "days": {}}
    binding = str(root.resolve())
    if state.get("root", binding) != binding:
        raise ValueError("Use a new state file when changing vault or export folder")
    state["root"] = binding
    count = 0
    for delivery in snapshot["deliveries"]:
        day = datetime.fromisoformat(delivery["sent_at"].replace("Z", "+00:00")).astimezone(ZoneInfo(timezone)).date().isoformat()
        notes = []
        archive = prepare_email(delivery, snapshot.get("journal_metrics", []))
        email_path, attachments = export_email(root, folder, day, delivery, archive, state)
        for paper in delivery["papers"]:
            record = next((r for r in state["papers"] if matches(r["identity"], paper) or (r.get("paper_id") and r["paper_id"] == paper.get("id"))), None)
            if record is None:
                identity = sorted(strong_ids(paper)) or [paper.get("id") or json.dumps(members(paper), sort_keys=True)]
                suffix = hashlib.sha256("|".join(identity).encode()).hexdigest()[:16]
                title = re.sub(r'[<>:"/\\|?*\x00-\x1f\[\]#^]', " ", str(paper.get("title") or "Paper"))[:64].strip().rstrip(".")
                record = {"path": f"Papers/{title} -- {suffix}.md", "identity": paper, "paper_id": paper.get("id")}
                state["papers"].append(record)
            record["identity"] = {**members(paper)[0], "identity_members": members(record["identity"]) + members(paper)}
            # Deduplicate aliases so repeated exports do not grow state indefinitely.
            record["identity"]["identity_members"] = list({json.dumps(m, sort_keys=True): m for m in record["identity"]["identity_members"]}.values())
            metadata = {"title": paper.get("title", ""), "doi": paper.get("doi", ""), "tags": ["literature-agent/paper"]}
            frontmatter = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in metadata.items()) + "\n---\n\n"
            managed_write(root, record["path"], paper_body(paper), frontmatter)
            notes.append(record["path"])
            count += 1
        state["days"].setdefault(day, {})[delivery["id"]] = {"subject": delivery["subject"], "notes": notes, "run_id": delivery["run_id"], "email_path": email_path, "attachments": attachments}
    for day, deliveries in state["days"].items():
        lines = [f"# {day} 每日论文", ""]
        for delivery in deliveries.values():
            lines += [f"## {text(delivery['subject'])}", ""]
            if delivery.get("email_path"):
                lines += [f"[[{folder}/{delivery['email_path'][:-3]}|邮件正文与附件]]", ""]
            titles = {r["path"]: re.sub(r"[\[\]|\r\n]", " ", str(r["identity"].get("title", "Paper"))) for r in state["papers"]}
            lines += [f"- [[{folder}/{path[:-3]}|{titles[path]}]]" for path in delivery["notes"]] or ["本次没有新的合格论文。"]
            lines.append("")
        managed_write(root, f"Daily/{day}.md", "\n".join(lines))
    managed_write(root, "论文索引.md", "# Literature Agent\n\n已成功邮件推送的文献；按发送日期归档。\n\n" + "\n".join(f"- [[{folder}/Daily/{day}|{day}]]" for day in sorted(state["days"], reverse=True)))
    atomic_write(state_path, json.dumps(state, ensure_ascii=False, indent=2))
    return {"deliveries": len(snapshot["deliveries"]), "paper_visits": count, "unique_notes": len(state["papers"]), "days": len(state["days"])}


@contextmanager
def config_lock(config_path: Path):
    # OS releases this lock even if the process crashes. Keep one sync per config.
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(config_path.parent / "sync.lock", "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        lock.close()


def snapshot_script() -> Path:
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
    return root / "scripts" / "obsidian-snapshot.py"


def sync(config_path: Path):
    with config_lock(config_path):
        try:
            return _sync(config_path)
        except Exception as error:
            atomic_write(config_path.parent / "last-sync.json", json.dumps({"at": datetime.now().astimezone().isoformat(), "status": "error", "error": str(error)}, ensure_ascii=False, indent=2))
            raise


def _sync(config_path: Path):
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    since_date = datetime.fromisoformat(config["since"])
    if since_date.tzinfo is None:
        raise ValueError("since must include a UTC offset")
    since = since_date.astimezone(datetime_timezone.utc).isoformat()
    script = snapshot_script()
    if config.get("mode", "ssh") == "local":
        import runpy
        snapshot = runpy.run_path(str(script))["snapshot"](config["database"], config["subscription_id"], since)
    else:
        if not re.fullmatch(r"[a-zA-Z0-9_.@:-]+", config["ssh_target"]) or config["ssh_target"].startswith("-"):
            raise ValueError("Invalid SSH target")
        remote = shlex.join(["python3", "-", config["database"], config["subscription_id"], since])
        result = subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", config["ssh_target"], remote],
                                input=script.read_bytes(), capture_output=True, timeout=120, check=True,
                                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        snapshot = json.loads(result.stdout)
    root = str((Path(config["vault"]).resolve() / config.get("folder", "Literature Agent")).resolve())
    state_path = config_path.parent / "state.json"
    if state_path.exists() and json.loads(state_path.read_text(encoding="utf-8")).get("root") != root:
        state_path = config_path.parent / ("state-" + hashlib.sha256(root.encode()).hexdigest()[:16] + ".json")
    outcome = export_snapshot(snapshot, Path(config["vault"]), config.get("folder", "Literature Agent"), state_path, config.get("timezone", "Asia/Hong_Kong"))
    atomic_write(config_path.parent / "last-sync.json", json.dumps({"at": datetime.now().astimezone().isoformat(), "status": "ok", **outcome}, ensure_ascii=False, indent=2))
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(sync(args.config)))
    return 0


if __name__ == "__main__":
    main()
