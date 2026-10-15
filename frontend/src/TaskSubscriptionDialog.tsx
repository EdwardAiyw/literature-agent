import { useEffect, useRef, useState, type FormEvent } from "react";
import { Mail, X } from "lucide-react";

export type SubscriptionSchedule = { recipient: string; schedule_time: string; timezone: string };

type SubscriptionTask = {
  name: string; topic: string; research_questions: string[]; language: string; output_language: string;
  target_count: number; sources: string[]; date_from: string; date_to: string;
  evidence_review: boolean; prompt_overrides: Record<string, string>;
};

const languages: Record<string, string> = { zh: "中文", en: "英文", bilingual: "中英文" };
const sourceNames: Record<string, string> = { semantic_scholar: "Semantic Scholar", openalex: "OpenAlex", crossref: "Crossref", arxiv: "arXiv", pubmed: "PubMed", fixture: "Fixture" };

export default function TaskSubscriptionDialog({ task, recipient, busy, onClose, onSave }: {
  task: SubscriptionTask; recipient: string; busy: boolean; onClose: () => void;
  onSave: (schedule: SubscriptionSchedule) => Promise<void>;
}) {
  const [schedule, setSchedule] = useState<SubscriptionSchedule>({ recipient, schedule_time: "08:00", timezone: "Asia/Hong_Kong" });
  const [error, setError] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const busyRef = useRef(busy);
  const closeRef = useRef(onClose);
  const submittingRef = useRef(false);
  busyRef.current = busy;
  closeRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    formRef.current?.querySelector<HTMLInputElement>("input")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) closeRef.current();
      if (event.key !== "Tab") return;
      const controls = Array.from(formRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)") || []);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); previous?.focus(); };
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || submittingRef.current) return;
    submittingRef.current = true;
    setError("");
    try { await onSave(schedule); } catch (error) { setError(String(error)); } finally { submittingRef.current = false; }
  };

  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <form ref={formRef} className="task-editor subscription-dialog" role="dialog" aria-modal="true" aria-labelledby="task-subscription-title" onSubmit={submit}>
      <div className="modal-heading"><h2 id="task-subscription-title">转为每日任务</h2><button type="button" className="icon-button" title="关闭" disabled={busy} onClick={onClose}><X size={17} /></button></div>
      <div className="subscription-task-summary">
        <strong>{task.name}</strong><p>{task.topic}</p>
        <dl><dt>检索范围</dt><dd>{task.date_from || "不限起始日期"} 至 {task.date_to || "不限结束日期"}</dd>
          <dt>语言与篇数</dt><dd>检索：{languages[task.language] || task.language} · 输出：{languages[task.output_language] || task.output_language} · 每次最多 {task.target_count} 篇</dd>
          <dt>文献来源</dt><dd>{task.sources.map((source) => sourceNames[source] || source).join("、")}</dd>
          <dt>高级配置</dt><dd>{task.research_questions?.length || 0} 个研究问题 · 证据审查{task.evidence_review ? "已启用" : "未启用"} · {Object.keys(task.prompt_overrides || {}).length} 个 Prompt 覆盖</dd></dl>
      </div>
      <p className="section-lead">沿用以上研究配置和日期范围，保留任务历史。补充投递安排即可保存。</p>
      <label>收件人<input type="email" required maxLength={320} disabled={busy} value={schedule.recipient} onChange={(event) => setSchedule({ ...schedule, recipient: event.target.value })} /></label>
      <div className="schedule-fields"><label>每日执行时间<input type="time" required disabled={busy} value={schedule.schedule_time} onChange={(event) => setSchedule({ ...schedule, schedule_time: event.target.value })} /></label>
        <label>时区<input required maxLength={80} disabled={busy} value={schedule.timezone} onChange={(event) => setSchedule({ ...schedule, timezone: event.target.value })} /></label></div>
      <p className="subscription-schedule-note">每日自动执行需要在“设置 → 自动运行与维护”注册自动任务，并保持电脑可运行。保存后可在“每日订阅”查看和手动运行。</p>
      {error && <p className="run-error" role="alert">{error}</p>}
      <div className="modal-actions"><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>取消</button><button type="submit" className="primary-button" disabled={busy}><Mail size={15} />{busy ? "正在转换…" : "保存每日任务"}</button></div>
    </form>
  </div>;
}
