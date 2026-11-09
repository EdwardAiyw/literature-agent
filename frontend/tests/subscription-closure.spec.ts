import { expect, test } from "@playwright/test";

test("paused subscription exposes report, retries once, and resumes through editing on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let retryCount = 0;
  let retrievalCount = 0;
  let subscription = {
    id: "closure-sub", task_id: "closure-task", name: "历史文献追踪", topic: "Retrieval augmented generation",
    recipient: "reader@example.org", enabled: false, target_count: 10,
    schedule_time: "07:00", timezone: "Asia/Hong_Kong", sources: ["openalex"],
    language: "bilingual", output_language: "zh", date_from: "2023-01-01", date_to: "", date_to_mode: "today",
    created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-09T00:00:00Z",
    auto_pause: { run_id: "closure-run", paused_at: "2026-11-09T00:00:00Z", reason: "all_delivered",
      status: "failed", error: "SMTP temporarily unavailable", paper_count: 62, report_ready: true },
  };
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/tasks", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/subscriptions", (route) => route.fulfill({ json: [subscription] }));
  await page.route("**/api/deliveries", (route) => route.fulfill({ json: [
    { id: "notice", subscription_id: subscription.id, kind: "pause_notice", status: "sent", recipient: subscription.recipient, created_at: subscription.updated_at },
    { id: "summary", subscription_id: subscription.id, kind: "history_summary", status: "failed", recipient: subscription.recipient, created_at: subscription.updated_at, error: "SMTP temporarily unavailable" },
  ] }));
  await page.route("**/api/subscriptions/closure-sub/closure/retry", async (route) => {
    retryCount += 1;
    subscription = { ...subscription, auto_pause: { ...subscription.auto_pause, status: "queued", error: "" } };
    await route.fulfill({ status: 202, json: subscription });
  });
  await page.route("**/api/subscriptions/closure-sub", async (route) => {
    expect(route.request().method()).toBe("PATCH");
    subscription = { ...subscription, ...route.request().postDataJSON() };
    await route.fulfill({ json: subscription });
  });
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/runs")) retrievalCount += 1; });
  await page.goto("/");
  await page.getByRole("button", { name: "每日订阅", exact: true }).click();
  const row = page.locator(".subscription-row");
  await expect(row).toContainText("已自动暂停");
  await expect(row).toContainText("历史文献 62 篇");
  await expect(row).toContainText("SMTP temporarily unavailable");
  await expect(page.locator(".delivery-panel")).toContainText("暂停通知");
  await expect(page.locator(".delivery-panel")).toContainText("历史文献汇总");
  // Download responses and report contents are covered by the backend integration test.
  await expect(row.getByRole("link", { name: "下载完整汇总" })).toHaveAttribute("href", "/api/subscriptions/closure-sub/closure/report");
  await expect(row.getByRole("link", { name: "下载完整汇总" })).toHaveAttribute("download", "");
  await row.getByRole("button", { name: "重试通知与汇总" }).click();
  await expect(row).toContainText("等待汇总");
  await expect(row.getByRole("button", { name: "重试通知与汇总" })).toHaveCount(0);
  expect(retryCount).toBe(1);
  expect(retrievalCount).toBe(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await row.getByRole("button", { name: "编辑订阅" }).click();
  await page.getByLabel("启用每日自动执行").check();
  await page.getByRole("button", { name: "保存订阅", exact: true }).click();
  await expect(row).toContainText("已启用");
  await expect(row).toContainText("上次暂停");
  expect(subscription.enabled).toBe(true);
  expect(retrievalCount).toBe(0);
});
