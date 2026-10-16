import { loadSettings } from "../src/config";
import { Engine } from "../src/engine";
import type { Question } from "../src/types";

const settings = loadSettings();
const engine = new Engine(settings);

const questions: Record<string, Question> = {
  department: {
    type: "choice",
    instructions: "Which team should handle this?",
    criteria: {
      billing: "Payment or subscription issues",
      technical: "Bugs or integration problems",
      sales: "Pricing or account questions",
    },
  },
  frustration: {
    type: "score",
    instructions: "How frustrated does the customer appear?",
    criteria: ["Calm", "Frustrated but civil", "Very angry"],
  },
  urgent: {
    type: "noul",
    instructions: "Does this require an immediate response?",
    criteria: null,
  },
};

const result = await engine.decide(
  questions,
  "Hi, I have been trying to connect Stripe but keep getting a 403 error.",
  1234,
);
console.log(
  JSON.stringify(
    {
      answers: result.answers,
      usage: {
        input_tokens: result.inputTokens,
        output_tokens: result.outputTokens,
      },
    },
    null,
    2,
  ),
);
