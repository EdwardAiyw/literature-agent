import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "/api";
type Metric = { journal: string; year: number; jif: string; source: string; source_url: string; matched_by: string };
type Status = { records: number; latest_year: number | null; updated_at: string | null };

export function JournalMetric({ paper }: { paper: { source: string; venue?: string; venue_type?: string; journal_metric?: Metric | null } }) {
  const metric = paper.journal_metric;
  const applicable = paper.source !== "arxiv" && !["repository", "conference", "proceedings-article", "book", "book-chapter", "posted-content"].includes(paper.venue_type || "");
  return <div className="journal-metric">
    <span>期刊/出版物：{paper.venue || metric?.journal || "未提供"}</span>
    {!applicable ? <span>期刊影响因子：不适用（预印本或非期刊文献）</span> : metric ? <>
      <span>期刊影响因子 JIF：<strong>{metric.jif}</strong> · {metric.year}</span>
      <span>来源：{metric.source} · 用户导入 · ISSN 匹配{metric.source_url && <> · <a href={metric.source_url} target="_blank" rel="noreferrer">来源链接</a></>}</span>
    </> : <span>期刊影响因子：未提供（无可匹配的已导入 JCR 数据）</span>}
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
  return <div className="settings-section">
    <div className="settings-title"><div /><div><strong>期刊影响因子（JIF）</strong><span>导入你可使用的 JCR 指标表，按 ISSN 匹配并标注指标年份和来源。</span></div><span className={`config-state ${status?.records ? "ready" : "missing"}`}>{status ? `${status.records} 条记录` : "读取中"}</span></div>
    <p className="muted">当前检索源不提供官方 JIF，此功能不会自动获取 JCR。使用最新已导入年份；未匹配显示“未提供”，预印本及非期刊文献显示“不适用”。JIF 不参与相关性筛选。</p>
    {status?.latest_year && <p className="muted">最新指标年份：{status.latest_year} · 最近导入：{status.updated_at ? new Date(status.updated_at).toLocaleString() : "未提供"}</p>}
    <div className="settings-form"><label>指标 CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => { setFile(event.target.files?.[0] || null); setNotice(""); }} /></label>
      <label>数据来源名称<input value={source} maxLength={200} onChange={(event) => setSource(event.target.value)} placeholder="填写 JCR 导出的实际来源" /></label>
      <label>来源链接（可选）<input type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} /></label></div>
    <p className="muted">UTF-8 CSV 列：journal、issn、year、jif；可另加 eissn。year 为指标年份，JIF 支持 0 和 &lt;0.1。相同 ISSN/年份会更新，其他年份保留；无效数据整批拒绝。请先将导出表整理为模板格式。</p>
    <div className="settings-actions"><a href={`${API}/journal-metrics/template`} download>下载空白 CSV 模板</a><button className="primary-button" disabled={busy || !file || !source.trim()} onClick={upload}>{busy ? "正在导入…" : "导入影响因子"}</button></div>
    {error && <p className="run-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </div>;
}
