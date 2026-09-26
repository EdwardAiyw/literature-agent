import http from "node:http";
import path from "node:path";
import { pathToFileURL } from "node:url";

const runtimeRoot = process.env.LOCALJEV_RUNTIME_ROOT || "D:\\localjev-runtime";
const modelPath = process.env.LOCALJEV_MODEL_PATH ||
  path.join(runtimeRoot, "models", "qwen2.5-3b-instruct-q4_k_m.gguf");
const modelName = process.env.LOCALJEV_MODEL_NAME || "qwen2.5-3b-instruct-q4_k_m";
const host = process.env.LOCALJEV_UPSTREAM_HOST || "127.0.0.1";
const port = Number.parseInt(process.env.LOCALJEV_UPSTREAM_PORT || "8000", 10);
const contextSize = Number.parseInt(process.env.LOCALJEV_CONTEXT_SIZE || "8192", 10);
const moduleUrl = pathToFileURL(
  path.join(runtimeRoot, "node_modules", "node-llama-cpp", "dist", "index.js"),
).href;
const { getLlama, LlamaChatSession } = await import(moduleUrl);

console.log(`[upstream] Loading ${modelName} from ${modelPath}`);
const llama = await getLlama({
  gpu: "vulkan",
  skipDownload: true,
  progressLogs: "stderr",
});
const model = await llama.loadModel({
  modelPath,
  gpuLayers: { fitContext: { contextSize } },
});
const context = await model.createContext({ contextSize, sequences: 1 });
console.log(`[upstream] Model loaded with ${context.contextSize} context tokens`);

let queueTail = Promise.resolve();

function serialize(operation) {
  const run = queueTail.then(operation, operation);
  queueTail = run.catch(() => {});
  return run;
}

function sendJson(response, status, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  response.end(body);
}

function errorPayload(message, type = "invalid_request_error") {
  return { error: { message, type, param: null, code: null } };
}

async function readJson(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 2 * 1024 * 1024) throw new Error("Request body exceeds 2 MiB");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function messageText(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .filter((part) => part && part.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n");
}

function prepareMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error("messages must be a non-empty array");
  }
  const systemPrompt = messages
    .filter((message) => message?.role === "system")
    .map((message) => messageText(message.content))
    .filter(Boolean)
    .join("\n\n");
  const prompt = messages
    .filter((message) => message?.role !== "system")
    .map((message) => `${message.role || "user"}: ${messageText(message.content)}`)
    .join("\n\n");
  if (!prompt) throw new Error("messages contain no user content");
  return { systemPrompt, prompt };
}

async function complete(body) {
  if (!body || typeof body !== "object") throw new Error("request body must be an object");
  if (body.model !== modelName) throw new Error(`model must be '${modelName}'`);

  const { systemPrompt, prompt } = prepareMessages(body.messages);
  const schema = body.response_format?.type === "json_schema"
    ? body.response_format.json_schema?.schema
    : null;
  if (!schema || typeof schema !== "object") {
    throw new Error("response_format.type=json_schema with a schema is required");
  }

  const grammar = await llama.createGrammarForJsonSchema(schema);
  const sequence = context.getSequence();
  const session = new LlamaChatSession({
    contextSequence: sequence,
    systemPrompt,
    autoDisposeSequence: true,
  });
  try {
    const maxTokens = Math.min(Math.max(Number(body.max_tokens) || 512, 1), 4096);
    const temperature = Math.min(Math.max(Number(body.temperature) || 0, 0), 2);
    const answer = await session.prompt(prompt, {
      grammar,
      maxTokens,
      temperature,
      seed: Number.isInteger(body.seed) ? body.seed : undefined,
      trimWhitespaceSuffix: true,
    });
    const content = JSON.stringify(grammar.parse(answer));
    const promptTokens = model.tokenize(`${systemPrompt}\n${prompt}`).length;
    const completionTokens = model.tokenize(content).length;
    return {
      id: `chatcmpl-localjev-${Date.now()}`,
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model: modelName,
      choices: [{
        index: 0,
        message: { role: "assistant", content },
        finish_reason: "stop",
      }],
      usage: {
        prompt_tokens: promptTokens,
        completion_tokens: completionTokens,
        total_tokens: promptTokens + completionTokens,
      },
    };
  } finally {
    session.dispose();
  }
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${host}:${port}`);
  if (request.method === "GET" && url.pathname === "/health") {
    sendJson(response, 200, { status: "ok", backend: "node-llama-cpp-vulkan" });
    return;
  }
  if (request.method === "GET" && url.pathname === "/v1/models") {
    sendJson(response, 200, {
      object: "list",
      data: [{ id: modelName, object: "model", owned_by: "local" }],
    });
    return;
  }
  if (request.method === "POST" && url.pathname === "/v1/chat/completions") {
    try {
      const body = await readJson(request);
      const result = await serialize(() => complete(body));
      sendJson(response, 200, result);
    } catch (error) {
      console.error("[upstream] Completion failed", error);
      const invalid = error instanceof SyntaxError || /must|required|messages|model|response_format/.test(String(error));
      sendJson(response, invalid ? 400 : 500, errorPayload(error instanceof Error ? error.message : String(error)));
    }
    return;
  }
  sendJson(response, 404, errorPayload("Not found", "not_found_error"));
});

server.listen(port, host, () => {
  console.log(`[upstream] OpenAI-compatible API listening on http://${host}:${port}`);
});

async function shutdown(signal) {
  console.log(`[upstream] Received ${signal}; shutting down`);
  server.close();
  await context.dispose();
  await model.dispose();
  await llama.dispose();
  process.exit(0);
}

process.once("SIGINT", () => void shutdown("SIGINT"));
process.once("SIGTERM", () => void shutdown("SIGTERM"));
