import { expect, test } from "@playwright/test";

test("imported JIF refreshes completed papers with year/source and keeps preprints inapplicable", async ({ page }, testInfo) => {
  let imported = false;
  const task = { id: "jif-task", name: "Journal metric test", topic: "RAG", research_questions: [], target_count: 2, language: "en", output_language: "zh", date_from: "", date_to: "", sources: ["crossref"], evidence_review: false, prompt_overrides: {}, origin: "user", created_at: new Date().toISOString() };
  const run = { id: "jif-run", task_id: task.id, status: "completed", paper_count: 2, progress: 6, total_steps: 6 };
  const metric = { journal: "Fixture Journal", jif: "0", year: 2025, source: "Synthetic JCR fixture", source_url: "https://example.org/jcr", matched_by: "issn" };
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/tasks", (route) => route.fulfill({ json: [task] }));
  await page.route("**/api/tasks/jif-task/runs*", (route) => route.fulfill({ json: [run] }));
  await page.route("**/api/runs/jif-run", (route) => route.fulfill({ json: run }));
  await page.route("**/api/runs/jif-run/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/papers")) return route.fulfill({ json: [
      { id: "p1", title: "Journal paper", authors: [], abstract: "", source: "crossref", venue: "Fixture Journal", issns: ["0028-0836"], journal_metric: imported ? metric : null, relevance_score: 0.7, summary: {}, review: "save" },
      { id: "p2", title: "Preprint", authors: [], abstract: "", source: "arxiv", venue: "arXiv", relevance_score: 0.7, summary: {}, review: "save" },
    ] });
    return route.fulfill({ json: path.endsWith("/summary") ? { total: 0 } : [] });
  });
  await page.route("**/api/journal-metrics", (route) => route.fulfill({ json: { records: imported ? 1 : 0, latest_year: imported ? 2025 : null, updated_at: imported ? "2026-10-17T00:00:00Z" : null } }));
  await page.route("**/api/journal-metrics/import", (route) => {
    const data = route.request().postDataJSON();
    expect(data.csv).toContain("0028-0836,,2025,0");
    expect(data.source).toBe("Synthetic JCR fixture");
    imported = true;
    return route.fulfill({ json: { imported: 1, records: 1 } });
  });
  await page.goto("/");
  await expect(page.getByText("期刊影响因子：暂未查到", { exact: false })).toBeVisible();
  await expect(page.getByText("期刊影响因子：不适用", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByText("期刊影响因子（JIF）", { exact: true })).toBeVisible();
  await page.getByLabel("指标 CSV", { exact: true }).setInputFiles({ name: "fixture.csv", mimeType: "text/csv", buffer: Buffer.from("journal,issn,eissn,year,jif\nFixture Journal,0028-0836,,2025,0\n") });
  await page.getByLabel("数据来源名称", { exact: true }).fill("Synthetic JCR fixture");
  await page.getByRole("button", { name: "导入影响因子", exact: true }).click();
  await expect(page.getByText("已导入 1 条 ISSN/年份指标记录", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "工作台", exact: true }).click();
  await expect(page.locator(".journal-metric").first()).toContainText("0 · 2025");
  await expect(page.locator(".journal-metric").first()).toContainText("Synthetic JCR fixture");
  await expect(page.locator(".journal-metric").nth(1)).toContainText("不适用");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("journal-metrics-mobile.png"), fullPage: true });
});

test("automatic JIF shows publisher provenance and settings toggle persists", async ({ page }) => {
  let enabled = true;
  const task = { id: "auto-jif", name: "Automatic JIF", topic: "AI", sources: ["crossref"], target_count: 1, research_questions: [], prompt_overrides: {}, created_at: new Date().toISOString() };
  const run = { id: "auto-run", task_id: task.id, status: "completed", paper_count: 1, progress: 6, total_steps: 6 };
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/tasks", (route) => route.fulfill({ json: [task] }));
  await page.route("**/api/tasks/auto-jif/runs*", (route) => route.fulfill({ json: [run] }));
  await page.route("**/api/runs/auto-run", (route) => route.fulfill({ json: run }));
  await page.route("**/api/runs/auto-run/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/papers")) return route.fulfill({ json: [{ id: "auto-paper", title: "Fixture paper", authors: [], source: "crossref", venue: "Fixture Journal", venue_type: "journal", journal_metric_status: "matched", journal_metric: { journal: "Fixture Journal", year: 2025, jif: "1.2", source: "Publisher fixture", source_kind: "publisher", source_url: "https://www.frontiersin.org/about/impact", fetched_at: "2026-10-17T01:00:00Z" }, relevance_score: .9, summary: {}, review: "save" }] });
    if (path.endsWith("/artifacts")) return route.fulfill({ json: [{ node: "journal_metrics", payload: { enabled: true, matched: 1, not_applicable: 0, lookup_failed: 0 } }] });
    return route.fulfill({ json: path.endsWith("/summary") ? { total: 0 } : [] });
  });
  await page.route("**/api/journal-metrics", (route) => route.fulfill({ json: { records: 1, latest_year: 2025, auto_enabled: enabled, cached_journals: 1, matched_journals: 1 } }));
  await page.route("**/api/settings/journal_metrics", (route) => {
    expect(route.request().method()).toBe("PUT");
    enabled = route.request().postDataJSON().journal_metrics_auto;
    return route.fulfill({ json: { journal_metrics_auto: enabled } });
  });
  await page.goto("/");
  await expect(page.locator(".journal-metric").filter({ hasText: "期刊/出版物" })).toContainText("官网公布");
  await expect(page.getByRole("link", { name: "来源链接", exact: true })).toHaveAttribute("href", "https://www.frontiersin.org/about/impact");
  await expect(page.getByText("已匹配 1 篇", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const toggle = page.getByRole("checkbox", { name: "自动获取影响因子", exact: true });
  await expect(toggle).toBeChecked();
  await toggle.uncheck();
  await expect(page.getByText("已关闭自动查询", { exact: false })).toBeVisible();
  await expect(toggle).not.toBeChecked();
  await toggle.check();
  await expect(page.getByText("已开启：下次运行", { exact: false })).toBeVisible();
});
