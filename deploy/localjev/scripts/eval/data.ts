import { mkdir } from "node:fs/promises";
import { parquetReadObjects } from "hyparquet";
import { compressors } from "hyparquet-compressors";
import { hashOrder, hashSeed, sha256, TASKS, type EvalConfig, type Example, type Source, type Suite } from "./common";

export const SOURCES: Source[] = [
  {
    name: "ag_news-test", dataset: "fancyzhx/ag_news", split: "test",
    revision: "eb185aade064a813bc0b7f42de02595523103ca4",
    url: "https://huggingface.co/datasets/fancyzhx/ag_news/resolve/eb185aade064a813bc0b7f42de02595523103ca4/data/test-00000-of-00001.parquet",
    sha256: "71de87ec66bc5737752a2502204dfa6d7fe9856ade3ea444dc6317789a4f13fb", format: "parquet",
  },
  {
    name: "boolq-validation", dataset: "google/boolq", split: "validation",
    revision: "35b264d03638db9f4ce671b711558bf7ff0f80d5",
    url: "https://huggingface.co/datasets/google/boolq/resolve/35b264d03638db9f4ce671b711558bf7ff0f80d5/data/validation-00000-of-00001.parquet",
    sha256: "52355d11524b4b874a9b9dcc278feb10f672d52c4f4eff9872e695ede59820f8", format: "parquet",
  },
  {
    name: "sst5-test", dataset: "SetFit/sst5", split: "test",
    revision: "e51bdcd8cd3a30da231967c1a249ba59361279a3",
    url: "https://huggingface.co/datasets/SetFit/sst5/resolve/e51bdcd8cd3a30da231967c1a249ba59361279a3/test.jsonl",
    sha256: "1384216112a34f3d70b6fa210762f3399bb080410c0456ac6e54a5cb413f04b2", format: "jsonl",
  },
  {
    name: "boolq-background", dataset: "google/boolq", split: "train (passages only; no labels/questions)",
    revision: "35b264d03638db9f4ce671b711558bf7ff0f80d5",
    url: "https://huggingface.co/datasets/google/boolq/resolve/35b264d03638db9f4ce671b711558bf7ff0f80d5/data/train-00000-of-00001.parquet",
    sha256: "4f028e992c0bd4df30b9f056f4946b64f5c23028034ff0ed5ea467d8538cc623", format: "parquet",
  },
];

async function download(source: Source): Promise<Record<string, unknown>[]> {
  await mkdir(".eval-cache/sources", { recursive: true });
  const path = `.eval-cache/sources/${source.name}.${source.format}`;
  let bytes: Uint8Array;
  if (await Bun.file(path).exists()) {
    bytes = await Bun.file(path).bytes();
  } else {
    console.log(`Downloading ${source.dataset} ${source.split}`);
    const response = await fetch(source.url, { signal: AbortSignal.timeout(120_000) });
    if (!response.ok) throw new Error(`Dataset download failed: ${response.status} ${source.url}`);
    bytes = new Uint8Array(await response.arrayBuffer());
  }
  if (sha256(bytes) !== source.sha256) throw new Error(`Checksum mismatch: ${source.name}; refusing changed data`);
  await Bun.write(path, bytes);
  if (source.format === "jsonl") {
    return new TextDecoder().decode(bytes).trim().split("\n").map((line) => JSON.parse(line));
  }
  return parquetReadObjects({ file: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer, compressors });
}

export function balancedSample(examples: Example[], n: number, seed: number): Example[] {
  const labels = [...new Set(examples.map((e) => e.gold))].sort((a, b) => a - b);
  if (n % labels.length) throw new Error("Sample count is not divisible by class count");
  const perClass = n / labels.length;
  return labels.flatMap((gold) => {
    const group = hashOrder(examples.filter((e) => e.gold === gold), (e) => e.id, `${seed}:sample`);
    if (group.length < perClass) throw new Error(`Not enough examples for class ${gold}`);
    return group.slice(0, perClass);
  });
}

