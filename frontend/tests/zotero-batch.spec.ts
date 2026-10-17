import { expect, test } from "@playwright/test";

test("task collection selection, batch retry and identifier download", async ({ page, request }, testInfo) => {
  const storedTask = await (await request.post("/api/tasks", { data: { name: "Identifier download fixture", topic: "RAG", target_count: 2 } })).json();
  const storedRun = await (await request.post(`/api/tasks/${storedTask.id}/runs`)).json();
  await expect.poll(async () => (await (await request.get(`/api/runs/${storedRun.id}`)).json()).status).toBe("completed");
  const task = { id: storedTask.id, name: "Batch test", topic: "RAG", research_questions: [], target_count: 2, language: "en", output_language: "zh", date_from: "", date_to: "", sources: ["crossref"], evidence_review: false, prompt_overrides: {}, origin: "user", created_at: new Date().toISOString(), zotero_auto_import: true, zotero_collection_key: "TARGET01" };
  const run = { id: storedRun.id, task_id: task.id, status: "completed", paper_count: 2, progress: 6, total_steps: 6 };
  let retried = false;
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/tasks", (route) => route.fulfill({ json: [task] }));
  await page.route(`**/api/tasks/${task.id}/runs*`, (route) => route.fulfill({ json: [run] }));
  await page.route(`**/api/runs/${run.id}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/retry")) { retried = true; return route.fulfill({ json: {} }); }
    if (path.endsWith("/zotero-batches")) return route.fulfill({ json: [{ id: "zotero_batch.test", destination: JSON.stringify(["user", "123", "TARGET01"]), status: retried ? "completed" : "failed", error: retried ? "" : "Zotero (429)：请求过于频繁，请稍后重试。", counts: { imported: retried ? 2 : 1, failed: retried ? 0 : 1 }, results: {} }] });
    if (path.endsWith("/zotero-identifiers")) return route.continue();
    return route.fulfill({ json: path.endsWith("/summary") ? { total: 0 } : [] });
  });
  await page.route(`**/api/runs/${run.id}`, (route) => route.fulfill({ json: run }));
  await page.route("**/api/zotero/collections", (route) => route.fulfill({ json: [{ key: "TARGET01", name: "Daily Digest", path: "Research / Daily Digest" }] }));
  await page.goto("/");
  await expect(page.getByText("Zotero (429)", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "重试失败条目" }).click();
  await expect(page.getByText("导入完成", { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载标识符 TXT" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`zotero-identifiers-${run.id}.txt`);
  await page.getByRole("button", { name: "读取集合", exact: true }).click();
  await page.getByLabel("目标集合", { exact: true }).selectOption("TARGET01");
  await expect(page.getByRole("option", { name: "Research / Daily Digest · TARGET01" })).toHaveCount(1);
  await page.getByLabel("检索完成后自动导入 Zotero", { exact: true }).check();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("batch-mobile.png"), fullPage: true });
  await request.delete(`/api/tasks/${storedTask.id}`);
});
