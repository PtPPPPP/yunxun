import { expect, test, type Page } from "playwright/test";

const apiURL = "http://127.0.0.1:8011/api";
async function get(page: Page, path: string) { return (await page.request.get(`${apiURL}${path}`)).json(); }
async function write(page: Page, path: string, data?: Record<string, unknown>, method = "POST") {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const response = await page.request.fetch(`${apiURL}${path}`, { method, data, headers: { "X-CSRF-Token": csrf } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function navigate(page: Page, name: string) {
  if (await page.getByRole("button", { name: "打开导航" }).isVisible()) await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name, exact: true }).click();
}
async function seed(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录", exact: true }).click();
  await expect(page.getByRole("main")).toBeVisible();
  const { plot } = await write(page, "/plots", { name: "可恢复的田", area_mu: 2, crop: "玉米", soil_type: "壤土", irrigation: "井灌", planted_on: "2026-04-01" });
  const first = plot.active_season.id;
  await write(page, `/seasons/${first}`, { crop: "玉米", started_on: "2026-04-01", ended_on: "2026-05-31" }, "PATCH");
  await write(page, "/seasons", { plot_id: plot.id, crop: "大豆", started_on: "2026-10-01" });
  const record = (data: Record<string, unknown>) => write(page, "/farm-records", { plot_id: plot.id, season_id: first, kind: "施肥", happened_on: "2026-04-30", ...data });
  await record({ cost: 30, detail: "保留的支出" });
  await record({ kind: "采收", happened_on: "2026-05-31", cost: 0, yield_kg: 100, unit_price: 2, detail: "保留的收入" });
  const { record: independent } = await record({ cost: 7, detail: "单独删除的支出" });
  const { task } = await write(page, "/farm-tasks", { plot_id: plot.id, title: "未完成的巡田", due_on: "2026-10-19" });
  const { task: done } = await write(page, "/farm-tasks", { plot_id: plot.id, title: "已经完成的工作", due_on: "2026-10-19" });
  await write(page, `/farm-tasks/${done.id}`, { plot_id: plot.id, title: done.title, due_on: done.due_on, done: true }, "PATCH");
  await page.reload();
  await expect(page.getByRole("main")).toBeVisible();
  return { plot, independent, task, first };
}
async function snapshot(page: Page) {
  const [plots, seasons, records, tasks] = await Promise.all([get(page, "/plots"), get(page, "/seasons"), get(page, "/farm-records"), get(page, "/farm-tasks")]);
  return { plots: plots.plots, seasons: seasons.seasons, records: records.records, tasks: tasks.tasks, done: tasks.recent_done };
}
async function deletePlot(page: Page) {
  await navigate(page, "地块档案");
  await page.locator(".plot-card").getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("2 茬");
  await page.getByRole("dialog").getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.locator(".plot-card")).toHaveCount(0);
}

