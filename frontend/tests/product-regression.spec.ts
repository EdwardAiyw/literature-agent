import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.resolve(currentDir, "../../test-results/p2-regression-20260924");
const navigation = ["工作台", "每日订阅", "Prompt 版本", "设置"];

async function useCompletedOnboarding(page: Page) {
  await page.route("**/api/onboarding", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        complete: true,
        data_dir: "playwright-data",
        steps: { data: true, llm: true, smtp: true, sources: true, scheduler: true },
      }),
    });
  });
  await page.route("**/api/jev/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ provider: "localjev", base_url: "http://127.0.0.1:8080", model: "jev-latest", configured: true, status: "ready", probability_kind: "self_reported", service: "LocalJev", upstream_model: "diffusiongemma-26B-A4B-it-4bit", available_models: ["localjev-0.2", "localjev-latest"] }),
    });
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
}

test("desktop cold load remains error-free across StrictMode initialization", async ({ page }) => {
  await useCompletedOnboarding(page);
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await page.goto("/");
    await expect(page.getByText("本地服务已连接")).toBeVisible();
    await expect(page.locator(".global-error")).toHaveCount(0);
  }
});

for (const viewport of [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 1000 },
]) {
  test(`${viewport.name} layout has no overflow and keeps all navigation visible`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await useCompletedOnboarding(page);
    await page.goto("/");
    await expect(page.getByText("本地服务已连接")).toBeVisible();

    for (const label of navigation) {
      await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
    }

    for (const label of navigation) {
      await page.getByRole("button", { name: label, exact: true }).click();
      await expectNoHorizontalOverflow(page);
      const controls = page.locator("main input:visible, main textarea:visible, main select:visible");
      for (let index = 0; index < await controls.count(); index += 1) {
        const box = await controls.nth(index).boundingBox();
        expect(box, `control ${index} on ${label} should have a layout box`).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 0.5);
      }
    }

    await page.getByRole("button", { name: "工作台", exact: true }).click();
    await page.screenshot({ path: path.join(screenshotDir, `workspace-${viewport.name}-fixed.png`), fullPage: true });
  });
}

test("rapid task switching keeps only the final task data", async ({ page, request }) => {
  const suffix = Date.now();
  const slowName = `Switch slow ${suffix}`;
  const finalName = `Switch final ${suffix}`;
  const create = async (name: string) => {
    const response = await request.post("/api/tasks", { data: { name, topic: name, target_count: 1, sources: ["openalex"] } });
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const slowTask = await create(slowName);
  const finalTask = await create(finalName);

  await useCompletedOnboarding(page);
  await page.route(`**/api/tasks/${slowTask.id}/runs*`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.continue();
  });
  await page.goto("/");
  await expect(page.getByText("本地服务已连接")).toBeVisible();

  await page.locator(".recent-task-main", { hasText: slowName }).click();
  await page.locator(".recent-task-main", { hasText: finalName }).click();
  await expect(page.locator(".run-task strong")).toHaveText(finalName);
  await page.waitForTimeout(600);
  await expect(page.locator(".run-task strong")).toHaveText(finalName);
});

test("Jev provider settings use one coherent form", async ({ page }) => {
  await useCompletedOnboarding(page);
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();

  await expect(page.getByText("LocalJev 决策层", { exact: true })).toBeVisible();
  const provider = page.getByRole("combobox", { name: "Provider", exact: true });
  await expect(provider).toHaveCount(1);
  await provider.selectOption("localjev");
  await expect(page.getByRole("textbox", { name: "LocalJev API 地址", exact: true })).toHaveValue("http://127.0.0.1:8080");
  await expect(page.getByRole("spinbutton", { name: "最大并发请求", exact: true })).toHaveCount(1);
  await expect(page.getByRole("spinbutton", { name: "超时（秒）", exact: true })).toHaveCount(1);
  await expect(page.locator(".localjev-chain")).toContainText("diffusiongemma-26B-A4B-it-4bit");
  await expectNoHorizontalOverflow(page);
});

for (const viewport of [
  { name: "mobile", width: 390, height: 844 },
  { name: "desktop", width: 1440, height: 1000 },
]) {
  test(`Jev audit stays readable without ${viewport.name} overflow`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await useCompletedOnboarding(page);
    await page.route("**/api/tasks", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify([{ id: "task-jev", name: "Jev audit run", topic: "decision routing", research_questions: [], target_count: 1, language: "bilingual", output_language: "zh", date_from: "", date_to: "", sources: ["openalex"], evidence_review: false, prompt_overrides: {}, origin: "user", created_at: "2026-09-25T00:00:00Z" }]) }));
    await page.route("**/api/tasks/task-jev/runs*", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify([{ id: "run-jev", task_id: "task-jev", status: "completed", current_node: "complete", paper_count: 1, error: "", progress: 6, total_steps: 6 }]) }));
    await page.route("**/api/runs/run-jev/events", (route) => route.fulfill({ contentType: "application/json", body: "[]" }));
    await page.route("**/api/runs/run-jev/artifacts", (route) => route.fulfill({ contentType: "application/json", body: "[]" }));
    await page.route("**/api/runs/run-jev/papers", (route) => route.fulfill({ contentType: "application/json", body: "[]" }));
    await page.route("**/api/runs/run-jev/decisions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify([{ id: "decision-1", stage: "relevance_screener", subject_id: "doi:10.0000/example-with-a-long-identifier", status: "fallback", provider: "localjev", probability_kind: "self_reported", routing: "needs_review", confidence: 0.68, cached: false, baseline_outcome: { recommended_action: "read", relevance_score: 0.62 }, final_outcome: { recommended_action: "read", relevance_score: 0.62 }, error: "", created_at: "2026-09-25T00:00:00Z" }]) }));
    await page.route("**/api/runs/run-jev/decisions/summary", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ total: 1, auto_applied: 0, needs_review: 1, fallback: 0, failed: 0, cached: 0, shadow: 0, providers: { localjev: 1 }, stages: { relevance_screener: 1 } }) }));

    await page.goto("/");
    await page.locator(".recent-task-main", { hasText: "Jev audit run" }).click();
    await expect(page.getByText("决策路由审计", { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.locator(".jev-row summary").click();
    await expect(page.getByText("基线结果", { exact: true })).toBeVisible();
    await expect(page.getByText("最终结果", { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
}
