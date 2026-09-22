import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, ArrowUpRight, BookOpen, CheckCircle2, CircleHelp, FileText, LayoutList, Mail, Play, Plus, Settings2, SlidersHorizontal, Sparkles, Trash2 } from "lucide-react";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001/api";
const defaultSources = ["openalex", "crossref", "arxiv", "pubmed"];
type Task = { id: string; name: string; topic: string; target_count: number; language: string; output_language: string; date_from: string; date_to: string; sources: string[]; evidence_review: boolean; created_at: string };
type Run = { id: string; task_id: string; status: string; current_node: string; paper_count: number; error: string; progress: number; total_steps: number };
type Paper = { id: string; title: string; authors: string[]; abstract: string; published_date: string; source: string; doi: string; official_url: string; relevance_score: number; priority: string; summary: Record<string, unknown>; review: string };
type RunEvent = { id: number; run_id: string; node: string; status: string; message: string; artifact_type: string; created_at: string };
type Artifact = { run_id: string; node: string; payload: Record<string, any>; created_at: string };
type Prompt = { id: string; role: string; version: string; body: string; builtin: boolean };
type Subscription = { id: string; task_id: string; name: string; topic: string; target_count: number; language: string; recipient: string; schedule_time: string; timezone: string; date_from: string; date_to: string; sources: string[]; enabled: boolean; created_at: string };
type Delivery = { id: string; subscription_id: string; run_id: string | null; kind: "digest" | "test"; status: "pending" | "sent" | "failed"; recipient: string; subject: string; error: string; created_at: string; sent_at: string | null };
type SourceOption = { id: string; label?: string; description?: string };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

