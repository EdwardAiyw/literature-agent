"""Zero-new-paper pause, one-off notice and restartable historical synthesis."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import html
import json
from typing import Callable

from .config import Settings
from .db import Database, now
from .email import DigestAttachment, DigestMessage, send_message
from .identifiers import export_identifiers
from .llm import ModelProvider


NODE = "subscription_closure"
SECTIONS = {"themes": "研究主题分类", "methods": "主要研究方法", "findings": "主要发现",
            "agreements_disagreements": "文献之间的联系与分歧", "gaps_next_steps": "研究空白与后续方向"}
INPUT_BUDGET = 18000


def should_pause(database: Database, run: dict, task: dict, papers: list[dict]) -> bool:
    if run.get("status") != "completed" or papers or task.get("sources") == ["fixture"]:
        return False
    retrieval = database.get_run_artifact(run["id"], "retrieval")
    manifest = database.get_run_artifact(run["id"], "result_manifest")
    if not retrieval or not manifest or manifest["payload"].get("errors"):
        return False
    diagnostics = retrieval["payload"].get("sources", {})
    return bool(task.get("sources")) and all(
        diagnostics.get(source, {}).get("status") in {"ok", "cached"} and not diagnostics[source].get("error")
        for source in task["sources"]
    )


def _message(subject: str, text: str, attachments: tuple[DigestAttachment, ...] = ()) -> DigestMessage:
    return DigestMessage(subject=subject, text=text,
                         html="<!doctype html><html><body><div style='white-space:pre-wrap;font-family:Arial,sans-serif;line-height:1.6'>"
                         + html.escape(text) + "</div></body></html>", attachments=attachments)


def pause_notice(job: dict) -> DigestMessage:
    sub = job["subscription"]
    requested = job["reason"] == "user_requested"
    label = "订阅已暂停" if requested else "订阅已自动暂停"
    reason = ("按用户要求暂停该订阅，并汇总历史成功推送的文献。" if requested else
              "本次取得的候选论文均已推送。" if job["reason"] == "all_delivered" else
              "本次正常检索和筛选后，没有符合要求的新增文献。")
    if job.get("source_warnings"):
        reason += "\n本次运行的来源或处理提示：\n" + "\n".join(job["source_warnings"])
    text = (f"{label}：{sub['name']}\n主题：{sub['topic']}\n暂停时间：{job['paused_at']}\n\n"
            f"{reason}\n后续每日检索与日报发送已暂停。此结果只反映当前检索范围与来源，不能证明整个领域没有新论文。\n\n"
            f"历史成功日报：{job['delivery_count']} 封；去重后文献：{len(job['papers'])} 篇；"
            f"历史缺失记录：{job['missing_papers']} 条。\n"
            "系统将汇总历次成功推送的全部可用文献，另发汇总邮件及完整报告；生成失败时可在订阅页面重试。\n\n"
            "恢复方式：进入“每日订阅”，编辑该订阅，勾选“启用每日自动执行”并保存。"
            "可以先调整主题、日期或来源。恢复后保留推送历史，继续排除已发文献。")
    return _message(f"[Literature Agent] {sub['topic']} · {label}", text)


def _pack(materials: list[dict]) -> list[list[dict]]:
    batches, batch, size = [], [], 2
    for material in materials:
        length = len(json.dumps(material, ensure_ascii=False)) + 2
        if length > INPUT_BUDGET:
            raise ValueError("Historical report material exceeds the input budget")
        if batch and size + length > INPUT_BUDGET:
            batches.append(batch)
            batch, size = [], 2
        batch.append(material)
        size += length
    if batch:
        batches.append(batch)
    return batches


def _materials(papers: list[dict]) -> list[dict]:
    materials = []
    for paper in papers:
        evidence = json.dumps({key: paper.get(key) for key in
                               ("title", "abstract", "summary", "published_date", "history_provenance")}, ensure_ascii=False)
        # Split unusually long abstracts/briefs without silently dropping evidence.
        for offset in range(0, len(evidence), 6000):
            materials.append({"refs": [paper["ref"]], "part": offset // 6000 + 1, "evidence": evidence[offset:offset + 6000]})
    return materials


def synthesize(settings: Settings, database: Database, job: dict) -> dict:
    papers = [p for p in job["papers"] if p.get("abstract") or p.get("summary")]
    if not papers:
        return {section: [] for section in SECTIONS}
    provider = ModelProvider(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    materials = _materials(papers)
    try:
        while True:
            batches = _pack(materials)
            outputs = []
            for batch in batches:
                refs = sorted({ref for material in batch for ref in material["refs"]})
                key = hashlib.sha256(json.dumps(batch, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                if key not in job["chunks"]:
                    job["chunks"][key] = provider.synthesize_history(job["subscription"]["topic"],
                        job["task"].get("output_language", "zh"), batch, refs)
                    database.save_run_artifact(job["run_id"], NODE, job)
                outputs.append({"refs": refs, "analysis": job["chunks"][key]})
            if len(outputs) == 1:
                return outputs[0]["analysis"]
            if len(outputs) >= len(materials):
                raise ValueError("Historical report reduction did not reduce the input")
            materials = outputs
    finally:
        if provider.client is not None:
            provider.client.close()


def report_text(job: dict, synthesis: dict) -> str:
    papers = job["papers"]
    abstract_count = sum(bool(p.get("abstract")) for p in papers)
    summary_only = sum(not p.get("abstract") and bool(p.get("summary")) for p in papers)
    lines = [f"# {job['subscription']['name']}：历史推送文献完整汇总", "",
             f"研究主题：{job['subscription']['topic']}", f"汇总截止：{job['paused_at']}",
             f"成功日报：{job['delivery_count']} 封；去重后文献：{len(papers)} 篇；合并重复推送：{job['duplicate_count']} 条。",
             f"推送时间范围：{job['first_sent_at'] or '无'} 至 {job['last_sent_at'] or '无'}。", "",
             "## 资料覆盖与限制", "",
             f"{abstract_count} 篇有原始摘要，{summary_only} 篇仅有已保存简报，"
             f"{len(papers) - abstract_count - summary_only} 篇仅有书目信息；历史缺失记录 {job['missing_papers']} 条。",
             f"{job['reconstructed_deliveries']} 封早期邮件通过历史运行或持久推送记录重建，已在逐篇条目标明。",
             "本报告依据系统实际保存的书目信息、摘要与简报生成，未读取论文全文。已保存简报属于二手材料，"
             "须结合原始摘要和证据提示核查；资料缺失处不推测。研究空白仅表示此文献集合中的不足，后续方向属于研究建议。", ""]
    if job["reason"] == "user_requested":
        lines.extend(["暂停原因：按用户要求暂停并汇总，不代表所有来源均已无新增文献。", ""])
    if job.get("source_warnings"):
        lines.extend(["本次运行的来源或处理提示：", *job["source_warnings"], ""])
    for section, label in SECTIONS.items():
        lines.extend([f"## {label}", ""])
        for point in synthesis[section]:
            lines.extend([point["text"] + " " + " ".join(f"[{ref}]" for ref in point["refs"]), ""])
        if not synthesis[section]:
            lines.extend(["可用资料不足，无法可靠归纳。", ""])
    lines.extend(["## 逐篇文献与完整参考清单", ""])
    for paper in papers:
        lines.extend([f"### [{paper['ref']}] {paper.get('title') or '未提供标题'}", "",
                      f"作者：{'；'.join(paper.get('authors') or []) or '未提供'}",
                      f"日期：{paper.get('published_date') or '未提供'}；期刊/出版物：{paper.get('venue') or '未提供'}",
                      f"DOI：{paper.get('doi') or '未提供'}；PMID：{paper.get('pmid') or '未提供'}；arXiv：{paper.get('arxiv_id') or '未提供'}",
                      f"原文：{paper.get('official_url') or '未提供'}", f"资料来源：{paper['history_provenance']}", ""])
        summary = paper.get("summary") or {}
        for field, label in (("research_problem", "研究问题"), ("method", "方法"), ("main_findings", "主要发现"),
                             ("limitations", "局限"), ("relevance_reason", "主题相关性"), ("research_use", "研究用途"),
                             ("evidence_warnings", "证据提示"), ("confidence", "简报置信度")):
            value = summary.get(field)
            if value is not None and value != "" and value != []:
                rendered = "；".join(str(v) for v in value) if isinstance(value, list) else str(value)
                lines.extend([f"{label}：{rendered}", ""])
        lines.extend(["原始摘要：" + (paper.get("abstract") or "未保存；请通过原文链接核查。"), ""])
    if not papers:
        lines.append("该订阅尚无成功推送的可用文献记录。")
    return "\n".join(lines)


def _send_once(settings: Settings, database: Database, job: dict, kind: str, message: DigestMessage,
               sender: Callable | None = None) -> dict:
    key = kind + "_delivery_id"
    delivery = database.get_delivery(job[key]) if job.get(key) else None
    if delivery and delivery["status"] == "sent":
        return delivery
    if not delivery:
        delivery = database.create_delivery(job["subscription"]["id"], job["run_id"], kind,
                                            job["subscription"]["recipient"], message.subject)
        job[key] = delivery["id"]
        database.save_run_artifact(job["run_id"], NODE, job)
    database.save_run_artifact(job["run_id"], "email_digest." + delivery["id"], asdict(message))
    try:
        (sender or send_message)(settings, delivery["recipient"], message)
    except Exception as exc:
        database.update_delivery(delivery["id"], status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    return database.update_delivery(delivery["id"], status="sent", sent_at=now(), error="")


def process_closure(settings: Settings, database: Database, run_id: str, sender: Callable | None = None) -> dict:
    job = database.transition_closure(run_id, {"queued"}, "running")
    if not job:
        artifact = database.get_run_artifact(run_id, NODE)
        return artifact["payload"] if artifact else {}
    try:
        _send_once(settings, database, job, "pause_notice", pause_notice(job), sender)
        if "report" not in job:
            analysis = synthesize(settings, database, job)
            job["report"] = report_text(job, analysis)
            job["analysis"] = analysis
            database.save_run_artifact(run_id, NODE, job)
        identifiers = export_identifiers(job["papers"])
        attachments = (DigestAttachment("literature-history-report.md", job["report"]),)
        if identifiers.identifiers:
            attachments += (DigestAttachment("zotero-identifiers.txt", identifiers.text),)
        message = _message(f"[Literature Agent] {job['subscription']['topic']} · 历史文献汇总（{len(job['papers'])} 篇）",
                           job["report"], attachments)
        _send_once(settings, database, job, "history_summary", message, sender)
        job.update(status="completed", error="")
    except Exception as exc:
        job.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    database.save_run_artifact(run_id, NODE, job)
    database.add_run_event(run_id, NODE, job["status"], job["error"] or "Historical report sent; subscription remains paused", NODE)
    return job
