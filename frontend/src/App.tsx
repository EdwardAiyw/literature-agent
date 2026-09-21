import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, BookOpen, CircleHelp, FileText, LayoutList, Play, Plus, Settings2, SlidersHorizontal, Sparkles } from "lucide-react";

const API = "http://localhost:8000/api";
type Task = { id: string; name: string; topic: string; target_count: number; language: string; output_language: string; created_at: string };
type Run = { id: string; task_id: string; status: string; current_node: string; paper_count: number; error: string };
type Paper = { id: string; title: string; authors: string[]; abstract: string; published_date: string; source: string; doi: string; official_url: string; relevance_score: number; priority: string; summary: Record<string, unknown>; review: string };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [activeView, setActiveView] = useState("workspace");
  const [topic, setTopic] = useState("");
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("bilingual");
  const [targetCount, setTargetCount] = useState(10);
  const [error, setError] = useState("");

  const loadTasks = async () => setTasks(await request<Task[]>("/tasks"));
  useEffect(() => { loadTasks().catch((e) => setError(String(e))); }, []);
  useEffect(() => {
    if (!run || ["completed", "failed", "cancelled"].includes(run.status)) return;
    const timer = window.setInterval(async () => {
      const current = await request<Run>(`/runs/${run.id}`); setRun(current);
      if (current.status === "completed") setPapers(await request<Paper[]>(`/runs/${run.id}/papers`));
    }, 500);
    return () => window.clearInterval(timer);
  }, [run]);

  const startTask = async () => {
    if (!topic.trim() || !name.trim()) return setError("请填写任务名称和研究主题。");
    setError("");
    const task = await request<Task>("/tasks", { method: "POST", body: JSON.stringify({ name, topic, language, output_language: "zh", target_count: targetCount, sources: ["fixture"] }) });
    const createdRun = await request<Run>(`/tasks/${task.id}/runs`, { method: "POST" });
    setSelectedTask(task); setRun(createdRun); setPapers([]); await loadTasks();
  };
  const review = async (paperId: string, value: string) => {
    await request(`/papers/${paperId}/review`, { method: "POST", body: JSON.stringify({ review: value }) });
    setPapers((current) => current.map((paper) => paper.id === paperId ? { ...paper, review: value } : paper));
  };
  const statusLabel = run ? ({ queued: "排队中", running: "运行中", completed: "已完成", failed: "失败" } as Record<string, string>)[run.status] || run.status : "未运行";
  const reviewed = useMemo(() => papers.filter((paper) => paper.review !== "unreviewed").length, [papers]);

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">LA</div><div><strong>Literature Agent</strong><span>Academic discovery</span></div></div>
      <nav>
        <button className={activeView === "workspace" ? "active" : ""} onClick={() => setActiveView("workspace")}><LayoutList size={17} />工作台</button>
        <button className={activeView === "prompts" ? "active" : ""} onClick={() => setActiveView("prompts")}><Sparkles size={17} />Prompt 版本</button>
        <button className={activeView === "settings" ? "active" : ""} onClick={() => setActiveView("settings")}><Settings2 size={17} />设置</button>
      </nav>
      <div className="sidebar-foot"><CircleHelp size={16} /> <span>本地优先 · Alpha</span></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div><p className="eyebrow">RESEARCH WORKSPACE</p><h1>{activeView === "workspace" ? "文献发现工作台" : activeView === "prompts" ? "Prompt 版本" : "设置"}</h1></div><div className="connection"><span className="status-dot" />本地服务已连接</div></header>
      {activeView === "workspace" && <>
        <section className="control-grid">
          <div className="panel create-panel"><div className="panel-heading"><div><span className="section-index">01</span><h2>创建研究任务</h2></div><SlidersHorizontal size={18} /></div><label>任务名称<input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：Agentic RAG 文献追踪" /></label><label>研究主题<textarea value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="描述要抓取和筛选的研究主题" rows={3} /></label><div className="field-row"><label>检索语言<select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="bilingual">中英文</option><option value="zh">中文</option><option value="en">英文</option></select></label><label>目标数量<input type="number" min="1" max="100" value={targetCount} onChange={(e) => setTargetCount(Number(e.target.value))} /></label></div>{error && <p className="error">{error}</p>}<button className="primary-button" onClick={startTask}><Play size={16} />开始检索</button></div>
          <div className="panel task-panel"><div className="panel-heading"><div><span className="section-index">02</span><h2>最近任务</h2></div><button className="icon-button" title="刷新任务" onClick={loadTasks}><Plus size={17} /></button></div>{tasks.length === 0 ? <div className="empty-state"><FileText size={25} /><p>还没有研究任务</p><span>创建第一个主题后，Agent 运行记录会显示在这里。</span></div> : <div className="task-list">{tasks.map((task) => <button className={`task-row ${selectedTask?.id === task.id ? "selected" : ""}`} key={task.id} onClick={() => setSelectedTask(task)}><span className="task-number">{task.name.slice(0, 2)}</span><span><strong>{task.name}</strong><small>{task.topic}</small></span><ArrowUpRight size={15} /></button>)}</div>}</div>
        </section>
        <section className="workspace-section"><div className="section-toolbar"><div><span className="section-index">03</span><h2>结果</h2></div><div className="toolbar-meta"><span>{run ? statusLabel : "等待任务"}</span><span>{papers.length} papers</span><span>{reviewed} 已审核</span></div></div>{run && <div className="run-strip"><span className="status-dot" />Agent：{run.current_node || "准备中"}<span className="run-id">Run {run.id.slice(0, 8)}</span></div>}{papers.length === 0 ? <div className="results-empty"><BookOpen size={30} /><strong>{run ? "Agent 正在整理结果" : "选择一个任务开始"}</strong><span>结果会在检索、去重和摘要完成后出现在这里。</span></div> : <div className="paper-table"><div className="table-head"><span>论文</span><span>来源</span><span>相关性</span><span>状态</span></div>{papers.map((paper) => <article className="paper-row" key={paper.id}><div><div className="paper-title">{paper.title}</div><div className="paper-authors">{paper.authors.join(", ")} · {paper.published_date}</div><p>{String(paper.summary.relevance_reason || "")}</p><a href={paper.official_url} target="_blank">查看原文 <ArrowUpRight size={13} /></a></div><span className="source-badge">{paper.source}</span><span className="score">{Math.round(paper.relevance_score * 100)}%</span><select value={paper.review} onChange={(e) => review(paper.id, e.target.value)}><option value="unreviewed">待审核</option><option value="read">精读</option><option value="save">保存</option><option value="background">背景</option><option value="ignore">忽略</option></select></article>)}</div>}</section>
      </>}
      {activeView === "prompts" && <section className="simple-section"><div className="section-toolbar"><div><span className="section-index">04</span><h2>内置 Prompt</h2></div></div><div className="prompt-grid"><div className="prompt-card"><span>query_planner.v1</span><strong>Query Planner</strong><p>将研究主题转换为学术检索计划、同义词和来源路由。</p><button className="secondary-button">查看内容</button></div><div className="prompt-card"><span>literature_summarizer.v1</span><strong>Literature Summarizer</strong><p>从标题和摘要生成问题、方法、发现、局限与研究用途。</p><button className="secondary-button">查看内容</button></div></div></section>}
      {activeView === "settings" && <section className="simple-section"><div className="section-toolbar"><div><span className="section-index">05</span><h2>连接设置</h2></div></div><div className="settings-list"><div><strong>模型提供商</strong><span>通过后端 .env 配置 OpenAI-compatible API</span></div><div><strong>文献来源</strong><span>Fixture（开发模式）；OpenAlex 适配器可在 Beta 启用</span></div><div><strong>Zotero</strong><span>将在 Beta 版本接入本地导入和开放获取 PDF 下载</span></div></div></section>}
    </main>
  </div>;
}
