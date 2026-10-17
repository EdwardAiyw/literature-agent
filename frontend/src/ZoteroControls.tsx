import { useEffect, useRef, useState } from "react";

const API = import.meta.env.VITE_API_URL || "/api";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API + path, init);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export type ZoteroConfig = { zotero_auto_import: boolean; zotero_collection_key: string };
type Collection = { key: string; name: string; path: string };

export function ZoteroTaskPicker({ value, onChange }: { value: ZoteroConfig; onChange: (value: ZoteroConfig) => void }) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setBusy(true); setError("");
    try { setCollections(await request<Collection[]>("/zotero/collections")); }
    catch (error) { setError(String(error)); }
    finally { setBusy(false); }
  };
  return <fieldset><legend>Zotero 导入</legend>
    <label className="check-field"><input type="checkbox" checked={value.zotero_auto_import} onChange={(event) => onChange({ ...value, zotero_auto_import: event.target.checked })} /><span>检索完成后自动导入 Zotero</span></label>
    <div className="field-row"><label>目标集合<select aria-label="目标集合" value={value.zotero_collection_key} onChange={(event) => onChange({ ...value, zotero_collection_key: event.target.value })}>
      <option value="">请选择集合</option>
      {value.zotero_collection_key && !collections.some((c) => c.key === value.zotero_collection_key) && <option value={value.zotero_collection_key}>{value.zotero_collection_key}（点击读取集合确认名称）</option>}
      {collections.map((c) => <option key={c.key} value={c.key}>{c.path} · {c.key}</option>)}
    </select></label><button type="button" className="secondary-button" disabled={busy} onClick={load}>{busy ? "正在读取…" : "读取集合"}</button></div>
    <p className="muted">先在设置中保存 Zotero 文献库和 API Key。自动导入使用所选集合；每日邮件附带可手动粘贴的标识符文件。</p>
    {error && <p className="run-error" role="alert">{error}</p>}
  </fieldset>;
}

type Batch = { id: string; status: string; destination: string; error: string; counts?: Record<string, number>; results: Record<string, { status: string; error?: string }> };

export function ZoteroBatchPanel({ runId, runStatus, collectionKey, automatic, onChange }: { runId: string; runStatus: string; collectionKey?: string; automatic?: boolean; onChange: () => void }) {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const changed = useRef(onChange);
  changed.current = onChange;
  useEffect(() => {
    const controller = new AbortController();
    let timer = 0, previous = "";
    const poll = async () => {
      try {
        const rows = await request<Batch[]>(`/runs/${runId}/zotero-batches`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setBatches(rows); setError("");
        const signature = JSON.stringify(rows.map((b) => [b.id, b.status, b.counts]));
        if (signature !== previous && rows.length) changed.current();
        previous = signature;
        if (automatic || rows.some((b) => ["queued", "running"].includes(b.status))) timer = window.setTimeout(poll, 3000);
      } catch (error) { if (!controller.signal.aborted) setError(String(error)); }
    };
    setBatches([]); void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [runId, automatic, runStatus, revision]);
  const submit = async (batch?: Batch) => {
    setBusy(true); setError("");
    try {
      await request(`/runs/${runId}/zotero-batches${batch ? `/${batch.id}/retry` : ""}`, { method: "POST" });
      setRevision((r) => r + 1);
    } catch (error) { setError(String(error)); }
    finally { setBusy(false); }
  };
  const active = batches.some((b) => ["queued", "running"].includes(b.status));
  return <div className="diagnostic-panel zotero-batch-panel">
    <div className="diagnostic-title"><strong>Zotero 导入与附件</strong><a href={`${API}/runs/${runId}/zotero-identifiers`} download>下载标识符 TXT</a></div>
    <p className="muted">每篇优先保留一个真实编号，已忽略的论文不导出。下载文件可粘贴到 Zotero 的“通过标识符添加条目”窗口。</p>
    {batches.map((batch) => { const target = JSON.parse(batch.destination) as string[]; return <div key={batch.id}>
      <p><strong>{{ queued: "等待导入", running: "正在导入", completed: "导入完成", failed: "导入失败" }[batch.status] || batch.status}</strong> · {target[0]} / {target[1]} / {target[2]}</p>
      <p>新增 {batch.counts?.imported || 0} · 已存在 {batch.counts?.existing || 0} · 失败 {batch.counts?.failed || 0} · 跳过 {batch.counts?.skipped || 0} · 待处理 {batch.counts?.pending ?? Object.keys(batch.results).length}</p>
      {batch.error && <p className="run-error">{batch.error}</p>}
      {batch.status === "failed" && <button className="secondary-button" disabled={busy || active} onClick={() => submit(batch)}>重试失败条目</button>}
    </div>; })}
    {runStatus === "completed" && collectionKey && !active && <button className="secondary-button" disabled={busy} onClick={() => submit()}>导入本次结果到任务集合</button>}
    {error && <p className="run-error" role="alert">{error}<button className="secondary-button" onClick={() => setRevision((r) => r + 1)}>刷新导入状态</button></p>}
  </div>;
}
