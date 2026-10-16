export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type Described = string | JsonValue[] | { [key: string]: JsonValue } | null;

export interface NoulQuestion {
  type: "noul";
  instructions: Described;
  criteria: { true: Described; false: Described } | null;
}

export interface ChoiceQuestion {
  type: "choice";
  instructions: Described;
  criteria: Record<string, Described>;
}

export interface ScoreQuestion {
  type: "score";
  instructions: Described;
  criteria: JsonValue[];
}

export type Question = NoulQuestion | ChoiceQuestion | ScoreQuestion;

export interface SystemOneRequest {
  state: string | JsonValue[] | { [key: string]: JsonValue };
  model: string;
  questions: Record<string, Question>;
}

export type NoulAnswer = { type: "noul"; noul: number };
export type ChoiceAnswer = {
  type: "choice";
  choice: string;
  probabilities: Record<string, number>;
  confidence: number;
};
export type ScoreAnswer = {
  type: "score";
  score: number;
  legend: Record<string, JsonValue>;
  probabilities: Record<string, number>;
  confidence: number;
};
export type Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer;

export interface ValidationIssue {
  type: "value_error";
  loc: (string | number)[];
  msg: string;
  input?: unknown;
}

export class RequestValidationError extends Error {
  readonly issue: ValidationIssue;

  constructor(loc: (string | number)[], message: string, input?: unknown) {
    super(message);
    this.name = "RequestValidationError";
    this.issue = {
      type: "value_error",
      loc,
      msg: message,
      ...(input === undefined ? {} : { input }),
    };
  }
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function described(value: unknown): value is Described {
  return (
    value === null ||
    typeof value === "string" ||
    Array.isArray(value) ||
    object(value)
  );
}

function fail(
  path: (string | number)[],
  message: string,
  input?: unknown,
): never {
  throw new RequestValidationError(["body", ...path], message, input);
}

function validateInstructions(
  raw: Record<string, unknown>,
  path: (string | number)[],
): Described {
  const value = raw.instructions ?? null;
  if (!described(value)) {
    fail([...path, "instructions"], "Input must be a string, object, array, or null", value);
  }
  return value;
}

function validateQuestion(raw: unknown, path: (string | number)[]): Question {
  if (!object(raw)) {
    fail(path, "Question must be an object", raw);
  }
  const instructions = validateInstructions(raw, path);

  if (raw.type === "noul") {
    const criterion = raw.criteria ?? null;
    if (criterion !== null && !object(criterion)) {
      fail([...path, "criteria"], "Noul criteria must be an object or null", criterion);
    }
    const yes = criterion?.true ?? null;
    const no = criterion?.false ?? null;
    if (!described(yes)) {
      fail([...path, "criteria", "true"], "Invalid true criterion", yes);
    }
    if (!described(no)) {
      fail([...path, "criteria", "false"], "Invalid false criterion", no);
    }
    return { type: "noul", instructions, criteria: { true: yes, false: no } };
  }

  if (raw.type === "choice") {
    if (!object(raw.criteria)) {
      fail([...path, "criteria"], "Choice criteria must be an object", raw.criteria);
    }
    const entries = Object.entries(raw.criteria);
    if (entries.length < 2 || entries.length > 128) {
      fail([...path, "criteria"], "A choice needs 2 to 128 options", raw.criteria);
    }
    const criteria: Record<string, Described> = {};
    for (const [label, value] of entries) {
      if (!described(value)) {
        fail([...path, "criteria", label], "Invalid choice criterion", value);
      }
      criteria[label] = value;
    }
    return { type: "choice", instructions, criteria };
  }

  if (raw.type === "score") {
    if (!Array.isArray(raw.criteria)) {
      fail([...path, "criteria"], "Score criteria must be an array", raw.criteria);
    }
    if (raw.criteria.length < 2 || raw.criteria.length > 10) {
      fail([...path, "criteria"], "A score needs 2 to 10 levels", raw.criteria);
    }
    return {
      type: "score",
      instructions,
      criteria: raw.criteria as JsonValue[],
    };
  }

  fail([...path, "type"], "Question type must be 'noul', 'choice', or 'score'", raw.type);
}

export function validateSystemOneRequest(raw: unknown): SystemOneRequest {
  if (!object(raw)) {
    fail([], "Request body must be an object", raw);
  }
  if (!("state" in raw)) {
    fail(["state"], "Field required");
  }
  if (
    typeof raw.state !== "string" &&
    !Array.isArray(raw.state) &&
    !object(raw.state)
  ) {
    fail(["state"], "State must be a string, object, or array", raw.state);
  }
  if (typeof raw.model !== "string") {
    fail(["model"], "Model must be a string", raw.model);
  }
  if (!object(raw.questions)) {
    fail(["questions"], "Questions must be an object", raw.questions);
  }
  const entries = Object.entries(raw.questions);
  if (entries.length === 0) {
    fail(["questions"], "At least one question is required", raw.questions);
  }
  const questions: Record<string, Question> = {};
  for (const [key, value] of entries) {
    questions[key] = validateQuestion(value, ["questions", key]);
  }
  return {
    state: raw.state as SystemOneRequest["state"],
    model: raw.model,
    questions,
  };
}
