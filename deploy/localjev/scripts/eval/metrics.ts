import { mean, quantile, type EvaluationRow } from "./common";

export function wilson(correct: number, total: number): [number, number] | null {
  if (!total) return null;
  const z = 1.959963984540054, p = correct / total;
  const center = (p + z * z / (2 * total)) / (1 + z * z / total);
  const radius = z * Math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total);
  return [Math.max(0, center - radius), Math.min(1, center + radius)];
}

export function taskMetrics(rows: EvaluationRow[]) {
  const valid = rows.filter((r) => r.ok && r.probabilities !== null && r.prediction !== null);
  const correct = valid.filter((r) => r.prediction === r.gold).length;
  const nll: number[] = [], brier: number[] = [], absoluteError: number[] = [];
  const bins = Array.from({ length: 10 }, () => ({ n: 0, confidence: 0, correct: 0 }));
  for (const row of valid) {
    const p = row.probabilities!;
    nll.push(-Math.log(Math.max(1e-12, p[row.gold]!)));
    brier.push(row.task === "boolq"
      ? (p[1]! - row.gold) ** 2
      : p.reduce((sum, probability, i) => sum + (probability - Number(i === row.gold)) ** 2, 0));
    if (row.score !== null) absoluteError.push(Math.abs(row.score - row.gold));
    // Confidence for calibration is top-class probability, NOT LocalJev's inverse entropy.
    const confidence = p[row.prediction!]!;
    const bin = bins[Math.min(9, Math.floor(confidence * 10))]!;
    bin.n++; bin.confidence += confidence; bin.correct += Number(row.prediction === row.gold);
  }
  const ece = valid.length ? bins.reduce((sum, b) => sum + (b.n ? Math.abs(b.correct - b.confidence) / valid.length : 0), 0) : null;
  const classCount = rows[0]?.labels.length ?? 0;
  const confusion = Array.from({ length: classCount }, () => Array<number>(classCount).fill(0));
  valid.forEach((r) => { confusion[r.gold]![r.prediction!]! += 1; });
  const macroF1 = classCount ? mean(confusion.map((r, c) => {
    const tp = r[c]!, fp = confusion.reduce((sum, x) => sum + x[c]!, 0) - tp;
    const fn = r.reduce((sum, x) => sum + x, 0) - tp;
    return 2 * tp + fp + fn ? 2 * tp / (2 * tp + fp + fn) : 0;
  })) : null;
  return {
    total: rows.length, valid: valid.length, correct,
    effectiveAccuracy: rows.length ? correct / rows.length : null,
    validAccuracy: valid.length ? correct / valid.length : null,
    effectiveAccuracy95Wilson: wilson(correct, rows.length),
    macroF1, brier: mean(brier), nll: mean(nll), ece,
    scoreMAE: mean(absoluteError), confusion,
  };
}

export function timingMetrics(rows: EvaluationRow[]) {
  const attempts = rows.flatMap((row) => row.attempts);
  const totalSeconds = rows.reduce((sum, row) => sum + row.elapsedMs, 0) / 1000;
  const rowTokens = (field: "inputTokens" | "outputTokens" | "cachedTokens") => rows.map((row) => row.attempts.reduce((sum, a) => sum + a[field], 0));
  const input = rowTokens("inputTokens"), cached = rowTokens("cachedTokens");
  return {
    requests: rows.length,
    failures: rows.filter((r) => !r.ok).length,
    firstPassValid: rows.filter((r) => r.ok && r.attempts.length === 1).length,
    retriedRequests: rows.filter((r) => r.attempts.length > 1).length,
    additionalAttempts: rows.reduce((sum, r) => sum + Math.max(0, r.attempts.length - 1), 0),
    latencyP50Ms: quantile(rows.map((r) => r.elapsedMs), .5),
    latencyP95Ms: quantile(rows.map((r) => r.elapsedMs), .95),
    latencyMeanMs: mean(rows.map((r) => r.elapsedMs)),
    totalSeconds,
    effectiveRequestsPerSecond: totalSeconds > 0 ? rows.filter((r) => r.ok).length / totalSeconds : null,
    inputTokensMean: mean(input), outputTokensMean: mean(rowTokens("outputTokens")),
    firstAttemptInputTokensMean: mean(rows.flatMap((r) => r.attempts[0] ? [r.attempts[0].inputTokens] : [])),
    reportedCachedFraction: input.reduce((a, b) => a + b, 0) ? cached.reduce((a, b) => a + b, 0) / input.reduce((a, b) => a + b, 0) : null,
    lengthLimitedAttempts: attempts.filter((a) => a.finishReason === "length").length,
    reasoningAttempts: attempts.filter((a) => a.reasoningCharacters > 0).length,
    warnings: [...new Set(attempts.flatMap((a) => a.warning ? [a.warning] : []))],
  };
}
