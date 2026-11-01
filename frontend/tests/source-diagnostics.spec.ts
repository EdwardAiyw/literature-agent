import { expect, test } from "@playwright/test";

test("expanded sources can be selected and saved in a daily subscription", async ({ page, request }) => {
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const catalogue = ["Semantic Scholar", "OpenAlex", "Crossref", "arXiv", "PubMed", "DOAJ", "DataCite", "HAL", "Europe PMC"];
  for (const label of catalogue) await expect(page.getByRole("checkbox", { name: label, exact: true })).toBeChecked();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const section = page.locator(".settings-section").filter({ has: page.getByText("文献来源", { exact: true }) });
  await expect(section).toContainText("9 个来源");
  await page.getByRole("button", { name: "每日订阅", exact: true }).click();
  for (const label of catalogue.slice(0, 5)) await page.getByRole("checkbox", { name: label, exact: true }).uncheck();
  for (const label of catalogue.slice(5)) await expect(page.getByRole("checkbox", { name: label, exact: true })).toBeChecked();
  const name = `Expanded sources ${Date.now()}`;
  await page.getByLabel("订阅名称", { exact: true }).fill(name);
  await page.getByLabel("研究主题", { exact: true }).fill("machine learning");
  await page.getByLabel("收件人", { exact: true }).fill("reader@example.org");
  await page.getByLabel("目标篇数", { exact: true }).fill("5");
  await page.getByLabel("执行时间", { exact: true }).fill("09:00");
  // Keep this validation subscription disabled so it cannot trigger delivery.
  await page.locator('input[type="checkbox"]').last().uncheck();
  const responsePromise = page.waitForResponse((response) => response.url().endsWith("/api/subscriptions") && response.request().method() === "POST");
  await page.getByRole("button", { name: "保存订阅", exact: true }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const subscription = await response.json();
  try {
    expect(subscription.sources).toEqual(["doaj", "datacite", "hal", "europe_pmc"]);
    expect(subscription.enabled).toBe(false);
    const row = page.locator(".subscription-row").filter({ hasText: name });
    await row.getByRole("button", { name: "编辑订阅", exact: true }).click();
    for (const label of catalogue.slice(5)) await expect(page.getByRole("checkbox", { name: label, exact: true })).toBeChecked();
    for (const label of catalogue.slice(0, 5)) await expect(page.getByRole("checkbox", { name: label, exact: true })).not.toBeChecked();
  } finally {
    await request.delete(`/api/subscriptions/${subscription.id}`);
  }
});

for (const sample of [
  { name: "legacy 429", source: "crossref", diagnostic: { status: "failed", count: 0, error: "HTTPStatusError: 429 Too Many Requests" }, label: "暂时限流" },
  { name: "anonymous Semantic Scholar", source: "semantic_scholar", diagnostic: { status: "rate_limited", count: 0, rate_limited: true, final_http_status: 429, attempts: 4, retry_count: 3, retry_after_seconds: 60 }, label: "暂时限流" },
  { name: "preserved partial results", source: "crossref", diagnostic: { status: "partial", count: 10, rate_limited: true, final_http_status: 429, attempts: 5, retry_count: 3 }, label: "部分可用（限流）" },
]) {
  test(`source diagnostics explain ${sample.name}`, async ({ page }) => {
    const task = { id: "source-task", name: "Source diagnostics", topic: "retrieval", origin: "user", sources: [sample.source], created_at: "2026-10-15T11:00:00Z" };
    const run = { id: "source-run", task_id: task.id, status: "completed", current_node: "completed", progress: 6, total_steps: 6, paper_count: 0, error: "" };
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/onboarding") return route.fulfill({ json: { complete: true, steps: {} } });
      if (path === "/api/tasks") return route.fulfill({ json: [task] });
      if (path === `/api/tasks/${task.id}/runs`) return route.fulfill({ json: [run] });
      if (path === `/api/runs/${run.id}`) return route.fulfill({ json: run });
      if (path.endsWith("/decisions/summary")) return route.fulfill({ json: { total: 0 } });
      if (["events", "decisions", "papers"].some((suffix) => path.endsWith("/" + suffix))) return route.fulfill({ json: [] });
      if (path.endsWith("/artifacts")) return route.fulfill({ json: [{ node: "retrieval", payload: { sources: { [sample.source]: sample.diagnostic } } }] });
      return route.continue();
    });
    await page.goto("/");
    const diagnostic = page.locator(".diagnostic");
    await expect(diagnostic.locator("b")).toHaveText(sample.label);
    await expect(diagnostic).toContainText("来源返回 HTTP 429");
    if (sample.diagnostic.count) await expect(diagnostic).toContainText("已保留成功取得的文献");
    if (sample.source === "semantic_scholar") {
      await expect(diagnostic).toContainText("Semantic Scholar API Key");
      await expect(diagnostic).toContainText("请求 4 次 · 重试 3 次");
    }
    await expect(page.locator(".global-error")).toHaveCount(0);
  });
}

test("source connection tests show each provider's actual status", async ({ page }) => {
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  const checks: Record<string, any> = {};
  await page.route("**/api/settings", async (route) => {
    const response = await route.fetch();
    const settings = await response.json();
    settings.sources = settings.sources.map((source: any) => ({ ...source, last_test: checks[source.id] || null }));
    await route.fulfill({ json: settings });
  });
  for (const source of ["crossref", "semantic_scholar"]) {
    await page.route(`**/api/sources/${source}/test`, async (route) => {
      checks[source] = { status: source === "crossref" ? "ok" : "rate_limited", count: source === "crossref" ? 1 : 0,
        checked_at: new Date().toISOString(), error: source === "crossref" ? "" : "HTTP 429" };
      await route.fulfill({ json: checks[source] });
    });
  }
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const crossref = page.getByRole("article", { name: "Crossref 来源", exact: true });
  await crossref.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(crossref.getByRole("status")).toContainText("连接正常");
  const semantic = page.getByRole("article", { name: "Semantic Scholar 来源", exact: true });
  await semantic.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(semantic.getByRole("status")).toContainText("暂时限流");
  await expect(page.getByText("连接测试通过。", { exact: true })).toHaveCount(0);
});
