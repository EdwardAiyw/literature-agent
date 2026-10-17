from __future__ import annotations

import html
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from .config import Settings
from .identifiers import export_identifiers
from .journal_metrics import format_jif


@dataclass(frozen=True)
class DigestAttachment:
    filename: str
    text: str


@dataclass(frozen=True)
class DigestMessage:
    subject: str
    html: str
    text: str
    attachments: tuple[DigestAttachment, ...] = ()


def _clean(value: Any) -> str:
    return html.escape(str(value or ""))


def _summary_text(paper: dict) -> str:
    summary = paper.get("summary") or {}
    problem = summary.get("research_problem") or paper.get("abstract") or "未提供"
    findings = summary.get("main_findings") or []
    if isinstance(findings, list):
        findings_text = "；".join(str(item) for item in findings)
    else:
        findings_text = str(findings)
    reason = summary.get("relevance_reason") or paper.get("screening", {}).get("relevance_reason") or ""
    return f"研究问题：{problem}\n主要发现：{findings_text}\n推荐理由：{reason}"


def render_digest(subscription: dict, papers: list[dict], diagnostics: dict[str, dict] | None = None) -> DigestMessage:
    topic = subscription.get("topic", "文献订阅")
    subject = f"[Literature Agent] {topic} · {len(papers)} 篇文献"
    lines = [f"Literature Agent 日报", f"主题：{topic}", f"论文数量：{len(papers)}", ""]
    cards: list[str] = []
    if not papers:
        notice = "本次没有找到符合相关性要求的文献。请查看来源诊断、检索式和日期范围后重试。"
        lines.extend([notice, ""])
        cards.append(f"<p>{notice}</p>")
    for index, paper in enumerate(papers, start=1):
        authors = ", ".join(paper.get("authors") or [])
        doi = paper.get("doi") or "未提供"
        url = paper.get("official_url") or ""
        summary = _summary_text(paper)
        journal = paper.get("venue") or (paper.get("journal_metric") or {}).get("journal") or "未提供"
        jif = format_jif(paper)
        lines.extend([
            f"{index}. {paper.get('title', 'Untitled')}",
            f"作者：{authors or '未提供'} | 来源：{paper.get('source', '')} | 日期：{paper.get('published_date', '')}",
            f"DOI：{doi}",
            f"期刊/出版物：{journal}",
            jif,
            f"原文：{url}",
            summary,
            "",
        ])
        cards.append(
            "<article style='border-top:1px solid #d9d9d9;padding:18px 0'>"
            f"<h2 style='font-size:17px;margin:0 0 8px'>{index}. {_clean(paper.get('title', 'Untitled'))}</h2>"
            f"<p style='color:#555;margin:4px 0'>作者：{_clean(authors or '未提供')} · 来源：{_clean(paper.get('source', ''))} · 日期：{_clean(paper.get('published_date', ''))}</p>"
            f"<p style='margin:8px 0'>DOI：{_clean(doi)}<br>原文：<a href='{_clean(url)}'>{_clean(url or '未提供')}</a></p>"
            f"<p>期刊/出版物：{_clean(journal)}<br>{_clean(jif)}</p>"
            f"<p style='white-space:pre-line;line-height:1.55'>{_clean(summary)}</p>"
            "</article>"
        )
    if diagnostics:
        lines.extend(["来源诊断："])
        for source, diagnostic in diagnostics.items():
            lines.append(f"- {source}: {diagnostic.get('status', '')}, {diagnostic.get('count', 0)} 条{('，' + diagnostic.get('error')) if diagnostic.get('error') else ''}")
    exported = export_identifiers(papers)
    attachment_notice = (f"Zotero 标识符：{len(exported.identifiers)} 个（已去重）。"
                         "下载附件后，将全部内容粘贴到 Zotero 的“通过标识符添加条目”窗口。"
                         "请先选中目标集合；已自动导入的条目无需再次粘贴。")
    if not exported.identifiers:
        attachment_notice = "本次没有可用的 Zotero 标识符，因此未附加标识符文件。"
    if exported.missing:
        attachment_notice += f"\n{len(exported.missing)} 篇缺少可靠标识符：\n" + "\n".join(exported.missing)
    lines.extend(["", attachment_notice])
    cards.append(f"<p style='white-space:pre-line'>{_clean(attachment_notice)}</p>")
    text = "\n".join(lines)
    html_body = (
        "<!doctype html><html><body style='font-family:Arial,sans-serif;color:#222;max-width:780px;margin:32px auto'>"
        f"<h1>Literature Agent 日报</h1><p>主题：{_clean(topic)} · 论文数量：{len(papers)}</p>"
        f"{''.join(cards)}"
        "</body></html>"
    )
    attachments = (DigestAttachment("zotero-identifiers.txt", exported.text),) if exported.identifiers else ()
    return DigestMessage(subject=subject, html=html_body, text=text, attachments=attachments)


def _smtp(settings: Settings):
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP_HOST and SMTP_FROM must be configured")
    if settings.smtp_ssl:
        return smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30)
    return smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)


def send_message(settings: Settings, recipient: str, message: DigestMessage, require_llm: bool = True) -> None:
    if require_llm and (not settings.llm_api_key or not settings.llm_model):
        raise RuntimeError("LLM_API_KEY and LLM_MODEL must be configured for the daily digest")
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP_HOST and SMTP_FROM must be configured")
    email = EmailMessage()
    email["Subject"] = message.subject
    email["From"] = formataddr(("Literature Agent", settings.smtp_from))
    email["To"] = recipient
    email.set_content(message.text)
    email.add_alternative(message.html, subtype="html")
    for attachment in message.attachments:
        email.add_attachment(attachment.text, subtype="plain", charset="utf-8", filename=attachment.filename)
    with _smtp(settings) as server:
        if settings.smtp_starttls and not settings.smtp_ssl:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(email)


def send_test_message(settings: Settings, recipient: str) -> None:
    send_message(settings, recipient, DigestMessage(
        subject="[Literature Agent] SMTP test",
        text="Literature Agent SMTP 配置测试成功。",
        html="<p>Literature Agent SMTP 配置测试成功。</p>",
    ), require_llm=False)
