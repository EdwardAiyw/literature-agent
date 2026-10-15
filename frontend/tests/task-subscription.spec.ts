import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import path from "node:path";

async function createTask(request: APIRequestContext, suffix: string) {
  const prompts = await (await request.get("/api/prompts")).json();
  const prompt = prompts.find((item: any) => item.role === "relevance_screener" && item.version === "v2");
  const response = await request.post("/api/tasks", { data: {
    name: `每日转换测试 ${suffix} ${Date.now()}`, topic: "Agentic retrieval augmented generation",
    research_questions: ["How are retrieval tools selected?"], language: "en", output_language: "bilingual",
    target_count: 17, date_from: "2023-01-01", date_to: "2026-10-15", sources: ["fixture"],
    evidence_review: true, prompt_overrides: { relevance_screener: prompt.id }, origin: "test",
  } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function openTask(page: Page, task: any) {
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.goto("/");
  await page.locator(".recent-task-main").filter({ hasText: task.name }).click();
  await expect(page.locator(".run-task")).toContainText(task.name);
}

async function cleanup(request: APIRequestContext, taskId: string) {
  const subscriptions = await (await request.get("/api/subscriptions")).json();
  const subscription = subscriptions.find((item: any) => item.task_id === taskId);
  const response = await request.delete(subscription ? `/api/subscriptions/${subscription.id}` : `/api/tasks/${taskId}`);
  expect.soft([200, 404], await response.text()).toContain(response.status());
}

test("current task converts with preserved settings/history and reopens its existing subscription", async ({ page, request }) => {
  const task = await createTask(request, "current");
  try {
    const run = await (await request.post(`/api/tasks/${task.id}/runs`)).json();
    await expect.poll(async () => (await (await request.get(`/api/runs/${run.id}`)).json()).status).toBe("completed");
    const papersBefore = await (await request.get(`/api/runs/${run.id}/papers`)).json();
    await openTask(page, task);
    await page.locator(".run-panel").getByRole("button", { name: "转为每日任务", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "转为每日任务" });
    await expect(dialog).toContainText("2023-01-01 至 2026-10-15");
    await expect(dialog).toContainText("输出：中英文 · 每次最多 17 篇");
    await expect(dialog).toContainText("1 个研究问题 · 证据审查已启用 · 1 个 Prompt 覆盖");
    await dialog.getByLabel("收件人", { exact: true }).fill("reader@example.org");
    await dialog.getByLabel("每日执行时间").fill("09:15");
    await dialog.getByLabel("时区", { exact: true }).fill("UTC");
    await page.screenshot({ path: path.resolve("../output/task-subscription/test-runtime-ui/desktop.png") });
    await dialog.getByRole("button", { name: "保存每日任务", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByText("已转为每日任务，研究配置和历史结果已保留。", { exact: true })).toBeVisible();
    const row = page.locator(".subscription-row").filter({ hasText: task.name });
    await expect(row).toContainText("09:15 · UTC · 17 篇");
    await expect(row).toContainText("reader@example.org");
    const subscriptions = await (await request.get("/api/subscriptions")).json();
    const converted = subscriptions.filter((item: any) => item.task_id === task.id);
    expect(converted).toHaveLength(1);
    for (const key of ["name", "topic", "research_questions", "language", "output_language", "target_count", "date_from", "date_to", "sources", "evidence_review", "prompt_overrides"]) expect(converted[0][key]).toEqual(task[key]);
    expect(await (await request.get(`/api/tasks/${task.id}/runs`)).json()).toHaveLength(1);
    expect(await (await request.get(`/api/runs/${run.id}/papers`)).json()).toEqual(papersBefore);
    await page.getByRole("button", { name: "工作台", exact: true }).click();
    await expect(page.locator(".run-panel").getByRole("button", { name: "查看每日订阅", exact: true })).toBeVisible();
    await page.locator(".run-panel").getByRole("button", { name: "查看每日订阅", exact: true }).click();
    await expect(row).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.reload();
    await page.getByRole("button", { name: "每日订阅", exact: true }).click();
    await expect(row).toBeVisible();
  } finally { await cleanup(request, task.id); }
});

test("recent-task entry validates required details and cancel makes no writes on mobile", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const task = await createTask(request, "mobile");
  let conversionRequests = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith(`/tasks/${task.id}/subscription`)) conversionRequests += 1; });
  try {
    await openTask(page, task);
    await page.locator(".recent-row").filter({ hasText: task.name }).getByRole("button", { name: "转为每日任务", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "转为每日任务" });
    await dialog.getByLabel("收件人", { exact: true }).fill("");
    await dialog.getByRole("button", { name: "保存每日任务", exact: true }).click();
    await expect(dialog).toBeVisible();
    expect(conversionRequests).toBe(0);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: path.resolve("../output/task-subscription/test-runtime-ui/mobile.png") });
    await dialog.getByRole("button", { name: "取消", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(conversionRequests).toBe(0);
    const unchanged = await (await request.get(`/api/tasks/${task.id}`)).json();
    expect(unchanged).toEqual(task);
  } finally { await cleanup(request, task.id); }
});

test("failed conversion retains the form and blocks duplicate clicks while pending", async ({ page, request }) => {
  const task = await createTask(request, "failure");
  let attempts = 0;
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`**/api/tasks/${task.id}/subscription`, async (route) => {
    attempts += 1;
    if (attempts === 1) { await pending; return route.fulfill({ status: 503, json: { detail: "Temporary failure" } }); }
    return route.continue();
  });
  try {
    await openTask(page, task);
    await page.locator(".run-panel").getByRole("button", { name: "转为每日任务", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "转为每日任务" });
    await dialog.getByLabel("收件人", { exact: true }).fill("retry@example.org");
    await dialog.getByRole("button", { name: "保存每日任务", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "正在转换…", exact: true })).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
    expect(attempts).toBe(1);
    release();
    await expect(dialog.getByRole("alert")).toContainText("Temporary failure");
    await expect(dialog.getByLabel("收件人", { exact: true })).toHaveValue("retry@example.org");
    await dialog.getByRole("button", { name: "保存每日任务", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(attempts).toBe(2);
  } finally { release(); await cleanup(request, task.id); }
});
