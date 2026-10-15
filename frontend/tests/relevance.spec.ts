import { expect, test } from "@playwright/test";

for (const selectedCount of [0, 1]) {
  test(`completed run explains relevance filtering with ${selectedCount} selected papers`, async ({ page }) => {
    const task = { id: "relevance-task", name: "Relevance regression", topic: "智能体检索增强生成",
      language: "bilingual", output_language: "zh", target_count: 50, sources: ["openalex"],
      origin: "user", created_at: "2026-10-15T11:00:00Z", date_from: "2023-01-01", date_to: "2026-10-15" };
    const run = { id: "relevance-run", task_id: task.id, status: "completed", current_node: "completed",
      paper_count: selectedCount, progress: 6, total_steps: 6, error: "" };
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/onboarding") return route.fulfill({ json: { complete: true, steps: {} } });
      if (path === "/api/tasks") return route.fulfill({ json: [task] });
      if (path === `/api/tasks/${task.id}/runs`) return route.fulfill({ json: [run] });
      if (path === `/api/runs/${run.id}`) return route.fulfill({ json: run });
      if (path.endsWith("/decisions")) return route.fulfill({ json: [] });
      if (path.endsWith("/decisions/summary")) return route.fulfill({ json: { total: 0 } });
      if (path.endsWith("/events")) return route.fulfill({ json: [] });
      if (path.endsWith("/papers")) return route.fulfill({ json: selectedCount ? [{
        id: "relevant-paper", run_id: run.id, title: "Agentic retrieval evaluation", authors: [],
        published_date: "2025-01-01", source: "openalex", relevance_score: .55, priority: "P1",
        abstract: "An evaluation of agentic retrieval.", summary: {}, review: "unreviewed",
      }] : [] });
      if (path.endsWith("/artifacts")) return route.fulfill({ json: [
        { node: "query_planner", payload: { ...task, query_plan: { queries: ["智能体 检索增强生成", "agentic retrieval augmented generation"] } } },
        { node: "retrieval", payload: { sources: { openalex: { status: "ok", count: 7, error: "" } } } },
        { node: "relevance_screener", payload: { evaluated_count: 7, rejected_count: 7 - selectedCount,
          selected_count: selectedCount, minimum_relevance_score: .4 } },
      ] });
      return route.continue();
    });
    await page.goto("/");
    await expect(page.getByRole("status")).toContainText(`评估 7 篇 · 筛除 ${7 - selectedCount} 篇 · 入选 ${selectedCount} 篇`);
    await expect(page.getByRole("status")).toContainText("符合要求的文献不足目标数量");
    await page.getByText("本次检索条件", { exact: true }).click();
    await expect(page.getByText("日期范围：2023-01-01 至 2026-10-15", { exact: true })).toBeVisible();
    await expect(page.getByText("agentic retrieval augmented generation", { exact: true })).toBeVisible();
    if (!selectedCount) await expect(page.getByText("本次运行没有符合要求的论文", { exact: true })).toBeVisible();
    await expect(page.locator(".paper-row")).toHaveCount(selectedCount);
    if (selectedCount) await expect(page.locator(".paper-row")).toContainText("背景参考");
    await expect(page.locator(".global-error")).toHaveCount(0);
  });
}
