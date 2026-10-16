export interface Settings {
  upstream: string;
  outputMode: "json_schema" | "json_object";
  upstreamApiKey: string;
  upstreamModel: string;
  apiKey: string;
  host: string;
  port: number;
  timeoutMs: number;
  maxOutputTokens: number;
  malformedRetries: number;
  temperature: number;
  maxInflight: number;
  maxQueue: number;
  questionsPerCall: number;
  outcomesPerCall: number;
}

function numberSetting(name: string, fallback: number, minimum: number): number {
  const raw = process.env[name];
  const value = raw === undefined ? fallback : Number(raw);
  if (!Number.isFinite(value) || value < minimum) {
    throw new Error(`${name} must be a number greater than or equal to ${minimum}`);
  }
  return value;
}

function integerSetting(name: string, fallback: number, minimum: number): number {
  const value = numberSetting(name, fallback, minimum);
  if (!Number.isInteger(value)) {
    throw new Error(`${name} must be an integer`);
  }
  return value;
}

export function loadSettings(
  overrides: Partial<Settings> = {},
): Settings {
  const outputMode = process.env.LOCALJEV_OUTPUT_MODE ?? "json_schema";
  if (!["json_schema", "json_object"].includes(outputMode)) throw new Error("Invalid LOCALJEV_OUTPUT_MODE");
  return {
    outputMode: outputMode as "json_schema" | "json_object",
    upstream: process.env.LOCALJEV_UPSTREAM ?? "http://127.0.0.1:8000",
    upstreamApiKey: process.env.LOCALJEV_UPSTREAM_API_KEY ?? "",
    upstreamModel:
      process.env.LOCALJEV_UPSTREAM_MODEL ??
      "diffusiongemma-26B-A4B-it-4bit",
    apiKey: process.env.LOCALJEV_API_KEY ?? "",
    host: process.env.LOCALJEV_HOST ?? "127.0.0.1",
    port: integerSetting("LOCALJEV_PORT", 8080, 1),
    timeoutMs: numberSetting("LOCALJEV_TIMEOUT", 180, 0.001) * 1_000,
    maxOutputTokens: integerSetting(
      "LOCALJEV_MAX_OUTPUT_TOKENS",
      2_048,
      1,
    ),
    malformedRetries: integerSetting("LOCALJEV_MALFORMED_RETRIES", 2, 0),
    temperature: numberSetting("LOCALJEV_TEMPERATURE", 0, 0),
    maxInflight: integerSetting("LOCALJEV_MAX_INFLIGHT", 2, 1),
    maxQueue: integerSetting("LOCALJEV_MAX_QUEUE", 64, 1),
    questionsPerCall: integerSetting(
      "LOCALJEV_QUESTIONS_PER_CALL",
      16,
      1,
    ),
    outcomesPerCall: integerSetting(
      "LOCALJEV_OUTCOMES_PER_CALL",
      128,
      1,
    ),
    ...overrides,
  };
}

export function apiBaseUrl(settings: Settings): string {
  const base = settings.upstream.replace(/\/+$/, "");
  return base.endsWith("/v1") ? base : `${base}/v1`;
}

export const MODEL_VERSION = "localjev-0.2";
export const MODEL_ALIASES = new Set([
  MODEL_VERSION,
  "localjev-latest",
  "jev-latest",
  "jev-preview",
]);
export const MODELS = [
  {
    name: "localjev-latest",
    description:
      "Alias for LocalJev 0.2, backed by a local OpenAI-compatible DiffusionGemma endpoint.",
    release_date: "2026-09-18",
  },
  {
    name: MODEL_VERSION,
    description:
      "Jev-compatible prompted probability inference with DiffusionGemma.",
    release_date: "2026-09-18",
  },
] as const;
