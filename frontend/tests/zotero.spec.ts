import { expect, test, type Page } from "@playwright/test";

test("Zotero configuration and per-paper retry survive reopening results", async ({ page }, testInfo) => {
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/settings", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...await response.json(), zotero_configured: true, zotero_api_key_configured: true, zotero_library_id: "123" } });
  });
  await page.route("**/api/settings/zotero/test", async (route) => {
    expect(route.request().postDataJSON()).not.toHaveProperty("zotero_api_key");
    await route.fulfill({ json: { status: "ok", diagnostics: { writable: true } } });
  });
  const task = { id: "zotero-task", name: "Zotero workflow", topic: "RAG", research_questions: [], target_count: 1, language: "en", output_language: "zh", date_from: "", date_to: "", sources: ["crossref"], evidence_review: false, prompt_overrides: {}, origin: "user", created_at: new Date().toISOString() };
  const run = { id: "zotero-run", task_id: task.id, status: "completed", current_node: "complete", paper_count: 1, error: "", progress: 6, total_steps: 6 };
  let result: Record<string, unknown> | null = null;
  let attempts = 0;
  await page.route("**/api/tasks", (route) => route.fulfill({ json: [task] }));
  await page.route("**/api/tasks/zotero-task/runs*", (route) => route.fulfill({ json: [run] }));
  await page.route("**/api/runs/zotero-run", (route) => route.fulfill({ json: run }));
  await page.route("**/api/runs/zotero-run/events", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/runs/zotero-run/artifacts", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/runs/zotero-run/decisions", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/runs/zotero-run/decisions/summary", (route) => route.fulfill({ json: { total: 0 } }));
  await page.route("**/api/runs/zotero-run/papers", (route) => route.fulfill({ json: [{ id: "zotero-paper", title: "Retrieval study", authors: ["Jane Doe"], abstract: "Study", published_date: "2026-10-01", source: "crossref", doi: "10.1234/study", official_url: "", relevance_score: 0.9, priority: "P1", summary: {}, review: "save", zotero: result }] }));
  await page.route("**/api/papers/zotero-paper/zotero", (route) => {
    attempts++;
    result = attempts === 1 ? { status: "failed", error: "Zotero permission denied" } : { status: "imported", item_key: "ITEM0001", url: "https://www.zotero.org/users/123/items/ITEM0001", error: "" };
    return route.fulfill({ json: result });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByText("Zotero 文献库", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("zotero-settings-desktop.png"), fullPage: true });
  await page.getByRole("button", { name: "测试 Zotero 连接" }).click();
  await expect(page.getByText("连接测试通过。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "工作台", exact: true }).click();
  await page.getByRole("button", { name: "导入 Zotero", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试 Zotero" })).toBeVisible();
  await page.getByRole("button", { name: "重试 Zotero" }).click();
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toBeVisible();
  await expect(page.locator(".global-error")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "检查 Zotero" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("zotero-result-mobile.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

async function destinationFixture(page: Page) {
  let saved = { zotero_library_type: "user", zotero_library_id: "123", zotero_collection_key: "", zotero_collection_name: "Literature Agent", zotero_configured: true, zotero_api_key_configured: true };
  const identity = () => JSON.stringify([saved.zotero_library_type, saved.zotero_library_id, saved.zotero_collection_key || saved.zotero_collection_name]);
  const initial = { status: "imported", item_key: "ITEM0001", url: "https://www.zotero.org/users/123/items/ITEM0001", error: "" };
  const results = new Map<string, typeof initial>([[identity(), initial]]);
  let paperGate: ReturnType<typeof deferred> | null = null;
  let importGate: ReturnType<typeof deferred> | null = null;
  const state = { paperRequests: 0, failSave: false, importStarted: false };
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/settings", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...await response.json(), ...saved } });
  });
  await page.route("**/api/settings/zotero", (route) => {
    if (state.failSave) return route.fulfill({ status: 422, json: { detail: "Invalid Zotero settings" } });
    saved = { ...saved, ...route.request().postDataJSON() };
    return route.fulfill({ json: saved });
  });
  await page.route("**/api/settings/secrets/zotero_api_key", (route) => {
    saved = { ...saved, zotero_configured: false, zotero_api_key_configured: false };
    return route.fulfill({ json: saved });
  });
  const task = { id: "destination-task", name: "Destination regression", topic: "RAG", research_questions: [], target_count: 1, language: "en", output_language: "zh", date_from: "", date_to: "", sources: ["crossref"], evidence_review: false, prompt_overrides: {}, origin: "user", created_at: new Date().toISOString() };
  const run = { id: "destination-run", task_id: task.id, status: "completed", current_node: "complete", paper_count: 1, error: "", progress: 6, total_steps: 6 };
  await page.route("**/api/tasks", (route) => route.fulfill({ json: [task] }));
  await page.route("**/api/tasks/destination-task/runs*", (route) => route.fulfill({ json: [run] }));
  await page.route("**/api/runs/destination-run", (route) => route.fulfill({ json: run }));
  for (const suffix of ["events", "artifacts", "decisions", "decisions/summary"]) {
    await page.route(`**/api/runs/destination-run/${suffix}`, (route) => route.fulfill({ json: suffix.endsWith("summary") ? { total: 0 } : [] }));
  }
  await page.route("**/api/runs/destination-run/papers", async (route) => {
    const result = saved.zotero_configured ? results.get(identity()) || null : null;
    const gate = paperGate;
    paperGate = null;
    state.paperRequests++;
    if (gate) await gate.promise;
    await route.fulfill({ json: [{ id: "destination-paper", title: "Study", authors: [], abstract: "", published_date: "2026-10-01", source: "crossref", doi: "10.1234/study", official_url: "", relevance_score: 0.9, summary: {}, review: "save", zotero: result }] });
  });
  await page.route("**/api/papers/destination-paper/zotero", async (route) => {
    const destination = identity();
    const result = { ...initial, url: `https://www.zotero.org/${saved.zotero_library_type === "user" ? "users" : "groups"}/${saved.zotero_library_id}/items/ITEM0001` };
    state.importStarted = true;
    if (importGate) await importGate.promise;
    results.set(destination, result);
    await route.fulfill({ json: result });
  });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toHaveAttribute("href", initial.url);
  return {
    state,
    holdNextPapers: () => { paperGate = deferred(); return paperGate; },
    holdImport: () => { importGate = deferred(); return importGate; },
  };
}

async function saveDestination(page: Page) {
  await page.getByRole("button", { name: "保存 Zotero", exact: true }).click();
  await expect(page.getByText("设置已保存并立即生效。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "工作台", exact: true }).click();
}

for (const change of [
  { label: "Library ID", value: "456", original: "123" },
  { label: "文献库类型", value: "group", original: "user" },
  { label: "分类名称", value: "Another collection", original: "Literature Agent" },
  { label: "Collection Key（可选）", value: "COLL0002", original: "" },
]) {
  test(`completed run refreshes Zotero status after changing ${change.label} and restores it when switching back`, async ({ page }) => {
    const { state } = await destinationFixture(page);
    const before = state.paperRequests;
    await page.getByRole("button", { name: "设置", exact: true }).click();
    const field = page.getByLabel(change.label, { exact: change.label !== "文献库类型" });
    if (change.label === "文献库类型") await field.selectOption(change.value);
    else await field.fill(change.value);
    await saveDestination(page);
    await expect(page.getByRole("link", { name: "已导入 Zotero" })).toHaveCount(0);
    await expect.poll(() => state.paperRequests).toBeGreaterThan(before);
    await expect(page.getByRole("button", { name: "导入 Zotero", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "设置", exact: true }).click();
    const originalField = page.getByLabel(change.label, { exact: change.label !== "文献库类型" });
    if (change.label === "文献库类型") await originalField.selectOption(change.original);
    else await originalField.fill(change.original);
    await saveDestination(page);
    await expect(page.getByRole("link", { name: "已导入 Zotero" })).toHaveAttribute("href", "https://www.zotero.org/users/123/items/ITEM0001");
  });
}

test("unsaved and rejected Zotero edits keep the saved destination status", async ({ page }) => {
  const { state } = await destinationFixture(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByLabel("Library ID", { exact: true }).fill("456");
  await page.getByRole("button", { name: "工作台", exact: true }).click();
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toBeVisible();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByLabel("Library ID", { exact: true }).fill("456");
  state.failSave = true;
  await page.getByRole("button", { name: "保存 Zotero", exact: true }).click();
  await expect(page.locator(".global-error")).toContainText("Invalid Zotero settings");
  await page.getByRole("button", { name: "工作台", exact: true }).click();
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toHaveAttribute("href", "https://www.zotero.org/users/123/items/ITEM0001");
});

test("a collection key takes precedence over name and key rotation keeps destination status", async ({ page }) => {
  const { state } = await destinationFixture(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByLabel("Collection Key（可选）", { exact: true }).fill("COLL0002");
  await saveDestination(page);
  await page.getByRole("button", { name: "导入 Zotero", exact: true }).click();
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toBeVisible();
  const before = state.paperRequests;
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByLabel("分类名称", { exact: true }).fill("Ignored when key is set");
  const section = page.locator(".settings-section").filter({ has: page.getByText("Zotero 文献库", { exact: true }) });
  await section.getByLabel("Zotero API Key", { exact: true }).fill("mock-new-key");
  await saveDestination(page);
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toBeVisible();
  expect(state.paperRequests).toBe(before);
});

test("clearing the Zotero key clears statuses and disables import", async ({ page }) => {
  await destinationFixture(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const section = page.locator(".settings-section").filter({ has: page.getByText("Zotero 文献库", { exact: true }) });
  await section.getByRole("button", { name: "清除已保存密钥", exact: true }).click();
  await expect(section.getByText("待配置", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "工作台", exact: true }).click();
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "导入 Zotero", exact: true })).toBeDisabled();
});

test("late import response from the old destination cannot restore its link or notice", async ({ page }) => {
  const fixture = await destinationFixture(page);
  const gate = fixture.holdImport();
  await page.getByRole("button", { name: "检查 Zotero", exact: true }).click();
  await expect.poll(() => fixture.state.importStarted).toBe(true);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByLabel("Library ID", { exact: true }).fill("456");
  await saveDestination(page);
  gate.resolve();
  await expect(page.getByRole("button", { name: "导入 Zotero", exact: true })).toBeEnabled();
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toHaveCount(0);
  await expect(page.locator(".notice")).not.toContainText("论文已导入 Zotero");
});

test("late papers response cannot repopulate an old destination after settings refresh", async ({ page }) => {
  const fixture = await destinationFixture(page);
  const gate = fixture.holdNextPapers();
  const before = fixture.state.paperRequests;
  // Reopening creates a non-polling loadRunData request as well as the run poll.
  await page.locator(".recent-task-main", { hasText: "Destination regression" }).click();
  await expect.poll(() => fixture.state.paperRequests).toBeGreaterThan(before);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByLabel("Library ID", { exact: true }).fill("456");
  await saveDestination(page);
  await expect(page.getByRole("button", { name: "导入 Zotero", exact: true })).toBeVisible();
  const oldResponse = page.waitForResponse((response) => response.url().endsWith("/runs/destination-run/papers") && response.request().method() === "GET");
  gate.resolve();
  await (await oldResponse).finished();
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByRole("link", { name: "已导入 Zotero" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "导入 Zotero", exact: true })).toBeVisible();
});
