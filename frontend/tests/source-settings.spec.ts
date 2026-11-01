import { expect, test } from "@playwright/test";
import path from "node:path";

test("source manager configures Google Scholar and controls task choices", async ({ page }) => {
  const connections: Record<string, any> = {};
  let savedKey = "";
  let lastPayload: any;
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/settings", async (route) => {
    const response = await route.fetch();
    const settings = await response.json();
    settings.sources = settings.sources.map((source: any) => {
      connections[source.id] ||= source;
      return connections[source.id];
    });
    await route.fulfill({ json: settings });
  });
  await page.route("**/api/sources/google_scholar", async (route) => {
    const source = connections.google_scholar;
    if (route.request().method() === "DELETE") {
      Object.assign(source, { added: false, enabled: false, selectable: false, default_enabled: false });
      return route.fulfill({ json: { status: "removed" } });
    }
    lastPayload = route.request().postDataJSON();
    if (lastPayload.api_key) savedKey = lastPayload.api_key;
    Object.assign(source, { added: true, ...lastPayload });
    delete source.api_key;
    if (lastPayload.clear_api_key) { savedKey = ""; source.enabled = false; source.default_enabled = false; }
    source.configured = source.credential_configured = !!savedKey;
    source.selectable = source.enabled && source.configured;
    source.budget_override = lastPayload.daily_request_budget ?? source.budget_override;
    source.daily_request_budget = source.budget_override || 200;
    return route.fulfill({ json: source });
  });
  await page.route("**/api/sources/google_scholar/test", async (route) => {
    connections.google_scholar.last_test = { status: "ok", count: 1, error: "", checked_at: new Date().toISOString() };
    await route.fulfill({ json: connections.google_scholar.last_test });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page.getByRole("button", { name: "管理文献来源", exact: true }).click();
  const manager = page.getByLabel("文献来源管理", { exact: true });
  await manager.getByRole("button", { name: "添加来源", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "添加文献来源" });
  await dialog.getByLabel("选择来源", { exact: true }).selectOption("google_scholar");
  await expect(dialog).toContainText("第三方服务 · SerpApi");
  await dialog.getByLabel("SerpApi API Key", { exact: true }).fill("ui-test-key");
  await dialog.getByLabel("每日请求上限", { exact: true }).fill("3");
  await dialog.getByLabel("默认用于新任务和新订阅", { exact: true }).check();
  await dialog.getByRole("button", { name: "保存来源", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const scholar = manager.getByRole("article", { name: "Google Scholar 来源", exact: true });
  await expect(scholar.getByRole("switch")).toBeChecked();
  await expect(scholar).toContainText("每日上限 3 次");
  await scholar.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(scholar.getByRole("status")).toContainText("连接正常");
  await page.getByRole("button", { name: "工作台", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "Google Scholar", exact: true })).toBeChecked();
  await page.reload();
  await expect(page.getByRole("checkbox", { name: "Google Scholar", exact: true })).toBeChecked();
  await page.getByRole("button", { name: "管理文献来源", exact: true }).click();
  await manager.screenshot({ path: path.resolve("../output/source-settings/test-runtime-ui/desktop.png") });
  await scholar.getByRole("switch").uncheck();
  await expect(scholar.getByRole("switch")).toBeEnabled();
  await page.getByRole("button", { name: "工作台", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "Google Scholar", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "管理文献来源", exact: true }).click();
  await scholar.getByRole("switch").check();
  await expect(scholar.getByRole("switch")).toBeEnabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await scholar.getByRole("button", { name: "配置", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "配置 Google Scholar" });
  await expect(editor.getByLabel("SerpApi API Key", { exact: true })).toHaveValue("");
  await expect(editor.getByLabel("每日请求上限", { exact: true })).toHaveValue("3");
  await editor.screenshot({ path: path.resolve("../output/source-settings/test-runtime-ui/mobile-dialog.png") });
  await editor.getByRole("button", { name: "保存来源", exact: true }).click();
  await expect(editor).toHaveCount(0);
  expect(lastPayload.api_key).toBeUndefined();
  expect(savedKey).toBe("ui-test-key");
  await scholar.getByRole("button", { name: "配置", exact: true }).click();
  await editor.getByRole("button", { name: "清除已保存密钥并停用", exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(scholar.getByRole("switch")).not.toBeChecked();
  await expect(scholar.getByRole("button", { name: "测试连接", exact: true })).toBeDisabled();
  await scholar.getByRole("button", { name: "移除 Google Scholar", exact: true }).click();
  await expect(scholar).toHaveCount(0);
  await manager.getByRole("button", { name: "添加来源", exact: true }).click();
  await expect(dialog.getByLabel("选择来源", { exact: true }).locator('option[value="google_scholar"]')).toHaveCount(1);
});