const nodeLabels: Record<string, string> = { query_planner: "检索规划", retrieval: "来源检索", dedupe: "去重规范化", relevance_screener: "相关性筛选", literature_summarizer: "文献简报", evidence_reviewer: "证据审查", complete: "保存结果" };
const sourceLabels: Record<string, string> = { openalex: "OpenAlex", crossref: "Crossref", arxiv: "arXiv", pubmed: "PubMed", fixture: "Fixture" };

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [sourceOptions, setSourceOptions] = useState<SourceOption[]>(defaultSources.map((id) => ({ id })));
  const [activeView, setActiveView] = useState("workspace");
  const [topic, setTopic] = useState("");
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("bilingual");
  const [targetCount, setTargetCount] = useState(10);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>(defaultSources);
  const [evidenceReview, setEvidenceReview] = useState(false);
  const [subscriptionForm, setSubscriptionForm] = useState({ name: "", topic: "", recipient: "", schedule_time: "", timezone: "Asia/Hong_Kong", target_count: "", date_from: "", date_to: "", sources: defaultSources });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deletingSubscriptionId, setDeletingSubscriptionId] = useState<string | null>(null);

  const loadTasks = async () => { const items = await request<Task[]>("/tasks"); setTasks(items); return items; };
  const loadSubscriptions = async () => setSubscriptions(await request<Subscription[]>("/subscriptions"));
  const loadDeliveries = async () => setDeliveries(await request<Delivery[]>("/deliveries"));
  const loadPrompts = async () => setPrompts(await request<Prompt[]>("/prompts"));
  const loadRunData = async (runId: string) => {
    const [currentEvents, currentArtifacts, currentPapers] = await Promise.all([
      request<RunEvent[]>(`/runs/${runId}/events`),
      request<Artifact[]>(`/runs/${runId}/artifacts`),
      request<Paper[]>(`/runs/${runId}/papers`),
    ]);
    setEvents(currentEvents); setArtifacts(currentArtifacts); setPapers(currentPapers);
  };
  const openTask = async (task: Task) => {
    setError(""); setSelectedTask(task); setRun(null); setPapers([]); setEvents([]); setArtifacts([]);
    const taskRuns = await request<Run[]>(`/tasks/${task.id}/runs?limit=1`);
    if (!taskRuns.length) return;
    setRun(taskRuns[0]); await loadRunData(taskRuns[0].id);
  };

  useEffect(() => {
    Promise.all([loadTasks().then((items) => items[0] ? openTask(items[0]) : undefined), loadSubscriptions(), loadDeliveries(), loadPrompts(), request<{ sources: SourceOption[] }>("/settings").then((settings) => { const liveSources = settings.sources.filter((source) => source.id !== "fixture"); if (liveSources.length) { setSourceOptions(liveSources); setSelectedSources(liveSources.map((source) => source.id)); setSubscriptionForm((current) => ({ ...current, sources: liveSources.map((source) => source.id) })); } })]).catch((e) => setError(String(e)));
  }, []);
  useEffect(() => {
    if (!run || ["completed", "failed", "cancelled"].includes(run.status)) { if (run) { loadRunData(run.id).catch(() => undefined); loadDeliveries().catch(() => undefined); } return; }
    const timer = window.setInterval(async () => { try { const current = await request<Run>(`/runs/${run.id}`); setRun(current); await loadRunData(current.id); } catch (e) { setError(String(e)); } }, 700);
    return () => window.clearInterval(timer);
  }, [run?.id, run?.status]);
  useEffect(() => { if (activeView === "subscriptions") loadDeliveries().catch((e) => setError(String(e))); }, [activeView]);

  const startTask = async () => {
    if (!topic.trim() || !name.trim()) return setError("请填写任务名称和研究主题。");
    if (!selectedSources.length) return setError("至少选择一个文献来源。");
    setError(""); setNotice("");
    const task = await request<Task>("/tasks", { method: "POST", body: JSON.stringify({ name, topic, language, output_language: "zh", target_count: targetCount, date_from: dateFrom, date_to: dateTo, sources: selectedSources, evidence_review: evidenceReview }) });
    const createdRun = await request<Run>(`/tasks/${task.id}/runs`, { method: "POST" });
    setSelectedTask(task); setRun(createdRun); setPapers([]); setEvents([]); setArtifacts([]); await loadTasks();
  };
  const createSubscription = async () => {
    const form = subscriptionForm;
    if (!form.name.trim() || !form.topic.trim() || !form.recipient.trim() || !form.schedule_time || !form.target_count) return setError("请填写订阅名称、主题、收件人、执行时间和目标篇数。");
    if (!form.sources.length) return setError("订阅至少需要一个来源。");
    setError(""); setNotice("");
    await request<Subscription>("/subscriptions", { method: "POST", body: JSON.stringify({ ...form, target_count: Number(form.target_count), output_language: "zh", language: "bilingual", enabled: true }) });
    setSubscriptionForm({ name: "", topic: "", recipient: "", schedule_time: "", timezone: "Asia/Hong_Kong", target_count: "", date_from: "", date_to: "", sources: selectedSources.length ? selectedSources : defaultSources });
    await loadSubscriptions(); setNotice("订阅已保存；首次运行前请在设置中确认 LLM、SMTP 和实时来源配置。");
  };
  const runSubscription = async (subscription: Subscription) => {
    setError(""); setNotice("");
    const createdRun = await request<Run>(`/subscriptions/${subscription.id}/runs`, { method: "POST" });
    const task = tasks.find((item) => item.id === subscription.task_id) || await request<Task>(`/tasks/${subscription.task_id}`);
    setSelectedTask(task); setRun(createdRun); setPapers([]); setEvents([]); setArtifacts([]); setActiveView("workspace"); await loadDeliveries();
  };
  const testSend = async (subscription: Subscription) => {
    setError("");
    const delivery = await request<Delivery>(`/subscriptions/${subscription.id}/test-send`, { method: "POST", body: JSON.stringify({}) });
    await loadDeliveries(); setNotice(delivery.status === "sent" ? "测试邮件已发送。" : `测试邮件失败：${delivery.error}`);
  };
  const deleteSubscription = async (subscription: Subscription) => {
    const confirmed = window.confirm(`确定删除“${subscription.name}”吗？\n\n该订阅的投递记录、任务和运行结果都会被删除。`);
    if (!confirmed) return;
    setError(""); setNotice(""); setDeletingSubscriptionId(subscription.id);
    try {
      await request<{ status: string }>(`/subscriptions/${subscription.id}`, { method: "DELETE" });
      await Promise.all([loadSubscriptions(), loadDeliveries(), loadTasks()]);
      if (selectedTask?.id === subscription.task_id) {
        setSelectedTask(null); setRun(null); setPapers([]); setEvents([]); setArtifacts([]);
      }
      setNotice("订阅及其历史运行数据已删除。");
    } catch (e) {
      setError(String(e));
    } finally {
      setDeletingSubscriptionId(null);
    }
  };
  const review = async (paperId: string, value: string) => { await request(`/papers/${paperId}/review`, { method: "POST", body: JSON.stringify({ review: value }) }); setPapers((current) => current.map((paper) => paper.id === paperId ? { ...paper, review: value } : paper)); };
  const toggleSource = (source: string, setter: (next: string[]) => void, current: string[]) => setter(current.includes(source) ? current.filter((item) => item !== source) : [...current, source]);
  const statusLabel = run ? ({ queued: "排队中", running: "运行中", completed: "已完成", failed: "失败", cancelled: "已取消" } as Record<string, string>)[run.status] || run.status : "未运行";
  const reviewed = useMemo(() => papers.filter((paper) => paper.review !== "unreviewed").length, [papers]);
  const latestEvent = events[events.length - 1];
  const retrievalArtifact = artifacts.find((artifact) => artifact.node === "retrieval");

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><div className="brand-mark">LA</div><div><strong>Literature Agent</strong><span>Academic discovery</span></div></div><nav>
      <button className={activeView === "workspace" ? "active" : ""} onClick={() => setActiveView("workspace")}><LayoutList size={17} />工作台</button>
      <button className={activeView === "subscriptions" ? "active" : ""} onClick={() => setActiveView("subscriptions")}><Mail size={17} />每日订阅</button>
      <button className={activeView === "prompts" ? "active" : ""} onClick={() => setActiveView("prompts")}><Sparkles size={17} />Prompt 版本</button>
      <button className={activeView === "settings" ? "active" : ""} onClick={() => setActiveView("settings")}><Settings2 size={17} />设置</button>
    </nav><div className="sidebar-foot"><CircleHelp size={16} /> <span>本地优先 · MVP</span></div></aside>
    <main className="main-content"><header className="topbar"><div><p className="eyebrow">RESEARCH WORKSPACE</p><h1>{activeView === "workspace" ? "文献发现工作台" : activeView === "subscriptions" ? "每日文献订阅" : activeView === "prompts" ? "Prompt 版本" : "连接设置"}</h1></div><div className="connection"><span className="status-dot" />本地服务已连接</div></header>
      {notice && <p className="notice">{notice}</p>}{error && <p className="error global-error">{error}</p>}
      {activeView === "workspace" && <>
        <section className="control-grid"><div className="panel create-panel"><div className="panel-heading"><div><span className="section-index">01</span><h2>创建研究任务</h2></div><SlidersHorizontal size={18} /></div><label>任务名称<input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：Agentic RAG 文献追踪" /></label><label>研究主题<textarea value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="描述要抓取和筛选的研究主题" rows={3} /></label><div className="field-row"><label>检索语言<select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="bilingual">中英文</option><option value="zh">中文</option><option value="en">英文</option></select></label><label>目标数量<input type="number" min="1" max="100" value={targetCount} onChange={(e) => setTargetCount(Number(e.target.value))} /></label></div><div className="field-row"><label>起始日期<input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label><label>结束日期<input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label></div><fieldset><legend>文献来源</legend><div className="source-grid">{sourceOptions.map((source) => <label className="source-option" key={source.id}><input type="checkbox" checked={selectedSources.includes(source.id)} onChange={() => toggleSource(source.id, setSelectedSources, selectedSources)} /><span>{sourceLabels[source.id] || source.id}</span></label>)}</div></fieldset><label className="check-field"><input type="checkbox" checked={evidenceReview} onChange={(e) => setEvidenceReview(e.target.checked)} /><span>启用证据审查</span></label><button className="primary-button" onClick={startTask}><Play size={16} />开始检索</button></div>
          <div className="panel task-panel"><div className="panel-heading"><div><span className="section-index">02</span><h2>最近任务</h2></div><button className="icon-button" title="刷新任务" onClick={loadTasks}><Plus size={17} /></button></div>{tasks.length === 0 ? <div className="empty-state"><FileText size={25} /><p>还没有研究任务</p><span>创建第一个主题后，Agent 运行记录会显示在这里。</span></div> : <div className="task-list">{tasks.map((task) => <button className={`task-row ${selectedTask?.id === task.id ? "selected" : ""}`} key={task.id} onClick={() => openTask(task).catch((e) => setError(String(e)))}><span className="task-number">{task.name.slice(0, 2)}</span><span><strong>{task.name}</strong><small>{task.topic}</small></span><ArrowUpRight size={15} /></button>)}</div>}</div></section>
        <section className="workspace-section"><div className="section-toolbar"><div><span className="section-index">03</span><h2>结果</h2></div><div className="toolbar-meta"><span>{run ? statusLabel : "等待任务"}</span><span>{papers.length} papers</span><span>{reviewed} 已审核</span></div></div>
          {run && <div className="run-strip"><Activity size={15} /><span>Agent：{nodeLabels[run.current_node] || run.current_node || "准备中"}</span><span className="progress-label">{run.progress}/{run.total_steps || 6}</span><span className="run-id">Run {run.id.slice(0, 8)}</span></div>}
          {run && <div className="activity-panel"><div className="activity-heading"><strong>Agent 活动</strong><span>{latestEvent?.message || "等待节点启动"}</span></div><div className="activity-track">{events.filter((event) => event.status === "completed").map((event) => <div className="activity-step" key={event.id}><CheckCircle2 size={15} /><span>{nodeLabels[event.node] || event.node}</span><small>{event.message}</small></div>)}{run.status === "failed" && <div className="activity-step failed"><AlertTriangle size={15} /><span>运行失败</span><small>{run.error}</small></div>}</div></div>}
          {retrievalArtifact && <div className="diagnostic-panel"><strong>来源诊断</strong><div className="diagnostic-grid">{(Object.entries(retrievalArtifact.payload.sources || {}) as [string, any][]).map(([source, diagnostic]) => <div className={`diagnostic ${diagnostic.status === "failed" ? "failed" : ""}`} key={source}><span>{sourceLabels[source] || source}</span><b>{diagnostic.status}</b><small>{diagnostic.count || 0} 条{diagnostic.error ? ` · ${diagnostic.error}` : ""}</small></div>)}</div></div>}
          {papers.length === 0 ? <div className="results-empty"><BookOpen size={30} /><strong>{run ? (run.status === "completed" ? "本次运行没有选出论文" : "Agent 正在整理结果") : "选择一个任务开始"}</strong><span>结果会在检索、去重和摘要完成后出现在这里。</span></div> : <div className="paper-table"><div className="table-head"><span>论文</span><span>来源</span><span>相关性</span><span>状态</span></div>{papers.map((paper) => <article className="paper-row" key={paper.id}><div><div className="paper-title">{paper.title}</div><div className="paper-authors">{paper.authors.join(", ")} · {paper.published_date}</div><p>{String(paper.summary.relevance_reason || "")}</p><a href={paper.official_url} target="_blank" rel="noreferrer">查看原文 <ArrowUpRight size={13} /></a></div><span className="source-badge">{sourceLabels[paper.source] || paper.source}</span><span className="score">{Math.round(paper.relevance_score * 100)}%</span><select value={paper.review} onChange={(e) => review(paper.id, e.target.value)}><option value="unreviewed">待审核</option><option value="read">精读</option><option value="save">保存</option><option value="background">背景</option><option value="ignore">忽略</option></select></article>)}</div>}
        </section>
      </>}
      {activeView === "subscriptions" && subscriptions.length > 0 && <div className="subscription-delete-strip"><span>订阅管理</span>{subscriptions.map((subscription) => <button className="delete-subscription-button" key={subscription.id} title={`删除订阅：${subscription.name}`} aria-label={`删除订阅：${subscription.name}`} disabled={deletingSubscriptionId === subscription.id} onClick={() => deleteSubscription(subscription)}><Trash2 size={14} /><span>{subscription.name}</span></button>)}</div>}
      {activeView === "subscriptions" && <section className="simple-section"><div className="section-toolbar"><div><span className="section-index">04</span><h2>配置每日订阅</h2></div><span className="toolbar-meta">{subscriptions.length} 个订阅</span></div><div className="subscription-layout"><div className="panel subscription-form"><label>订阅名称<input value={subscriptionForm.name} onChange={(e) => setSubscriptionForm({ ...subscriptionForm, name: e.target.value })} placeholder="例如：我的 RAG 日报" /></label><label>研究主题<textarea value={subscriptionForm.topic} onChange={(e) => setSubscriptionForm({ ...subscriptionForm, topic: e.target.value })} rows={3} placeholder="每日检索的主题" /></label><div className="field-row"><label>收件人<input type="email" value={subscriptionForm.recipient} onChange={(e) => setSubscriptionForm({ ...subscriptionForm, recipient: e.target.value })} /></label><label>目标篇数<input type="number" min="1" max="100" value={subscriptionForm.target_count} onChange={(e) => setSubscriptionForm({ ...subscriptionForm, target_count: e.target.value })} /></label></div><div className="field-row"><label>执行时间<input type="time" value={subscriptionForm.schedule_time} onChange={(e) => setSubscriptionForm({ ...subscriptionForm, schedule_time: e.target.value })} /></label><label>时区<input value={subscriptionForm.timezone} onChange={(e) => setSubscriptionForm({ ...subscriptionForm, timezone: e.target.value })} placeholder="Asia/Hong_Kong" /></label></div><div className="field-row"><label>起始日期<input type="date" value={subscriptionForm.date_from} onChange={(e) => setSubscriptionForm({ ...subscriptionForm, date_from: e.target.value })} /></label><label>结束日期<input type="date" value={subscriptionForm.date_to} onChange={(e) => setSubscriptionForm({ ...subscriptionForm, date_to: e.target.value })} /></label></div><fieldset><legend>订阅来源</legend><div className="source-grid">{sourceOptions.map((source) => <label className="source-option" key={source.id}><input type="checkbox" checked={subscriptionForm.sources.includes(source.id)} onChange={() => toggleSource(source.id, (next) => setSubscriptionForm({ ...subscriptionForm, sources: next }), subscriptionForm.sources)} /><span>{sourceLabels[source.id] || source.id}</span></label>)}</div></fieldset><button className="primary-button" onClick={createSubscription}><Plus size={16} />保存订阅</button></div><div className="subscription-list">{subscriptions.length === 0 ? <div className="empty-state"><Mail size={25} /><p>还没有每日订阅</p><span>配置后可手动运行，Windows 定时任务稍后调用同一 CLI。</span></div> : subscriptions.map((subscription) => <article className="subscription-row" key={subscription.id}><div><strong>{subscription.name}</strong><p>{subscription.topic}</p><small>{subscription.schedule_time} · {subscription.target_count} 篇 · {subscription.enabled ? "已启用" : "已停用"}</small></div><div className="row-actions"><button className="secondary-button" onClick={() => runSubscription(subscription)}><Play size={14} />手动运行</button><button className="icon-button" title="发送测试邮件" onClick={() => testSend(subscription)}><Mail size={15} /></button></div></article>)}</div></div><div className="delivery-panel"><div className="section-toolbar"><h2>投递记录</h2><button className="icon-button" title="刷新投递记录" onClick={loadDeliveries}><Plus size={16} /></button></div>{deliveries.length === 0 ? <p className="muted">尚无投递记录。</p> : deliveries.map((delivery) => <div className="delivery-row" key={delivery.id}><span className={`delivery-status ${delivery.status}`}>{delivery.status}</span><span>{delivery.kind === "test" ? "SMTP 测试" : "每日摘要"}</span><span>{delivery.recipient}</span><small>{delivery.error || new Date(delivery.created_at).toLocaleString()}</small></div>)}</div></section>}
      {activeView === "prompts" && <section className="simple-section"><div className="section-toolbar"><div><span className="section-index">05</span><h2>运行时 Prompt</h2></div><span className="toolbar-meta">{prompts.length} 个版本</span></div><div className="prompt-grid">{prompts.map((prompt) => <div className="prompt-card" key={prompt.id}><span>{prompt.id}</span><strong>{nodeLabels[prompt.role] || prompt.role}</strong><p>{prompt.body}</p><small>内置版本 · 运行时快照</small></div>)}</div></section>}
      {activeView === "settings" && <section className="simple-section"><div className="section-toolbar"><div><span className="section-index">06</span><h2>连接设置</h2></div></div><div className="settings-list"><div><strong>模型提供商</strong><span>通过后端 .env 配置 OpenAI-compatible API；每日订阅要求 LLM_API_KEY 和 LLM_MODEL。</span></div><div><strong>SMTP</strong><span>通过 SMTP_HOST、SMTP_PORT、SMTP_USERNAME、SMTP_PASSWORD、SMTP_FROM 配置；密码不会写入数据库。</span></div><div><strong>文献来源</strong><span>OpenAlex、Crossref、arXiv、PubMed；订阅运行要求 LITERATURE_AGENT_LIVE=true。</span></div><div><strong>Zotero</strong><span>MVP 暂不自动导入；邮件保留 DOI 和原文链接。</span></div></div></section>}
    </main>
  </div>;
}
