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
import tempfile
from datetime import datetime, timezone as datetime_timezone
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from .paper_identity import matches, members, strong_ids

START = "<!-- literature-agent:start -->"
END = "<!-- literature-agent:end -->"


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
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
    value = str(value or "").replace(START, "").replace(END, "")
    return re.sub(r"([\\`*_{}\[\]<>|#])", r"\\\1", value)


def link(label, url):
    if urlparse(str(url)).scheme not in {"https", "http", "zotero"}:
        return ""
    return f"[{text(label)}](<{str(url).replace('>', '%3E').replace('<', '%3C').replace(chr(10), '').replace(chr(13), '')}>)"


def paper_body(paper):
    lines = [f"# {text(paper.get('title'))}", "", f"作者：{text('；'.join(paper.get('authors') or []))}",
             f"发表日期：{text(paper.get('published_date'))}", f"来源：{text(paper.get('source'))}",
             f"期刊/会议：{text(paper.get('venue'))}", ""]
    urls = [("原文", paper.get("official_url")), ("开放版本", paper.get("open_access_url"))]
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
    summary = paper.get("summary") or {}
    for key, label in [("research_problem", "研究问题"), ("method", "方法"), ("main_findings", "主要发现"),
                       ("limitations", "局限"), ("relevance_reason", "与研究主题的关系"), ("research_use", "研究用途"),
                       ("recommended_action", "建议"), ("confidence", "摘要置信度"), ("evidence_warnings", "证据提示")]:
        value = summary.get(key)
        if value:
            rendered = "\n".join("- " + text(v) for v in value) if isinstance(value, list) else text(value)
            lines.extend([f"## {label}", "", rendered, ""])
    if paper.get("abstract"):
        lines += ["## 原始摘要", "", text(paper["abstract"]), ""]
    return "\n".join(lines)


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
        state["days"].setdefault(day, {})[delivery["id"]] = {"subject": delivery["subject"], "notes": notes, "run_id": delivery["run_id"]}
    for day, deliveries in state["days"].items():
        lines = [f"# {day} 每日论文", ""]
        for delivery in deliveries.values():
            lines += [f"## {text(delivery['subject'])}", ""]
            titles = {r["path"]: re.sub(r"[\[\]|\r\n]", " ", str(r["identity"].get("title", "Paper"))) for r in state["papers"]}
            lines += [f"- [[{folder}/{path[:-3]}|{titles[path]}]]" for path in delivery["notes"]] or ["本次没有新的合格论文。"]
            lines.append("")
        managed_write(root, f"Daily/{day}.md", "\n".join(lines))
    managed_write(root, "论文索引.md", "# Literature Agent\n\n已成功邮件推送的文献；按发送日期归档。\n\n" + "\n".join(f"- [[{folder}/Daily/{day}|{day}]]" for day in sorted(state["days"], reverse=True)))
    atomic_write(state_path, json.dumps(state, ensure_ascii=False, indent=2))
    return {"deliveries": len(snapshot["deliveries"]), "paper_visits": count, "unique_notes": len(state["papers"]), "days": len(state["days"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    state_path = args.config.parent / "state.json"
    # OS releases this lock even if the process crashes. Keep one sync per config.
    lock = open(args.config.parent / "sync.lock", "a+b")
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
        since_date = datetime.fromisoformat(config["since"])
        if since_date.tzinfo is None:
            raise ValueError("since must include a UTC offset")
        since = since_date.astimezone(datetime_timezone.utc).isoformat()
        if not re.fullmatch(r"[a-zA-Z0-9_.@:-]+", config["ssh_target"]) or config["ssh_target"].startswith("-"):
            raise ValueError("Invalid SSH target")
        remote = shlex.join(["python3", "-", config["database"], config["subscription_id"], since])
        script = Path(__file__).resolve().parents[3] / "scripts" / "obsidian-snapshot.py"
        result = subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", config["ssh_target"], remote],
                                input=script.read_bytes(), capture_output=True, timeout=120, check=True)
        outcome = export_snapshot(json.loads(result.stdout), Path(config["vault"]), config.get("folder", "Literature Agent"), state_path, config.get("timezone", "Asia/Hong_Kong"))
        atomic_write(args.config.parent / "last-sync.json", json.dumps({"at": datetime.now().astimezone().isoformat(), "status": "ok", **outcome}, ensure_ascii=False, indent=2))
        print(json.dumps(outcome))
    except Exception as error:
        atomic_write(args.config.parent / "last-sync.json", json.dumps({"at": datetime.now().astimezone().isoformat(), "status": "error", "error": str(error)}, ensure_ascii=False, indent=2))
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    main()
