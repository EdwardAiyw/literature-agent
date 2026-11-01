import { useState } from "react";
import { ArrowUpRight, Database, Plus, RefreshCw, Settings2, X } from "lucide-react";

const API = import.meta.env.VITE_API_URL || "/api";

export type SourceConnection = {
  id: string; label?: string; description?: string; live?: boolean;
  added?: boolean; enabled?: boolean; configured?: boolean; selectable?: boolean;
  default_enabled?: boolean; requires_credentials?: boolean; credential_field?: string;
  credential_label?: string; credential_configured?: boolean; access_mode?: string; docs_url?: string;
  daily_request_budget?: number; budget_override?: number | null;
  contact_email?: string;
  last_test?: { status: string; count: number; error: string; checked_at: string; final_http_status?: number } | null;
};

async function call<T>(path: string, method: string, payload?: unknown): Promise<T> {
  const response = await fetch(`${API}${path}`, { method, headers: { "Content-Type": "application/json" }, body: payload === undefined ? undefined : JSON.stringify(payload) });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "来源配置未保存，请检查输入后重试。");
  return result;
}

export function SourcePicker({ sources, value, onChange, onConfigure }: { sources: SourceConnection[]; value: string[]; onChange: (next: string[]) => void; onConfigure?: () => void }) {
  const options = sources.filter((source) => source.selectable !== false || value.includes(source.id));
  return <fieldset className="source-picker"><legend>检索来源</legend><div className="source-grid">{options.map((source) => <label className="source-option" key={source.id} title={source.description}>
    <input type="checkbox" checked={value.includes(source.id)} disabled={source.selectable === false && !value.includes(source.id)} onChange={() => onChange(value.includes(source.id) ? value.filter((id) => id !== source.id) : [...value, source.id])} />
    {source.label || source.id}{source.selectable === false && "（已停用或待配置）"}
  </label>)}</div>{!options.length && <p className="muted">还没有可用来源，请先在设置中添加并启用。</p>}
    {onConfigure && <button type="button" className="source-manage-link" onClick={onConfigure}><Settings2 size={13} />管理文献来源</button>}
  </fieldset>;
}

type Props = { sources: SourceConnection[]; defaultBudget: number; reload: () => Promise<void>; setNotice: (message: string) => void; setError: (message: string) => void };

export default function SourceSettings({ sources, defaultBudget, reload, setNotice, setError }: Props) {
  const [adding, setAdding] = useState(false);
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState<SourceConnection | null>(null);
  const [busy, setBusy] = useState("");
  const [pendingEnabled, setPendingEnabled] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");
  const added = sources.filter((source) => source.added !== false);
  const available = sources.filter((source) => source.added === false);
  const visible = added.filter((source) => `${source.label} ${source.description}`.toLowerCase().includes(query.toLowerCase()));
  const selectedSource = available.find((source) => source.id === selected) || available[0];
  const act = async (id: string, action: () => Promise<unknown>, message: string) => {
    setBusy(id); setError(""); setNotice("");
    try { await action(); await reload(); setNotice(message); } catch (error) { setError(error instanceof Error ? error.message : String(error)); } finally { setBusy(""); }
  };
  const toggle = async (source: SourceConnection, enabled: boolean) => {
    setPendingEnabled((current) => ({ ...current, [source.id]: enabled }));
    await act(source.id, () => call(`/sources/${source.id}`, "PUT", { enabled, ...(!enabled ? { default_enabled: false } : {}) }), "来源设置已保存。");
    setPendingEnabled((current) => { const next = { ...current }; delete next[source.id]; return next; });
  };
  return <div className="settings-section source-settings" aria-label="文献来源管理">
    <div className="settings-title"><Database size={18} /><div><strong>文献来源</strong><span>添加检索服务、配置密钥，并选择哪些来源用于新任务。</span></div><span className="config-state">{added.length} 个来源 · {sources.filter((source) => source.selectable !== false && source.added !== false).length} 已启用</span></div>
    <div className="source-toolbar"><label>筛选来源<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="名称或覆盖领域" /></label><button className="primary-button" disabled={!available.length || !!busy} onClick={() => { setSelected(available[0]?.id || ""); setAdding(true); }}><Plus size={15} />添加来源</button></div>
    <div className="source-connection-list">{visible.map((source) => <article className="source-connection" key={source.id} aria-label={`${source.label} 来源`}>
      <div className="source-connection-info"><div className="source-connection-heading"><strong>{source.label}</strong><span className={`source-state ${source.enabled && source.configured ? "enabled" : ""}`}>{!source.configured ? "待配置" : source.enabled ? "已启用" : "已停用"}</span>{source.default_enabled && <span className="source-default">新任务默认</span>}</div>
        <p>{source.description}</p><div className="source-connection-meta"><span>{source.access_mode}</span><span>每日上限 {source.daily_request_budget ?? defaultBudget} 次</span>{source.docs_url && <a href={source.docs_url} target="_blank" rel="noreferrer">接入说明<ArrowUpRight size={12} /></a>}</div>
        {source.last_test && <div className={`source-test-result ${source.last_test.status === "ok" ? "success" : "failed"}`} role="status"><span>{source.last_test.status === "ok" ? `连接正常 · ${source.last_test.count} 条` : source.last_test.status === "rate_limited" ? "暂时限流" : "连接未通过"}</span><time>{new Date(source.last_test.checked_at).toLocaleString()}</time>{source.last_test.error && <span>{source.last_test.error}</span>}</div>}
      </div><div className="source-connection-actions"><label className="source-enable"><input type="checkbox" role="switch" aria-label={`${source.label} 启用`} checked={pendingEnabled[source.id] ?? !!source.enabled} disabled={!!busy || !source.configured} onChange={(event) => void toggle(source, event.target.checked)} />启用</label>
        <button className="secondary-button" disabled={!!busy} onClick={() => setEditing(source)}><Settings2 size={13} />配置</button>
        <button className="secondary-button" disabled={!!busy || !source.configured} onClick={() => void act(source.id, () => call(`/sources/${source.id}/test`, "POST"), "来源检测完成，请查看检测结果。")}><RefreshCw size={13} />{busy === source.id ? "处理中…" : "测试连接"}</button>
        <button className="text-button" disabled={!!busy} onClick={() => void act(source.id, () => call(`/sources/${source.id}`, "DELETE"), "来源已移除，可随时重新添加。")} aria-label={`移除 ${source.label}`}>移除</button>
      </div>
    </article>)}</div>
    {!added.length && <p className="muted">还没有添加文献来源。</p>}{added.length > 0 && !visible.length && <p className="muted">没有匹配的来源。</p>}
    <p className="source-settings-note">Google Scholar 通过 SerpApi 接入，需要该服务的 API Key 和可用额度。测试连接会进行一次小规模真实检索，并计入请求上限。已有任务保留来源选择，停用或移除的来源会在运行时跳过。</p>
    {adding && <div className="modal-backdrop"><section className="task-editor source-dialog" role="dialog" aria-modal="true" aria-label="添加文献来源"><div className="modal-heading"><h2>添加文献来源</h2><button className="icon-button" aria-label="关闭" onClick={() => setAdding(false)}><X size={17} /></button></div><label htmlFor="source-type">选择来源</label><select id="source-type" value={selectedSource?.id || ""} onChange={(event) => setSelected(event.target.value)}>{available.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}</select>{selectedSource && <SourceForm key={selectedSource.id} source={selectedSource} defaultBudget={defaultBudget} onCancel={() => setAdding(false)} onSaved={async () => { await reload(); setAdding(false); setNotice("文献来源已添加，可在任务和订阅中选择。"); }} />}</section></div>}
    {editing && <div className="modal-backdrop"><section className="task-editor source-dialog" role="dialog" aria-modal="true" aria-label={`配置 ${editing.label}`}><div className="modal-heading"><h2>配置 {editing.label}</h2><button className="icon-button" aria-label="关闭" onClick={() => setEditing(null)}><X size={17} /></button></div><SourceForm source={editing} defaultBudget={defaultBudget} onCancel={() => setEditing(null)} onSaved={async () => { await reload(); setEditing(null); setNotice("来源配置已保存并立即生效。"); }} /></section></div>}
  </div>;
}

