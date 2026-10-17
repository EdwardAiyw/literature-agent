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
  await expect(page.getByText("期刊影响因子：未提供", { exact: false })).toBeVisible();
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