const FOCUS = "Evaluate only the text in the TARGET section of the document. Ignore the unrelated BACKGROUND sections. ";
export async function prepareSuite(config: EvalConfig): Promise<Suite> {
  // Always verify source bytes. Cached input text is never trusted without its hash.
  const [news, boolq, sentiment, backgroundRows] = await Promise.all(SOURCES.map(download));
  const newsLabels = ["world", "sports", "business", "science_technology"];
  const newsDescriptions = ["World news, politics, international affairs", "Sports and athletic competitions", "Business, finance, economics", "Science, technology, computing"];
  const levels = ["very negative", "negative", "neutral", "positive", "very positive"];
  const all: Example[][] = [
    news!.map((row, index) => {
      if (typeof row.text !== "string" || !["number", "bigint"].includes(typeof row.label) || !Number.isInteger(Number(row.label)) || Number(row.label) < 0 || Number(row.label) > 3) throw new Error("Unexpected AG News schema");
      // Shuffle label order deterministically per example; do not always favor the same slot.
      const options = hashOrder(newsLabels, (label) => label, `${config.seed}:options:${index}`);
      return {
        id: `ag_news:test:${index}`, task: "ag_news", row: index, text: row.text,
        gold: Number(row.label), labels: newsLabels,
        question: { type: "choice", instructions: FOCUS + "What is the main news topic? Choose the single best category.",
          criteria: Object.fromEntries(options.map((label) => [label, newsDescriptions[newsLabels.indexOf(label)]!])) },
      };
    }),
    boolq!.map((row, index) => {
      if (typeof row.passage !== "string" || typeof row.question !== "string" || typeof row.answer !== "boolean") throw new Error("Unexpected BoolQ schema");
      return {
        id: `boolq:validation:${index}`, task: "boolq", row: index, text: row.passage,
        gold: Number(row.answer), labels: ["no", "yes"],
        question: { type: "noul", instructions: FOCUS + `According to the passage, ${row.question}?`, criteria: null },
      };
    }),
    sentiment!.map((row, index) => {
      if (typeof row.text !== "string" || !Number.isInteger(row.label) || row.label_text !== levels[Number(row.label)]) throw new Error("Unexpected SST-5 label mapping");
      return {
        id: `sst5:test:${index}`, task: "sst5", row: index, text: row.text,
        gold: Number(row.label), labels: levels,
        question: { type: "score", instructions: FOCUS + "Rate the overall sentiment of this movie review, from very negative (0) to very positive (4).", criteria: levels },
      };
    }),
  ];
  const selected = all.map((examples) => hashOrder(balancedSample(examples, config.samplesPerTask, config.seed), (e) => e.id, `${config.seed}:execution`));
  // Interleave tasks to spread heating/drift over the same execution positions.
  const examples = Array.from({ length: config.samplesPerTask }, (_, index) => TASKS.map((_, task) => selected[task]![index]!)).flat();
  const targetTexts = new Set(examples.map((e) => e.text));
  const background = [...new Set(backgroundRows!.map((row) => {
    if (typeof row.passage !== "string") throw new Error("Unexpected background schema");
    return row.passage;
  }))].filter((text) => !targetTexts.has(text));
  const suite: Suite = { version: 1, seed: config.seed, samplesPerTask: config.samplesPerTask, sources: SOURCES, examples, background };
  await Bun.write(`.eval-cache/suite-${config.seed}-${config.samplesPerTask}.json`, JSON.stringify(suite));
  return suite;
}

export function makeState(example: Example, backgroundWords: number, suite: Suite): string {
  const tokens: string[] = [];
  if (backgroundWords && !suite.background.length) throw new Error("Missing background corpus");
  let index = hashSeed(`${suite.seed}:background:${example.id}`) % suite.background.length;
  while (tokens.length < backgroundWords) {
    tokens.push(...suite.background[index]!.split(/\s+/).filter(Boolean));
    index = (index + 1) % suite.background.length;
  }
  const words = tokens.slice(0, backgroundWords);
  const split = Math.floor(words.length / 2);
  return [
    words.length ? `BACKGROUND (irrelevant):\n${words.slice(0, split).join(" ")}` : "",
    `TARGET:\n${example.text}\nEND TARGET`,
    words.length ? `BACKGROUND (irrelevant):\n${words.slice(split).join(" ")}` : "",
  ].filter(Boolean).join("\n\n");
}
