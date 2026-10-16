import { describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { hashOrder, quantile, type EvaluationRow, type Example, type Suite } from "../scripts/eval/common";
import { balancedSample, makeState } from "../scripts/eval/data";
import { taskMetrics, timingMetrics, wilson } from "../scripts/eval/metrics";
import { answerValues } from "../scripts/eval/run";
import { report } from "../scripts/eval/report";

const example: Example = {
  id: "boolq:validation:0", row: 0, task: "boolq", text: "The target evidence remains intact.",
  gold: 1, labels: ["no", "yes"], question: { type: "noul", instructions: "Is this true?", criteria: null },
};
const suite: Suite = { version: 1, seed: 42, samplesPerTask: 20, sources: [], examples: [example], background: ["One unrelated passage here.", "Another passage with several irrelevant words."] };
function row(overrides: Partial<EvaluationRow> = {}): EvaluationRow {
  return {
    key: "model|0|boolq:validation:0", model: "model", backgroundWords: 0,
    task: "boolq", exampleId: example.id, gold: 1, labels: ["no", "yes"],
    stateHash: "example", stateWords: 6, elapsedMs: 1000, ok: true,
    answer: { type: "noul", noul: .8 }, probabilities: [.2, .8], prediction: 1,
    score: null, error: null,
    attempts: [{ ms: 990, status: 200, inputTokens: 100, outputTokens: 20, cachedTokens: 0, backendSeconds: .9, finishReason: "stop", reasoningCharacters: 0, warning: null, requestHash: "request", responseHash: "response" }],
    ...overrides,
  };
}

describe("evaluation data", () => {
  test("hash sampling is deterministic, stratified, and without replacement", () => {
    const population = Array.from({ length: 100 }, (_, i) => ({ ...example, id: `row-${i}`, gold: i % 2 }));
    const sample = balancedSample(population, 20, 42);
    expect(sample).toEqual(balancedSample(population, 20, 42));
    expect(sample.filter((e) => e.gold === 0)).toHaveLength(10);
    expect(new Set(sample.map((e) => e.id)).size).toBe(20);
    expect(sample).not.toEqual(balancedSample(population, 20, 43));
    expect(() => balancedSample(population, 21, 42)).toThrow();
    expect(() => balancedSample(population, 102, 42)).toThrow();
    expect(hashOrder(population, (e) => e.id, "a")).toHaveLength(100);
  });
  test("context variants preserve gold evidence, add the requested words, and omit labels", () => {
    const short = makeState(example, 0, suite);
    const long = makeState(example, 2048, suite);
    expect(short).toBe(`TARGET:\n${example.text}\nEND TARGET`);
    expect(long).toContain(short);
    expect(long.split("BACKGROUND (irrelevant):")).toHaveLength(3);
    const added = long.replace(short, "").replaceAll("BACKGROUND (irrelevant):", "").trim().split(/\s+/);
    expect(added).toHaveLength(2048);
    expect(long).toBe(makeState(example, 2048, suite));
    expect(long).not.toContain(example.id);
    expect(makeState({ ...example, gold: 0 }, 2048, suite)).toBe(long);
  });
  test("choice probabilities follow semantic labels, not shuffled presentation order", () => {
    const e: Example = { ...example, task: "ag_news", labels: ["world", "sports"], gold: 0 };
    expect(answerValues({ type: "choice", choice: "world", probabilities: { sports: .2, world: .8 }, confidence: .2 }, e)).toEqual({ probabilities: [.8, .2], prediction: 0, score: null });
  });
  test("score accuracy uses argmax, while score error uses the expected value", () => {
    const e: Example = { ...example, task: "sst5", labels: ["negative", "neutral", "positive"], gold: 0 };
    const result = answerValues({ type: "score", score: .8, probabilities: { "0": .5, "1": .2, "2": .3 }, legend: {}, confidence: 0 }, e);
    expect(result.prediction).toBe(0);
    expect(result.score).toBe(.8);
    expect(answerValues({ type: "noul", noul: .5 }, example).prediction).toBe(1);
  });
});

describe("evaluation metrics", () => {
  test("binary Brier, NLL and ECE have known values", () => {
    const m = taskMetrics([row()]);
    expect(m.effectiveAccuracy).toBe(1);
    expect(m.brier).toBeCloseTo(.04);
    expect(m.nll).toBeCloseTo(-Math.log(.8));
    expect(m.ece).toBeCloseTo(.2);
  });
  test("failures count as wrong, not as missing or uniform predictions", () => {
    const m = taskMetrics([row(), row({ key: "failed", ok: false, probabilities: null, prediction: null, answer: null, error: "timeout" })]);
    expect(m.total).toBe(2);
    expect(m.valid).toBe(1);
    expect(m.validAccuracy).toBe(1);
    expect(m.effectiveAccuracy).toBe(.5);
    expect(m.brier).toBeCloseTo(.04);
  });
  test("multiclass Brier, score MAE and zero-probability clipping", () => {
    const m = taskMetrics([row({ task: "sst5", labels: ["a", "b", "c"], gold: 0, probabilities: [.5, .2, .3], prediction: 0, score: .8 })]);
    expect(m.brier).toBeCloseTo(.38);
    expect(m.scoreMAE).toBeCloseTo(.8);
    expect(taskMetrics([row({ probabilities: [1, 0], prediction: 0 })]).nll).toBeCloseTo(-Math.log(1e-12));
  });
  test("latency includes retries and failures; tokens sum all attempts", () => {
    const r = row();
    const m = timingMetrics([r, row({ elapsedMs: 3000, ok: false, attempts: [r.attempts[0]!, r.attempts[0]!] })]);
    expect(m.latencyP50Ms).toBe(2000);
    expect(m.latencyP95Ms).toBeCloseTo(2900);
    expect(m.failures).toBe(1);
    expect(m.retriedRequests).toBe(1);
    expect(m.inputTokensMean).toBe(150);
    expect(m.outputTokensMean).toBe(30);
    expect(m.firstPassValid).toBe(1);
  });
  test("empty metrics are absent, never spuriously perfect", () => {
    expect(taskMetrics([]).effectiveAccuracy).toBeNull();
    expect(taskMetrics([]).ece).toBeNull();
    expect(timingMetrics([]).latencyMeanMs).toBeNull();
    expect(quantile([], .5)).toBeNull();
    expect(wilson(0, 0)).toBeNull();
    expect(wilson(20, 40)![0]).toBeCloseTo(.352, 2);
    expect(wilson(20, 40)![1]).toBeCloseTo(.648, 2);
  });
  test("reports are regenerable and mark incomplete matrices", async () => {
    const directory = await mkdtemp(join(tmpdir(), "localjev-eval-test-"));
    try {
      await Bun.write(join(directory, "manifest.json"), JSON.stringify({ runId: "test", config: { models: ["model"], backgroundWords: [0, 2048], samplesPerTask: 40, seed: 42, temperature: 0, maxOutputTokens: 256, malformedRetries: 2, cacheMode: "bust-prefix" }, environment: { bun: "test", cpu: "test", memoryGiB: 64 }, examples: [example], expectedResults: 2 }));
      await Bun.write(join(directory, "results.jsonl"), JSON.stringify(row()) + "\n");
      await Bun.write(join(directory, "warmups.jsonl"), "");
      await report(directory);
      const first = await Bun.file(join(directory, "report.md")).text();
      expect(first).toContain("PARTIAL");
      await report(directory);
      expect(await Bun.file(join(directory, "report.md")).text()).toBe(first);
      expect((await Bun.file(join(directory, "summary.json")).json()).complete).toBe(false);
      await appendDuplicate(directory);
      await expect(report(directory)).rejects.toThrow("Duplicate results");
    } finally { await rm(directory, { recursive: true, force: true }); }
  });
});
async function appendDuplicate(directory: string) {
  await Bun.write(join(directory, "results.jsonl"), [row(), row()].map((r) => JSON.stringify(r)).join("\n") + "\n");
}