function SourceForm({ source, defaultBudget, onCancel, onSaved }: { source: SourceConnection; defaultBudget: number; onCancel: () => void; onSaved: () => Promise<void> }) {
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(source.added === false ? true : !!source.enabled);
  const [isDefault, setIsDefault] = useState(!!source.default_enabled);
  const [budget, setBudget] = useState(source.budget_override ? String(source.budget_override) : "");
  const [email, setEmail] = useState(source.contact_email || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (clear = false) => {
    setBusy(true); setError("");
    try {
      await call(`/sources/${source.id}`, "PUT", clear ? { clear_api_key: true } : {
        enabled, default_enabled: enabled && isDefault, daily_request_budget: budget === "" ? null : Number(budget),
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}), ...(source.id === "pubmed" ? { email } : {}),
      });
      setApiKey(""); await onSaved();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); }
  };
  return <form onSubmit={(event) => { event.preventDefault(); void submit(); }}>
    <p className="source-form-description">{source.description}</p><div className="source-access"><span>{source.access_mode}</span>{source.docs_url && <a href={source.docs_url} target="_blank" rel="noreferrer">查看接入说明 / 申请密钥<ArrowUpRight size={12} /></a>}</div>
    <fieldset disabled={busy} className="source-form-fields">
      {source.credential_field && <label>{source.credential_label || "API Key"}<input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={source.credential_configured ? "已保存；留空保持不变" : "填写此服务的 API Key"} required={enabled && !!source.requires_credentials && !source.credential_configured} /></label>}
      {source.id === "pubmed" && <label>联系邮箱（可选）<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>}
      <label>每日请求上限<input type="number" min="1" max="100000" value={budget} onChange={(event) => setBudget(event.target.value)} placeholder={`沿用全局设置：${defaultBudget}`} /></label>
      <label className="check-field"><input type="checkbox" checked={enabled} onChange={(event) => { setEnabled(event.target.checked); if (!event.target.checked) setIsDefault(false); }} />启用此来源</label>
      <label className="check-field"><input type="checkbox" checked={isDefault} disabled={!enabled} onChange={(event) => setIsDefault(event.target.checked)} />默认用于新任务和新订阅</label>
    </fieldset>
    {error && <p className="error" role="alert">{error}</p>}
    {source.credential_configured && <button type="button" className="text-button" disabled={busy} onClick={() => void submit(true)}>清除已保存密钥并停用</button>}
    <div className="modal-actions"><button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>取消</button><button type="submit" className="primary-button" disabled={busy}>{busy ? "保存中…" : "保存来源"}</button></div>
  </form>;
}
