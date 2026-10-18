import { expect, test } from "@playwright/test";

test("server settings describe persistent secrets and internal scheduling", async ({ page }) => {
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/settings", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...(await response.json()), server_mode: true } });
  });
  await page.route("**/api/scheduler", (route) => route.fulfill({ json: { mode: "internal", running: true, supported: false, tasks: [] } }));
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByRole("heading", { name: "服务器连接设置" })).toBeVisible();
  await expect(page.getByText("服务器已连接", { exact: true })).toBeVisible();
  await expect(page.getByText("服务器运行 · SSH 管理", { exact: true })).toBeVisible();
  await expect(page.getByText("密钥保存在服务器受限文件中")).toBeVisible();
  await expect(page.getByText("后台运行中", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "注册自动任务", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "选择目录", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "恢复备份", exact: true })).toBeDisabled();
});

test("web subscription editing preserves task identity and hidden research configuration", async ({ page, request }) => {
  const prompts = await (await request.get("/api/prompts")).json();
  const prompt = prompts.find((item: any) => item.role === "relevance_screener" && item.version === "v2");
  const response = await request.post("/api/subscriptions", { data: {
    name: `服务器订阅编辑 ${Date.now()}`, topic: "Retrieval tool selection", recipient: "reader@example.org",
    schedule_time: "07:00", timezone: "Asia/Hong_Kong", target_count: 7, sources: ["openalex"],
    language: "en", output_language: "bilingual", research_questions: ["How are tools selected?"],
    evidence_review: true, prompt_overrides: { relevance_screener: prompt.id }, enabled: false,
  } });
  expect(response.ok()).toBeTruthy();
  const subscription = await response.json();
  try {
    await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
    await page.goto("/");
    await page.getByRole("button", { name: "每日订阅", exact: true }).click();
    const row = page.locator(".subscription-row").filter({ hasText: subscription.name });
    await row.getByRole("button", { name: "编辑订阅", exact: true }).click();
    await expect(page.getByRole("heading", { name: "编辑每日订阅" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "截止日期策略", exact: true })).toHaveValue("today");
    await page.getByRole("combobox", { name: "截止日期策略", exact: true }).selectOption("fixed");
    await page.getByLabel("结束日期", { exact: true }).fill("2026-10-15");
    await page.getByLabel("执行时间", { exact: true }).fill("08:35");
    await page.getByRole("textbox", { name: "研究主题", exact: true }).fill("Agentic retrieval planning");
    await page.getByRole("button", { name: "保存订阅", exact: true }).click();
    await expect(row).toContainText("08:35 · Asia/Hong_Kong");
    await expect(row).toContainText("Agentic retrieval planning");
    const saved = await (await request.get(`/api/subscriptions/${subscription.id}`)).json();
    expect(saved.date_to_mode).toBe("fixed");
    expect(saved.date_to).toBe("2026-10-15");
    for (const key of ["id", "task_id", "language", "output_language", "research_questions", "evidence_review", "prompt_overrides", "enabled", "sources"]) expect(saved[key]).toEqual(subscription[key]);
    const task = await (await request.get(`/api/tasks/${subscription.task_id}`)).json();
    expect(task.topic).toBe("Agentic retrieval planning");
    expect(task.research_questions).toEqual(subscription.research_questions);
    await row.getByRole("button", { name: "编辑订阅", exact: true }).click();
    await expect(page.getByRole("combobox", { name: "截止日期策略", exact: true })).toHaveValue("fixed");
    await page.getByLabel("执行时间", { exact: true }).fill("11:00");
    await page.getByRole("button", { name: "取消编辑", exact: true }).click();
    expect((await (await request.get(`/api/subscriptions/${subscription.id}`)).json()).schedule_time).toBe("08:35");
  } finally { expect((await request.delete(`/api/subscriptions/${subscription.id}`)).ok()).toBeTruthy(); }
});
