import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

import {
  MODEL_ALIASES,
  MODELS,
  MODEL_VERSION,
  type Settings,
} from "./config";
import {
  BackendProtocolError,
  BackendUnavailableError,
  type DecisionEngine,
  MalformedModelOutputError,
  OverloadedError,
  UpstreamHttpError,
} from "./engine";
import {
  RequestValidationError,
  type SystemOneRequest,
  validateSystemOneRequest,
} from "./types";

function jsonResponse(
  body: unknown,
  status = 200,
  headers: HeadersInit = {},
): Response {
  return Response.json(body, { status, headers });
}

function apiError(
  status: number,
  errorType: string,
  message: string,
  headers: HeadersInit = {},
): Response {
  return jsonResponse(
    { detail: { error_type: errorType, message } },
    status,
    headers,
  );
}

function authenticated(settings: Settings, request: Request): Response | null {
  if (!settings.apiKey) return null;
  const authorization = request.headers.get("authorization");
  if (!authorization) {
    return apiError(
      403,
      "authentication_error",
      "Must supply an API key! Check your request and try again.",
    );
  }
  const match = /^Bearer\s+(.+)$/i.exec(authorization);
  const supplied = Buffer.from(match?.[1]?.trim() ?? "");
  const expected = Buffer.from(settings.apiKey);
  const matches =
    supplied.length === expected.length && timingSafeEqual(supplied, expected);
  if (!matches) {
    return apiError(
      401,
      "authentication_error",
      "Cannot authenticate with the server. Please check your API key and try again.",
    );
  }
  return null;
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (typeof value === "object" && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
      a.localeCompare(b),
    );
    return `{${entries
      .map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function requestSeed(body: SystemOneRequest): number {
  const canonical = stableStringify([body.state, body.questions]);
  const digest = createHash("sha256").update(canonical).digest();
  return digest.readUInt32BE(0);
}

function requestId(): string {
  return `req_${randomBytes(16).toString("hex")}`;
}

export class LocalJevApp {
  constructor(
    readonly settings: Settings,
    readonly engine: DecisionEngine,
  ) {}

  async close(): Promise<void> {
    await this.engine.close?.();
  }

  async fetch(request: Request): Promise<Response> {
    const id = requestId();
    let response: Response;
    try {
      response = await this.route(request);
    } catch (error) {
      console.error(`[${id}] Unhandled request error`, error);
      response = apiError(500, "api_error", "Internal server error");
    }
    const headers = new Headers(response.headers);
    headers.set("x-typesafe-request-id", id);
    headers.set("x-request-id", id);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  }

  private async route(request: Request): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname.startsWith("/v1/")) {
      const denied = authenticated(this.settings, request);
      if (denied) return denied;
    }

    if (request.method === "GET" && pathname === "/health") {
      return jsonResponse({ status: "ok" });
    }
    if (request.method === "GET" && pathname === "/ready") {
      try {
        if (!(await this.engine.ready?.())) {
          return jsonResponse(
            {
              status: "unavailable",
              detail: `upstream model ${JSON.stringify(this.settings.upstreamModel)} is not loaded`,
            },
            503,
          );
        }
      } catch {
        return jsonResponse({ status: "unavailable" }, 503);
      }
      return jsonResponse({
        status: "ready",
        upstream_model: this.settings.upstreamModel,
      });
    }
    if (request.method === "GET" && pathname === "/v1/models") {
      return jsonResponse({ models: MODELS });
    }
    if (request.method === "POST" && pathname === "/v1/systemone") {
      return this.systemOne(request);
    }
    return apiError(404, "not_found_error", "Route not found");
  }

  private async systemOne(request: Request): Promise<Response> {
    let raw: unknown;
    try {
      raw = await request.json();
    } catch {
      return apiError(400, "invalid_request_error", "Request body must be valid JSON");
    }

    let body: SystemOneRequest;
    try {
      body = validateSystemOneRequest(raw);
    } catch (error) {
      if (error instanceof RequestValidationError) {
        return jsonResponse({ detail: [error.issue] }, 422);
      }
      throw error;
    }

    if (!MODEL_ALIASES.has(body.model)) {
      return apiError(
        404,
        "not_found_error",
        `Model ${JSON.stringify(body.model)} not found. Available: localjev-latest.`,
      );
    }

    try {
      const result = await this.engine.decide(
        body.questions,
        body.state,
        requestSeed(body),
      );
      return jsonResponse({
        model: MODEL_VERSION,
        answers: result.answers,
        usage: {
          input_tokens: result.inputTokens,
          output_tokens: result.outputTokens,
        },
      });
    } catch (error) {
      if (error instanceof OverloadedError) {
        return apiError(529, "overloaded_error", error.message, {
          "retry-after": "1",
        });
      }
      if (
        error instanceof MalformedModelOutputError ||
        error instanceof BackendProtocolError
      ) {
        return apiError(502, "api_error", error.message);
      }
      if (
        error instanceof UpstreamHttpError ||
        error instanceof BackendUnavailableError
      ) {
        return apiError(503, "api_error", error.message, {
          "retry-after": "2",
        });
      }
      throw error;
    }
  }
}
