import { expect, test } from "@playwright/test";

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

test("source connection test shows each provider instead of claiming all passed", async ({ page }) => {
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/settings/sources/test", (route) => route.fulfill({ json: {
    status: "ok", diagnostics: {
      crossref: { ok: true, status: "ok", count: 1 },
      semantic_scholar: { ok: false, status: "rate_limited", count: 0, rate_limited: true, final_http_status: 429 },
    },
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "测试来源", exact: true }).click();
  const panel = page.getByRole("status").filter({ hasText: "最近一次来源检测" });
  await expect(panel.locator(".diagnostic").filter({ hasText: "Crossref" })).toContainText("正常");
  await expect(panel.locator(".diagnostic").filter({ hasText: "Semantic Scholar" })).toContainText("暂时限流");
  await expect(page.getByText("来源检测完成，请查看各来源结果。", { exact: true })).toBeVisible();
  await expect(page.getByText("连接测试通过。", { exact: true })).toHaveCount(0);
});
