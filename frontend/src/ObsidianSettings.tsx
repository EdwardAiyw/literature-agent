import { useEffect, useState } from "react";
import { BookOpen, RefreshCw, Save } from "lucide-react";

const API = import.meta.env.VITE_API_URL || "/api";
type Config = { vault: string; folder: string; mode: "ssh" | "local"; ssh_target: string; database: string; subscription_id: string; since: string; timezone: string };
type Status = { supported: boolean; config: Config | null; vaults: { path: string; name: string; open: boolean }[]; last_sync: { at: string; status: string; error?: string; unique_notes?: number; days?: number } | null; scheduler: { tasks: { name: string; state: string; last_result?: number }[]; error?: string } };

async function request<T>(path = "", method = "GET", body?: Config): Promise<T> {
  const response = await fetch(`${API}/obsidian${path}`, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail === "string" ? error.detail : "Obsidian 操作失败，请检查配置和连接。");
  }
  return response.json();
}

export default function ObsidianSettings({ dataDir }: { dataDir: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [form, setForm] = useState<Config>({ vault: "", folder: "Literature Agent", mode: "ssh", ssh_target: "", database: "/opt/literature-agent/data/literature_agent_v2.db", subscription_id: "", since: new Date(new Date().setHours(0, 0, 0, 0)).toISOString(), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Hong_Kong" });
  const [saved, setSaved] = useState<Config | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const dirty = !saved || JSON.stringify(form) !== JSON.stringify(saved);
  const load = async () => { const next = await request<Status>(); setStatus(next); return next; };
  useEffect(() => {
    let active = true;
    request<Status>().then((next) => {
      if (!active) return;
      setStatus(next);
      if (next.config) { const config = { ...next.config, mode: next.config.mode || "ssh" as const }; setForm(config); setSaved(config); }
      else { const vault = next.vaults.find((v) => v.open) || next.vaults[0]; if (vault) setForm((current) => ({ ...current, vault: vault.path })); }
    }).catch((error) => { if (active) setError(String(error)); });
    return () => { active = false; };
  }, [dataDir]);
  const execute = async (action: string) => {
    setBusy(action); setError(""); setNotice("");
    try {
      if (action === "save") { await request("", "PUT", form); setSaved({ ...form }); }
      else await request(`/${action}`, "POST");
      await load();
      const messages: Record<string, string> = { save: "Obsidian 配置已保存。", sync: "同步完成，已有论文笔记已复用。", register: "已启用：登录时及每 15 分钟同步。", disable: "已停用自动同步，笔记保留。", open: "已打开 Obsidian 论文索引。" };
      setNotice(messages[action]);
    } catch (error) { setError(String(error)); if (action === "sync") await load().catch(() => undefined); }
    finally { setBusy(""); }
  };
  const field = (label: string, key: keyof Config, placeholder?: string) => <label>{label}<input value={form[key]} placeholder={placeholder} onChange={(e) => setForm({ ...form, [key]: e.target.value })} /></label>;
  const task = status?.scheduler.tasks[0];
  return <section className="settings-section obsidian-settings" aria-label="Obsidian 连接">
    <div className="settings-title"><BookOpen size={18} /><div><strong>Obsidian 文库</strong><span>把成功推送保存为论文笔记和每日索引，保留个人阅读批注。</span></div><span className={`config-state ${saved ? "ready" : "missing"}`}>{saved ? "已配置" : "待配置"}</span></div>
    {error && <p className="error" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {status?.supported === false ? <p className="muted">请在 Windows 本机版的设置页连接 Obsidian 文库。服务器继续发送每日论文，电脑登录联网后可自动补齐。</p> : <>
      <fieldset disabled={!!busy || !status} className="obsidian-form"><div className="settings-form">
        {!!status?.vaults.length && <label>已发现的 Obsidian 文库<select value={status.vaults.some((v) => v.path === form.vault) ? form.vault : ""} onChange={(e) => { if (e.target.value) setForm({ ...form, vault: e.target.value }); }}><option value="">自定义路径</option>{status.vaults.map((v) => <option key={v.path} value={v.path}>{v.name}{v.open ? "（当前打开）" : ""}</option>)}</select></label>}
        {field("文库路径", "vault")}{field("导出文件夹", "folder")}
        <label>推送来源<select value={form.mode} onChange={(e) => { const mode = e.target.value as Config["mode"]; setForm({ ...form, mode, database: mode === "local" ? `${dataDir}/literature_agent_v2.db` : "/opt/literature-agent/data/literature_agent_v2.db" }); }}><option value="ssh">Linux 服务器</option><option value="local">本机</option></select></label>
        {form.mode === "ssh" && field("SSH 地址", "ssh_target", "user@server")}
        {field(form.mode === "ssh" ? "服务器数据库路径" : "本机数据库路径", "database")}
        {field("每日订阅 ID", "subscription_id")}{field("导入起始时间（含时区）", "since", "2026-10-19T00:00:00+08:00")}{field("归档时区", "timezone")}
      </div></fieldset>
      <p className="muted">{form.mode === "ssh" ? "需先验证 SSH 主机指纹并配置密钥登录。" : "只读取已成功发送的每日论文。"}批注请写在“我的阅读笔记”区域。电脑离线后会在下次联网同步时补齐。</p>
      {dirty && <p className="muted">请先保存配置，再同步或启用自动同步。</p>}
      <div className="settings-actions"><button className="primary-button" disabled={!!busy || !status || !form.vault || !form.subscription_id || !dirty} onClick={() => execute("save")}><Save size={14} />保存 Obsidian 配置</button><button className="secondary-button" disabled={!!busy || dirty} onClick={() => execute("sync")}><RefreshCw size={14} />{busy === "sync" ? "正在同步…" : "立即同步到 Obsidian"}</button><button className="secondary-button" disabled={!!busy || dirty} onClick={() => execute("register")}>启用自动同步</button><button className="secondary-button" disabled={!!busy || !task} onClick={() => execute("disable")}>停用自动同步</button><button className="secondary-button" disabled={!!busy || dirty || status?.last_sync?.status !== "ok"} onClick={() => execute("open")}>打开论文索引</button><button className="secondary-button" disabled={!!busy} onClick={() => { setError(""); load().catch((e) => setError(String(e))); }}>刷新同步状态</button></div>
      <div className="obsidian-status" aria-label="Obsidian 同步状态"><span>自动同步：{task ? task.state === "Disabled" ? "已停用" : "已启用（登录时及每 15 分钟）" : "未启用"}</span>{status?.scheduler.error && <span>自动任务状态读取失败：{status.scheduler.error}</span>}{status?.last_sync ? <><span>最近同步：{new Date(status.last_sync.at).toLocaleString()} · {status.last_sync.status === "ok" ? "成功" : "失败"}</span>{status.last_sync.status === "ok" ? <span>{status.last_sync.unique_notes} 篇论文笔记 · {status.last_sync.days} 份每日清单</span> : <span role="alert">{status.last_sync.error}</span>}</> : <span>尚未同步</span>}</div>
    </>}
  </section>;
}