test("地块删除说明全部影响范围，恢复关联及单独删除台账后收支完整还原", async ({ page }) => {
  const { plot, independent } = await seed(page);
  const before = await snapshot(page);
  await navigate(page, "农事台账");
  await page.locator(".stats-record").filter({ hasText: "单独删除的支出" }).getByRole("button", { name: "删除 施肥 记录" }).click();
  await expect(page.getByRole("dialog")).toContainText("移入回收站，可恢复");
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.locator(".stats-record")).toHaveCount(2);
  await navigate(page, "地块档案");
  await page.locator(".plot-card").getByRole("button", { name: "删除", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("2 茬");
  await expect(dialog).toContainText("3 条农事台账记录");
  await expect(dialog).toContainText("已单独删除 1 条");
  await expect(dialog).toContainText("2 项待办（含已完成）");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.locator(".plot-card")).toHaveCount(1);
  expect((await get(page, "/trash")).plots).toHaveLength(0);
  await deletePlot(page);
  await navigate(page, "首页");
  await expect(page.getByText("未完成的巡田", { exact: true })).toHaveCount(0);
  await navigate(page, "今日农活");
  await expect(page.locator("select option").filter({ hasText: plot.name })).toHaveCount(0);
  await navigate(page, "统计面板");
  await expect(page.locator(".stat-card").filter({ hasText: "地块数" })).toContainText("0");
  await expect(page.locator(".stat-card").filter({ hasText: "作业记录" })).toContainText("0");
  await expect(page.locator(".economics-table tbody tr")).toHaveCount(0);
  await navigate(page, "回收站");
  const plots = page.getByRole("region", { name: "回收站地块" });
  const records = page.getByRole("region", { name: "回收站台账" });
  await expect(plots).toContainText("2 茬、3 条台账");
  await expect(records.getByRole("button", { name: "恢复台账 施肥 2026-04-30" })).toBeDisabled();
  await plots.getByRole("button", { name: `恢复地块 ${plot.name}`, exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(plots.locator(".trash-card")).toHaveCount(0);
  await expect(records.getByRole("button", { name: "恢复台账 施肥 2026-04-30" })).toBeEnabled();
  expect((await get(page, "/farm-records")).records.some((row: { id: string }) => row.id === independent.id)).toBe(false);
  await records.getByRole("button", { name: "恢复台账 施肥 2026-04-30" }).click();
  await expect(records.locator(".trash-card")).toHaveCount(0);
  expect(await snapshot(page)).toEqual(before);
  await navigate(page, "统计面板");
  await expect(page.locator(".stat-card").filter({ hasText: "已记录收支差额" })).toContainText("¥163");
});

test("最终删除有明确确认，取消保留资料，确认后不可恢复", async ({ page }) => {
  const { plot } = await seed(page);
  await deletePlot(page);
  await navigate(page, "回收站");
  await page.getByRole("button", { name: `最终删除地块 ${plot.name}`, exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("2 茬、3 条台账");
  await expect(page.getByRole("dialog")).toContainText("无法再从回收站恢复");
  await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
  expect((await get(page, "/trash")).plots).toHaveLength(1);
  await page.getByRole("button", { name: `最终删除地块 ${plot.name}`, exact: true }).click();
  await page.getByRole("button", { name: "最终删除（不可恢复）", exact: true }).click();
  await expect(page.getByRole("region", { name: "回收站地块" })).toContainText("没有已删除地块");
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  expect((await page.request.post(`${apiURL}/trash/plots/${plot.id}/restore`, { headers: { "X-CSRF-Token": csrf } })).status()).toBe(404);
  await expect(page.getByRole("region", { name: "回收站资料" })).toContainText("当前没有自动清理");
});

test("核对失败不能确认删除，关联数量变化时要求重新核对", async ({ page }) => {
  const { plot, first } = await seed(page);
  await navigate(page, "地块档案");
  await page.route("**/api/plots/*/delete-impact", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "影响范围暂时无法读取" }) }));
  await page.locator(".plot-card").getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("影响范围暂时无法读取");
  await expect(page.getByRole("button", { name: "确认删除", exact: true })).toBeDisabled();
  await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
  await page.unroute("**/api/plots/*/delete-impact");
  await page.locator(".plot-card").getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("3 条农事台账记录");
  await write(page, "/farm-records", { plot_id: plot.id, season_id: first, kind: "施肥", happened_on: "2026-04-30", cost: 1 });
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("请取消并重新核对");
  await expect(page.getByRole("button", { name: "确认删除", exact: true })).toBeDisabled();
  expect((await get(page, "/plots")).plots).toHaveLength(1);
  await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
  await page.locator(".plot-card").getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("4 条农事台账记录");
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.locator(".plot-card")).toHaveCount(0);
});

test("手机回收站读取失败可重试，恢复冲突保留原资料且可再次恢复", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { plot } = await seed(page);
  await deletePlot(page);
  await page.route("**/api/trash", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "回收站读取失败" }) }));
  await navigate(page, "回收站");
  await expect(page.getByRole("alert")).toContainText("回收站读取失败");
  await expect(page.getByText("没有已删除地块。", { exact: true })).toHaveCount(0);
  await page.unroute("**/api/trash");
  await page.getByRole("button", { name: "刷新回收站", exact: true }).click();
  await expect(page.getByRole("button", { name: `恢复地块 ${plot.name}`, exact: true })).toBeVisible();
  await page.route("**/api/trash/plots/*/restore", (route) => route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: "检测到多个进行中茬次，未恢复或覆盖数据。" }) }));
  await page.getByRole("button", { name: `恢复地块 ${plot.name}`, exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("未恢复或覆盖数据");
  await expect(page.getByRole("region", { name: "回收站地块" }).locator(".trash-card")).toHaveCount(1);
  await page.unroute("**/api/trash/plots/*/restore");
  await page.getByRole("button", { name: `恢复地块 ${plot.name}`, exact: true }).click();
  await expect(page.getByRole("region", { name: "回收站地块" }).locator(".trash-card")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await navigate(page, "地块档案");
  await expect(page.locator(".plot-card")).toContainText(plot.name);
});

test("单笔台账可最终清理，地块和其他台账保留", async ({ page }) => {
  const { independent } = await seed(page);
  await write(page, `/farm-records/${independent.id}`, undefined, "DELETE");
  await navigate(page, "回收站");
  await page.getByRole("button", { name: "最终删除台账 施肥 2026-04-30", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("所属地块不受影响");
  await page.getByRole("button", { name: "最终删除（不可恢复）", exact: true }).click();
  await expect(page.getByRole("region", { name: "回收站台账" })).toContainText("没有单独删除的台账");
  expect((await get(page, "/plots")).plots).toHaveLength(1);
  expect((await get(page, "/farm-records")).records).toHaveLength(2);
});
