import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.resolve(currentDir, "../../test-results/p2-regression-20260924");
const navigation = ["工作台", "每日订阅", "Prompt 版本", "设置"];

async function useCompletedOnboarding(page: Page) {
  await page.route("**/api/onboarding", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        complete: true,
        data_dir: "playwright-data",
        steps: { data: true, llm: true, smtp: true, sources: true, scheduler: true },
      }),
    });
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
}

test("desktop cold load remains error-free across StrictMode initialization", async ({ page }) => {
  await useCompletedOnboarding(page);
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await page.goto("/");
    await expect(page.getByText("本地服务已连接")).toBeVisible();
    await expect(page.locator(".global-error")).toHaveCount(0);
  }
});

for (const viewport of [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 1000 },
]) {
  test(`${viewport.name} layout has no overflow and keeps all navigation visible`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await useCompletedOnboarding(page);
    await page.goto("/");
    await expect(page.getByText("本地服务已连接")).toBeVisible();

    for (const label of navigation) {
      await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
    }

    for (const label of navigation) {
      await page.getByRole("button", { name: label, exact: true }).click();
      await expectNoHorizontalOverflow(page);
      const controls = page.locator("main input:visible, main textarea:visible, main select:visible");
      for (let index = 0; index < await controls.count(); index += 1) {
        const box = await controls.nth(index).boundingBox();
        expect(box, `control ${index} on ${label} should have a layout box`).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 0.5);
      }
    }

    await page.getByRole("button", { name: "工作台", exact: true }).click();
    await page.screenshot({ path: path.join(screenshotDir, `workspace-${viewport.name}-fixed.png`), fullPage: true });
  });
}

test("rapid task switching keeps only the final task data", async ({ page, request }) => {
  const suffix = Date.now();
  const slowName = `Switch slow ${suffix}`;
  const finalName = `Switch final ${suffix}`;
  const create = async (name: string) => {
    const response = await request.post("/api/tasks", { data: { name, topic: name, target_count: 1, sources: ["openalex"] } });
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const slowTask = await create(slowName);
  const finalTask = await create(finalName);

  await useCompletedOnboarding(page);
  await page.route(`**/api/tasks/${slowTask.id}/runs*`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.continue();
  });
  await page.goto("/");
  await expect(page.getByText("本地服务已连接")).toBeVisible();

  await page.locator(".recent-task-main", { hasText: slowName }).click();
  await page.locator(".recent-task-main", { hasText: finalName }).click();
  await expect(page.locator(".run-task strong")).toHaveText(finalName);
  await page.waitForTimeout(600);
  await expect(page.locator(".run-task strong")).toHaveText(finalName);
});
