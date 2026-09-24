import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(currentDir, "..");
const resultRoot = path.join(projectRoot, "test-results", "p2-regression-20260924");
const python = path.join(projectRoot, "backend", ".venv", "Scripts", "python.exe");

export default defineConfig({
  testDir: "./tests",
  outputDir: path.join(resultRoot, "artifacts"),
  timeout: 30_000,
  fullyParallel: false,
  reporter: [["list"], ["html", { outputFolder: path.join(resultRoot, "html-report"), open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8011",
    browserName: "chromium",
    channel: "msedge",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `"${python}" -m literature_agent.launcher --port 8011 --no-browser`,
    url: "http://127.0.0.1:8011/api/health",
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      LITERATURE_AGENT_DATA_DIR: path.join(resultRoot, "playwright-data"),
      LITERATURE_AGENT_BOOTSTRAP: path.join(resultRoot, "playwright-bootstrap.json"),
      LITERATURE_AGENT_LIVE: "false",
    },
  },
});
