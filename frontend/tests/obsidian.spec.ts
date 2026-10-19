import { expect, test } from "@playwright/test";

test("Obsidian settings save, synchronize, recover from failure and manage an independent task", async ({ page }, testInfo) => {
  let config: any = null;
  let last: any = null;
  let enabled = false;
  let fail = false;
  const actions: string[] = [];
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/obsidian{,/**}", async (route) => {
    const action = new URL(route.request().url()).pathname.split("/")[3];
    if (route.request().method() === "PUT") { config = route.request().postDataJSON(); return route.fulfill({ json: { status: "ok" } }); }
    if (route.request().method() === "POST") {
      actions.push(action);
      if (action === "register") enabled = true;
      if (action === "disable") enabled = false;
      if (action === "sync") {
        if (fail) { last = { at: "2026-10-19T02:00:00Z", status: "error", error: "SSH connection failed" }; return route.fulfill({ status: 400, json: { detail: last.error } }); }
        last = { at: "2026-10-19T02:00:00Z", status: "ok", unique_notes: 10, days: 1 };
      }
      return route.fulfill({ json: { status: "ok" } });
    }
    return route.fulfill({ json: { supported: true, config, vaults: [{ name: "Fixture vault", path: "D:/Fixture vault", open: true }], last_sync: last, scheduler: { tasks: enabled ? [{ name: "Literature Agent Obsidian Sync", state: "Ready" }] : [] } } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const panel = page.getByRole("region", { name: "Obsidian 连接" });
  await expect(panel.getByLabel("文库路径", { exact: true })).toHaveValue("D:/Fixture vault");
  await expect(panel.getByRole("button", { name: "立即同步到 Obsidian" })).toBeDisabled();
  await panel.getByLabel("SSH 地址").fill("fixture@example.org");
  await panel.getByLabel("每日订阅 ID").fill("fixture-subscription");
  await panel.getByRole("button", { name: "保存 Obsidian 配置" }).click();
  await expect(panel.getByText("Obsidian 配置已保存。", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "立即同步到 Obsidian" }).click();
  await expect(panel.getByText("10 篇论文笔记 · 1 份每日清单")).toBeVisible();
  await panel.getByRole("button", { name: "启用自动同步", exact: true }).click();
  await expect(panel.getByText("自动同步：已启用（登录时及每 15 分钟）")).toBeVisible();
  await panel.getByRole("button", { name: "打开论文索引" }).click();
  fail = true;
  await panel.getByRole("button", { name: "立即同步到 Obsidian" }).click();
  await expect(panel.getByRole("alert").first()).toContainText("SSH connection failed");
  fail = false;
  await panel.getByRole("button", { name: "立即同步到 Obsidian" }).click();
  await expect(panel.getByRole("alert")).toHaveCount(0);
  await panel.getByRole("button", { name: "停用自动同步" }).click();
  await expect(panel.getByText("自动同步：未启用")).toBeVisible();
  await panel.getByLabel("导出文件夹").fill("Other folder");
  await expect(panel.getByRole("button", { name: "立即同步到 Obsidian" })).toBeDisabled();
  expect(actions).toEqual(["sync", "register", "open", "sync", "sync", "disable"]);
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
  await panel.screenshot({ path: testInfo.outputPath("obsidian-mobile.png") });
});

test("server Obsidian panel explains the desktop connection without local controls", async ({ page }) => {
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: { complete: true, steps: {} } }));
  await page.route("**/api/obsidian", (route) => route.fulfill({ json: { supported: false, config: null, vaults: [], last_sync: null, scheduler: { tasks: [] } } }));
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const panel = page.getByRole("region", { name: "Obsidian 连接" });
  await expect(panel.getByText("请在 Windows 本机版的设置页连接 Obsidian 文库。", { exact: false })).toBeVisible();
  await expect(panel.getByRole("button")).toHaveCount(0);
});
