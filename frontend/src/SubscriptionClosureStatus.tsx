export type AutoPause = {
  run_id: string;
  paused_at: string;
  reason: "all_delivered" | "no_relevant_papers" | "user_requested";
  status: "queued" | "running" | "failed" | "completed";
  error: string;
  paper_count: number;
  report_ready: boolean;
};

export default function SubscriptionClosureStatus({ pause, enabled, reportUrl, retry, busy }: {
  pause?: AutoPause | null; enabled: boolean; reportUrl: string; retry: () => void; busy: boolean;
}) {
  if (!pause) return null;
  const status = { queued: "等待汇总", running: "正在汇总并发送", failed: "通知或汇总失败", completed: "历史汇总已发送" }[pause.status];
  return <div className="closure-status">
    <small>{enabled ? "上次暂停" : pause.reason === "user_requested" ? "已暂停" : "已自动暂停"} · {pause.reason === "user_requested" ? "按用户要求暂停并汇总" : pause.reason === "all_delivered" ? "候选文献均已推送" : "无符合要求的新增文献"} · {new Date(pause.paused_at).toLocaleString()}</small>
    <small>{status} · 历史文献 {pause.paper_count} 篇</small>
    {pause.error && <small role="alert">{pause.error}</small>}
    <div className="row-actions">
      {pause.report_ready && <a className="secondary-button small-button" href={reportUrl} download>下载完整汇总</a>}
      {pause.status === "failed" && <button className="secondary-button small-button" disabled={busy} onClick={retry}>{busy ? "正在提交…" : "重试通知与汇总"}</button>}
    </div>
  </div>;
}
