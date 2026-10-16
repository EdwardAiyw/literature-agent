import { join } from "node:path";
import { TASKS, mean, sha256, type EvalConfig, type EvaluationRow } from "./common";
import { taskMetrics, timingMetrics } from "./metrics";

const fixed = (v: number | null, digits = 3) => v === null ? "—" : v.toFixed(digits);
const percent = (v: number | null) => v === null ? "—" : `${(100 * v).toFixed(1)}%`;
export async function report(directory: string): Promise<void> {
  const manifest = await Bun.file(join(directory, "manifest.json")).json();
  const config = manifest.config as EvalConfig;
  const text = await Bun.file(join(directory, "results.jsonl")).text();
  const rows: EvaluationRow[] = text.trim() ? text.trim().split("\n").map((line) => JSON.parse(line)) : [];
  if (new Set(rows.map((r) => r.key)).size !== rows.length) throw new Error("Duplicate results: refusing biased report");
  const cells = config.models.flatMap((model) => config.backgroundWords.map((words) => {
    const selected = rows.filter((r) => r.model === model && r.backgroundWords === words);
    const tasks = Object.fromEntries(TASKS.map((task) => [task, taskMetrics(selected.filter((r) => r.task === task))]));
    return {
      model, backgroundWords: words,
      complete: selected.length === manifest.examples.length,
      macroTaskAccuracy: mean(TASKS.flatMap((t) => tasks[t]!.effectiveAccuracy !== null ? [tasks[t]!.effectiveAccuracy!] : [])),
      tasks, timing: timingMetrics(selected),
    };
  }));
  const paired = config.models.map((model) => ({
    model,
    comparisons: config.backgroundWords.filter((n) => n !== 0).map((words) => {
      const baseline = new Map(rows.filter((r) => r.model === model && r.backgroundWords === 0).map((r) => [r.exampleId, r]));
      const longer = rows.filter((r) => r.model === model && r.backgroundWords === words);
      let bothValid = 0, changed = 0, lost = 0, gained = 0;
      for (const after of longer) {
        const before = baseline.get(after.exampleId);
        if (!before?.ok || !after.ok) continue;
        bothValid++;
        changed += Number(before.prediction !== after.prediction);
        lost += Number(before.prediction === before.gold && after.prediction !== after.gold);
        gained += Number(before.prediction !== before.gold && after.prediction === after.gold);
      }
      return { backgroundWords: words, bothValid, predictionsChanged: changed, correctToWrong: lost, wrongToCorrect: gained };
    }),
  }));
  const reportCodeHashes = Object.fromEntries(await Promise.all(["scripts/eval/report.ts", "scripts/eval/metrics.ts"].map(async (path) => [path, sha256(await Bun.file(path).bytes())])));
  const summary = { runId: manifest.runId, results: rows.length, expectedResults: manifest.expectedResults, complete: rows.length === manifest.expectedResults, reportCodeHashes, cells, paired };
  await Bun.write(join(directory, "summary.json"), JSON.stringify(summary, null, 2) + "\n");
  const lines = [
    `# LocalJev bake-off: ${manifest.runId}`, "",
    `Status: **${summary.complete ? "complete" : "PARTIAL"}** (${summary.results}/${summary.expectedResults} measured requests).`, "",
    `Runtime: Bun ${manifest.environment.bun}; ${manifest.environment.cpu}; ${manifest.environment.memoryGiB} GiB RAM; oMLX ${manifest.backendVersion ?? "unknown"}.`,
    `Seed ${config.seed}; configured ${config.samplesPerTask} balanced examples/task; selected ${manifest.examples.length} total examples${manifest.examples.length < config.samplesPerTask * 3 ? " (**LIMITED PILOT, not necessarily balanced**)" : ""}; temperature ${config.temperature}; max output ${config.maxOutputTokens}; up to ${config.malformedRetries} corrective retries; one request in flight.`,
    `Cache policy: **${config.cacheMode}**. Background sizes are **words added**, not context-window settings or exact token budgets. Token counts below are backend-reported.`, "",
    "## Quality × model × input length", "",
    "Accuracy counts failed requests as wrong. SST-5 accuracy uses the highest-probability level; MAE uses the expected score. Macro accuracy weights the three tasks equally.", "",
    "| Model | Background words | AG News accuracy | BoolQ accuracy | SST-5 accuracy | SST-5 MAE ↓ | Macro accuracy | Failures |",
    "|---|---:|---:|---:|---:|---:|---:|---:|",
  ];
  for (const c of cells) {
    lines.push(`| ${c.model} | ${c.backgroundWords} | ${percent(c.tasks.ag_news!.effectiveAccuracy)} | ${percent(c.tasks.boolq!.effectiveAccuracy)} | ${percent(c.tasks.sst5!.effectiveAccuracy)} | ${fixed(c.tasks.sst5!.scoreMAE)} | ${percent(c.macroTaskAccuracy)} | ${c.timing.failures}/${c.timing.requests} |`);
  }
  lines.push("", "## Decision latency × model × input length", "",
    "Wall time covers the real LocalJev Engine, tokenization/inference upstream, JSON parsing and corrective retries. Warm-ups/model loading are excluded. Latency includes failed requests. This non-streaming benchmark does **not measure TTFT**. No localhost Bun HTTP hop is included.", "",
    "| Model | Background words | p50 (s) ↓ | p95 (s) ↓ | Mean (s) ↓ | Input tokens, first attempt | Output tokens incl. retries | Retried | Cached input |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|");
  for (const c of cells) {
    const t = c.timing;
    lines.push(`| ${c.model} | ${c.backgroundWords} | ${fixed(t.latencyP50Ms === null ? null : t.latencyP50Ms / 1000)} | ${fixed(t.latencyP95Ms === null ? null : t.latencyP95Ms / 1000)} | ${fixed(t.latencyMeanMs === null ? null : t.latencyMeanMs / 1000)} | ${fixed(t.firstAttemptInputTokensMean, 0)} | ${fixed(t.outputTokensMean, 1)} | ${t.retriedRequests}/${t.requests} | ${percent(t.reportedCachedFraction)} |`);
  }
  lines.push("", "## Per-task uncertainty and calibration", "",
    "Wilson 95% intervals are indicative, unadjusted for multiple comparisons and class-stratified sampling. Calibration/F1/MAE are conditional on valid responses: always inspect coverage above. ECE uses 10 equal-width bins and **max class probability**, not LocalJev's entropy-based confidence. Tiny samples make ECE noisy. Brier is `(p_yes-y)²` for BoolQ and the sum over class errors for multiclass tasks; do not compare its magnitude across tasks. NLL clips probabilities at 1e-12; all probability metrics concern self-reported, normalized model outputs.", "",
    "| Model | Background | Task | Correct / total | Accuracy 95% interval | Macro F1 | Brier ↓ | NLL ↓ | ECE ↓ |",
    "|---|---:|---|---:|---|---:|---:|---:|---:|");
  for (const c of cells) for (const task of TASKS) {
    const m = c.tasks[task]!;
    lines.push(`| ${c.model} | ${c.backgroundWords} | ${task} | ${m.correct}/${m.total} | ${m.effectiveAccuracy95Wilson?.map(percent).join("–") ?? "—"} | ${fixed(m.macroF1)} | ${fixed(m.brier)} | ${fixed(m.nll)} | ${fixed(m.ece)} |`);
  }
  lines.push("", "## Paired background effect", "", "Only pairs with valid responses in both conditions are counted.", "",
    "| Model | Added words | Valid pairs | Prediction changed | Correct → wrong | Wrong → correct |",
    "|---|---:|---:|---:|---:|---:|");
  for (const p of paired) for (const c of p.comparisons) lines.push(`| ${p.model} | ${c.backgroundWords} | ${c.bothValid} | ${c.predictionsChanged} | ${c.correctToWrong} | ${c.wrongToCorrect} |`);
  lines.push("", "## Output diagnostics", "",
    "Grammar-valid JSON can still contain semantically invalid probabilities (such as all zeros). Retries recover some of these; length-limited attempts and reasoning are shown separately. No warnings returned is not proof of schema enforcement.", "",
    "| Model | Background | First-pass valid / requests | Additional attempts | Length-limited attempts | Reasoning attempts |",
    "|---|---:|---:|---:|---:|---:|");
  for (const c of cells) {
    const t = c.timing;
    lines.push(`| ${c.model} | ${c.backgroundWords} | ${t.firstPassValid}/${t.requests} | ${t.additionalAttempts} | ${t.lengthLimitedAttempts} | ${t.reasoningAttempts} |`);
  }
  const errors = new Map<string, number>();
  for (const row of rows.filter((r) => !r.ok)) errors.set(row.error ?? "unknown", (errors.get(row.error ?? "unknown") ?? 0) + 1);
  if (errors.size) lines.push("", "Terminal errors:", ...[...errors].map(([message, n]) => `- ${n} × ${message.replaceAll("\n", " ")}`));
  const warmups = await Bun.file(join(directory, "warmups.jsonl")).text();
  lines.push("", "## Excluded warm-ups / first-call overhead", "",
    "The first call may include model loading/eviction/compilation; these are **not isolated cold-load measurements**. Two short warm-ups do not guarantee every prompt shape is compiled. New model load behavior and runtime settings can affect the first calls.", "",
    "| Model | Warm-up | Seconds | Valid |", "|---|---:|---:|---|");
  for (const w of warmups.trim().split("\n").filter(Boolean).map((l) => JSON.parse(l))) lines.push(`| ${w.model} | ${w.index + 1} | ${(w.ms / 1000).toFixed(3)} | ${w.ok} |`);
  lines.push("", "## Caveats and provenance", "",
    "- Public benchmark contamination is possible. These are held-out dataset splits, not guaranteed unseen pretraining data; this is not a Jev-vs-model benchmark.",
    "- Balanced sampling changes class priors. The background condition is an artificial distraction/prefill stress test, not a new natural long-document dataset. The complete target stays in the middle; no evidence is truncated.",
    "- Model order is fixed to minimize reload overhead; conditions are interleaved per example. Thermal/runtime drift and one-machine measurements limit generalization. No concurrency/throughput saturation or repeated-run variance study.",
    "- Same LocalJev prompts/settings are requested; tokenizers, schema enforcement, forced model settings, quantization recipes and backend implementations can differ. The manifest records what could be inspected; unseen server overrides remain a limitation.",
    "- Maximum context limits were NOT changed. This measures real input lengths. Retrying adds extra input/output tokens and latency.",
    "- See manifest.json for pinned source revisions/checksums, selected row IDs, code hashes, settings and machine metadata. results.jsonl contains per-example outputs/timing without source passages, credentials, or prompts. See docs/evaluation.md for reproduction and dataset licensing.", "");
  await Bun.write(join(directory, "report.md"), lines.join("\n"));
}

if (import.meta.main) {
  const directory = process.argv[2];
  if (!directory) throw new Error("Usage: bun run scripts/eval/report.ts RUN_DIRECTORY");
  await report(directory);
  console.log(`Wrote ${directory}/report.md and summary.json`);
}
