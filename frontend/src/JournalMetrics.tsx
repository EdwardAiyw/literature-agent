import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "/api";
type Metric = { journal: string; year: number; jif: string; source: string; source_url: string; matched_by: string; source_kind?: string; fetched_at?: string };
type Status = { records: number; latest_year: number | null; updated_at: string | null; auto_enabled?: boolean; cached_journals?: number; matched_journals?: number };

export function JournalMetricsDiagnostics({ stats }: { stats?: Record<string, unknown> }) {
  if (!stats?.enabled) return null;
  return <div className="journal-metric" role="status">
    <strong>影响因子查询</strong>
    {stats.error ? <span>本次查询未完成，已有指标仍可展示，文献照常推送。</span> : <span>
      已匹配 {Number(stats.matched) || 0} 篇 · 暂未查到 {Number(stats.not_found) || 0} 篇 · 信息不足 {Number(stats.insufficient_metadata) || 0} 篇 · 不适用 {Number(stats.not_applicable) || 0} 篇 · 指标冲突 {Number(stats.conflict) || 0} 篇 · 查询失败 {Number(stats.lookup_failed) || 0} 本期刊
      {!!stats.timed_out && " · 已达查询时间上限，文献照常推送"}
    </span>}
  </div>;
}

export function JournalMetric({ paper }: { paper: { source: string; venue?: string; venue_type?: string; journal_metric?: Metric | null; journal_metric_status?: string } }) {
  const metric = paper.journal_metric;
  const journalType = ["journal", "journal-article"].includes(paper.venue_type || "");
  const preprint = paper.source === "arxiv" || ["arXiv", "arXiv (Cornell University)"].includes(paper.venue || "");
  const applicable = (!preprint || journalType) && !["repository", "conference", "proceedings-article", "book", "book-chapter", "posted-content"].includes(paper.venue_type || "");
  return <div className="journal-metric">
    <span>期刊/出版物：{paper.venue || metric?.journal || "未提供"}</span>
    {!applicable ? <span>期刊影响因子：不适用（预印本或非期刊文献）</span> : metric ? <>
      <span>期刊影响因子 JIF：<strong>{metric.jif}</strong> · {metric.year}</span>
      <span>来源：{metric.source} · {metric.source_kind === "publisher" ? "官网公布" : "用户导入"} · ISSN 匹配{metric.source_url && /^https?:\/\//.test(metric.source_url) && <> · <a href={metric.source_url} target="_blank" rel="noreferrer">来源链接</a></>}</span>
      {metric.fetched_at && <span>获取时间：{new Date(metric.fetched_at).toLocaleString()}</span>}
    </> : <span>期刊影响因子：{paper.journal_metric_status === "insufficient_metadata" ? "期刊信息不足" : "暂未查到"}</span>}
  </div>;
}

export default function JournalMetricsSettings({ onImported }: { onImported: () => void }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [source, setSource] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = async (signal?: AbortSignal) => {
    const response = await fetch(`${API}/journal-metrics`, { signal });
    if (!response.ok) throw new Error(await response.text());
    const data: Status = await response.json();
    if (!signal?.aborted) setStatus(data);
  };
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch((error) => { if (!controller.signal.aborted) setError(String(error)); });
    return () => controller.abort();
  }, []);
  const upload = async () => {
    if (!file || !source.trim()) { setError("请选择指标 CSV 并填写数据来源。"); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      if (file.size > 15_000_000) throw new Error("CSV 不能超过 15 MB。");
      const response = await fetch(`${API}/journal-metrics/import`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv: await file.text(), source, source_url: sourceUrl.trim() }) });
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json();
      await load();
      setNotice(`已导入 ${result.imported} 条 ISSN/年份指标记录；返回工作台可查看匹配结果。`);
      onImported();
    } catch (error) { setError(String(error)); }
    finally { setBusy(false); }
  };
  const toggleAuto = async (enabled: boolean) => {
    const previous = status;
    let saved = false;
    setStatus((current) => current ? { ...current, auto_enabled: enabled } : current);
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(`${API}/settings/journal_metrics`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ journal_metrics_auto: enabled }) });
      if (!response.ok) throw new Error(await response.text());
      saved = true;
      await load();
      setNotice(enabled ? "已开启：下次运行会自动查询影响因子并随文献推送。" : "已关闭自动查询；已有指标仍可展示。");
    } catch (error) { if (!saved) setStatus(previous); setError(String(error)); }
    finally { setBusy(false); }
  };
  return <div className="settings-section">
    <div className="settings-title"><div /><div><strong>期刊影响因子（JIF）</strong><span>检索后自动查询期刊官网，随每日邮件附上数值、指标年份和来源。</span></div><span className={`config-state ${status?.records ? "ready" : "missing"}`}>{status ? `${status.records} 条记录` : "读取中"}</span></div>
    <label className="check-field"><input type="checkbox" checked={status?.auto_enabled ?? true} disabled={busy || !status} onChange={(event) => toggleAuto(event.target.checked)} /><span>自动获取影响因子</span></label>
    <p className="muted">官网明确公布 JIF 和年份才展示；查不到标注“暂未查到”，预印本和会议论文显示“不适用”。查询失败仍照常推送文献，JIF 不参与相关性筛选。公开来源覆盖不全，也可导入已有 JCR 数据。</p>
    {status?.cached_journals !== undefined && <p className="muted">已查询期刊：{status.cached_journals} · 已查到：{status.matched_journals || 0}</p>}
    {status?.latest_year && <p className="muted">最新指标年份：{status.latest_year} · 最近更新：{status.updated_at ? new Date(status.updated_at).toLocaleString() : "未提供"}</p>}
    <div className="settings-form"><label>指标 CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => { setFile(event.target.files?.[0] || null); setNotice(""); }} /></label>
      <label>数据来源名称<input value={source} maxLength={200} onChange={(event) => setSource(event.target.value)} placeholder="填写 JCR 导出的实际来源" /></label>
      <label>来源链接（可选）<input type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} /></label></div>
    <p className="muted">UTF-8 CSV 列：journal、issn、year、jif；可另加 eissn。year 为指标年份，JIF 支持 0 和 &lt;0.1。相同 ISSN/年份会更新，其他年份保留；无效数据整批拒绝。请先将导出表整理为模板格式。</p>
    <div className="settings-actions"><a href={`${API}/journal-metrics/template`} download>下载空白 CSV 模板</a><button className="primary-button" disabled={busy || !file || !source.trim()} onClick={upload}>{busy ? "正在导入…" : "导入影响因子"}</button></div>
    {error && <p className="run-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </div>;
}
