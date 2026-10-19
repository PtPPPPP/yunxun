import { expect, test, type Page } from "playwright/test";
import { join } from "node:path";
import { tmpdir } from "node:os";

const apiURL = "http://127.0.0.1:8011/api";
const guide = (page: Page) => page.getByRole("region", { name: "首次使用引导" });
async function get(page: Page, path: string) { return (await page.request.get(`${apiURL}${path}`)).json(); }
async function write(page: Page, path: string, data?: Record<string, unknown>, method = "POST") {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const response = await page.request.fetch(`${apiURL}${path}`, { method, data, headers: { "X-CSRF-Token": csrf } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function login(page: Page, registered = false) {
  await page.goto("/");
  if (registered) {
    await page.getByRole("button", { name: "注册", exact: true }).click();
    await page.getByLabel("显示名称").fill("新农户");
    await page.getByLabel("用户名").fill(`guest_${Date.now().toString(16)}`);
    await page.getByLabel("密码").fill("test-password");
    await page.getByRole("button", { name: "注册并进入" }).click();
  } else await page.getByRole("button", { name: "访客登录" }).click();
  await expect(guide(page)).toContainText("0/3 步已完成");
}
async function realPlot(page: Page) {
  return (await write(page, "/plots", { name: "自己的东田", area_mu: 2, soil_type: "壤土", irrigation: "井灌", crop: "玉米", planted_on: "2026-01-01" })).plot;
}
async function load(page: Page) {
  await guide(page).getByRole("button", { name: "加载演示数据", exact: true }).click();
  await expect(guide(page).getByRole("button", { name: "只清空演示数据" })).toBeVisible();
  await expect(page.locator(".home-summary .stat-card strong").last()).toHaveText("3");
}
async function navigate(page: Page, name: string) {
  if (await page.getByRole("button", { name: "打开导航" }).isVisible()) await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("navigation", { name: "功能菜单" }).getByRole("button", { name, exact: true }).click();
}

test("注册用户通过三步入口完成第一笔真实农活，不重复建立第一茬", async ({ page }) => {
  await login(page, true);
  expect((await get(page, "/plots")).plots).toHaveLength(0);
  await expect(guide(page).getByRole("button", { name: "加载演示数据" })).toHaveCount(0);
  let extraSeasons = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/seasons")) extraSeasons++; });
  await guide(page).getByRole("button", { name: "去登记地块" }).click();
  await page.getByLabel("地块名称").fill("第一块真实田");
  await page.getByLabel("面积（亩）").fill("2");
  await page.getByLabel("播种或定植日期").fill("2026-01-01");
  await page.getByRole("button", { name: "新建地块", exact: true }).click();
  await expect(guide(page)).toContainText("2/3 步已完成");
  await expect(guide(page)).toContainText("第一茬已建立，无需重复创建");
  const { plots } = await get(page, "/plots");
  const { seasons } = await get(page, "/seasons");
  expect(seasons).toHaveLength(1);
  expect(extraSeasons).toBe(0);
  await guide(page).getByRole("button", { name: "去记第一笔农活" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("记录到地块")).toHaveValue(plots[0].id);
  await expect(dialog.getByLabel("所属茬次")).toHaveValue(seasons[0].id);
  await dialog.getByLabel("作业类型").selectOption("施肥");
  await dialog.getByLabel("费用（元）").fill("25");
  await dialog.getByText("补充用量、作物与说明（选填）", { exact: true }).click();
  await dialog.getByLabel("作业说明").fill("今天实际追肥");
  await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(guide(page)).toContainText("已完成第一条真实业务流程");
  expect((await get(page, "/farm-records")).records).toHaveLength(1);
  expect((await get(page, "/seasons")).seasons).toHaveLength(1);
  await guide(page).getByRole("button", { name: "查看收支", exact: true }).click();
  await expect(page.getByLabel("收支数据来源")).toHaveValue("real");
  await expect(page.locator(".economics-panel .stat-card").filter({ hasText: "已记录支出" })).toContainText("¥25");
});

test("跳过和继续跨刷新保留，完成状态随真实业务增删变化", async ({ page }) => {
  await login(page);
  await guide(page).getByRole("button", { name: "暂时跳过" }).click();
  await page.reload();
  await expect(guide(page).getByRole("button", { name: "继续引导" })).toBeVisible();
  await expect(guide(page).getByRole("button", { name: "去登记地块" })).toHaveCount(0);
  const plot = await realPlot(page);
  await page.reload();
  await expect(guide(page)).toContainText("2/3 步已完成");
  await guide(page).getByRole("button", { name: "继续引导" }).click();
  await expect(guide(page)).toContainText("✓ 已完成：登记第一块地");
  await expect(guide(page).getByRole("button", { name: "去记第一笔农活" })).toBeEnabled();
  await write(page, `/plots/${plot.id}`, undefined, "DELETE");
  await page.reload();
  await expect(guide(page)).toContainText("0/3 步已完成");
  await expect(guide(page).getByRole("button", { name: "去登记地块" })).toBeVisible();
});

test("缺少第一茬时直接补建，返回地块不会再次打开建茬表单", async ({ page }) => {
  await login(page);
  const plot = await realPlot(page);
  await write(page, `/seasons/${plot.active_season.id}`, undefined, "DELETE");
  await page.reload();
  await expect(guide(page)).toContainText("1/3 步已完成");
  await guide(page).getByRole("button", { name: "去建立第一茬" }).click();
  await expect(page.getByRole("heading", { name: "开始新茬", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "确认开始新茬" }).click();
  await expect(guide(page)).toContainText("2/3 步已完成");
  expect((await get(page, "/seasons")).seasons).toHaveLength(1);
  await navigate(page, "首页");
  await navigate(page, "地块档案");
  await expect(page.getByRole("heading", { name: "新建地块", exact: true })).toBeVisible();
});

test("演示数据明确标识、重复加载不重复，收支和追溯可与真实记录分开查看", async ({ page }) => {
  await login(page);
  expect((await get(page, "/plots")).plots).toHaveLength(0);
  await load(page);
  const seeded = (await get(page, "/farm-records")).records;
  await Promise.all([write(page, "/demo-data"), write(page, "/demo-data")]);
  expect((await get(page, "/farm-records")).records).toEqual(seeded);
  expect((await get(page, "/plots")).plots).toHaveLength(1);
  await expect(guide(page)).toContainText("0/3 步已完成");
  await expect(guide(page)).toContainText("不代表真实经营成果");
  await navigate(page, "地块档案");
  await expect(page.locator(".plot-card .demo-badge")).toHaveText("演示");
  await expect(page.locator(".plot-card")).toContainText("番茄");
  await navigate(page, "农事台账");
  await expect(page.locator(".stats-records .demo-badge")).toHaveCount(3);
  await page.getByLabel("台账数据来源").selectOption("real");
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(0);
  await page.getByLabel("台账数据来源").selectOption("demo");
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(3);
  await navigate(page, "农事待办");
  await expect(page.locator(".task-list .demo-badge")).toHaveCount(2);
  await guide(page).getByRole("button", { name: "查看演示收支" }).click();
  await expect(page.getByLabel("收支数据来源")).toHaveValue("demo");
  await expect(page.locator(".economics-panel")).toContainText("演示收支：示例金额不代表真实经营成果");
  await expect(page.locator(".economics-panel .stat-card").filter({ hasText: "已记录支出" })).toContainText("¥200");
  await expect(page.locator(".economics-panel .stat-card").filter({ hasText: "已记录收入" })).toContainText("¥600");
  await page.getByRole("button", { name: "查看当前范围收入台账", exact: true }).click();
  await expect(page.getByLabel("台账数据来源")).toHaveValue("demo");
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(1);
  await expect(page.locator(".stats-records .demo-badge")).toHaveText("演示记录");
  await page.getByRole("button", { name: "返回收支统计" }).click();
  await page.getByLabel("收支数据来源").selectOption("real");
  await expect(page.locator(".economics-table tbody tr")).toHaveCount(0);
});

test("只清空演示数据，独立真实地块、台账和杂事仍保留", async ({ page }) => {
  await login(page);
  await load(page);
  const plot = await realPlot(page);
  const { record } = await write(page, "/farm-records", { plot_id: plot.id, kind: "施肥", happened_on: "2026-10-19", cost: 35 });
  const { task } = await write(page, "/farm-tasks", { title: "我的杂事", due_on: "2026-10-19" });
  await page.reload();
  await guide(page).getByRole("button", { name: "只清空演示数据" }).click();
  await expect(guide(page)).toContainText("演示数据已清空");
  expect((await get(page, "/plots")).plots.map((row: { id: string }) => row.id)).toEqual([plot.id]);
  expect((await get(page, "/farm-records")).records.map((row: { id: string }) => row.id)).toEqual([record.id]);
  expect((await get(page, "/farm-tasks")).tasks.map((row: { id: string }) => row.id)).toEqual([task.id]);
  await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["0", "1", "1", "1"]);
  await navigate(page, "统计面板");
  await expect(page.getByLabel("收支数据来源")).toHaveValue("real");
  await expect(page.locator(".economics-panel .stat-card").filter({ hasText: "已记录支出" })).toContainText("¥35");
});

test("演示地块下新增自己的记录，清空后保留关联并可再次加载新演示", async ({ page }) => {
  await login(page);
  await load(page);
  const plot = (await get(page, "/plots")).plots[0];
  const { record } = await write(page, "/farm-records", { plot_id: plot.id, season_id: plot.active_season.id, kind: "其他", happened_on: plot.active_season.started_on, cost: 45 });
  const { task } = await write(page, "/farm-tasks", { plot_id: plot.id, title: "自己的安排", due_on: "2026-10-19" });
  await page.reload();
  await guide(page).getByRole("button", { name: "只清空演示数据" }).click();
  await expect(guide(page)).toContainText("1 个地块、1 个茬次已转为普通资料");
  const retained = (await get(page, "/plots")).plots[0];
  expect(retained.id).toBe(plot.id);
  expect(retained.is_demo).toBe(false);
  expect((await get(page, "/farm-records")).records).toEqual([record]);
  expect((await get(page, "/farm-tasks")).tasks).toEqual([task]);
  await guide(page).getByRole("button", { name: "加载演示数据", exact: true }).click();
  await expect(guide(page).getByRole("button", { name: "只清空演示数据" })).toBeVisible();
  const plots = (await get(page, "/plots")).plots;
  expect(plots).toHaveLength(2);
  expect(plots.find((row: { is_demo: boolean }) => row.is_demo).id).not.toBe(plot.id);
  expect((await get(page, "/farm-records")).records).toHaveLength(4);
});

test("演示加载失败可重试，手机重复点击只发出一次加载", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.route("**/api/demo-data", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "演示暂时无法加载" }) }));
  await guide(page).getByRole("button", { name: "加载演示数据", exact: true }).click();
  await expect(guide(page).getByRole("alert")).toContainText("演示暂时无法加载");
  expect((await get(page, "/plots")).plots).toHaveLength(0);
  await page.unroute("**/api/demo-data");
  let writes = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/demo-data")) writes++; });
  await guide(page).getByRole("button", { name: "加载演示数据", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(guide(page).getByRole("button", { name: "只清空演示数据" })).toBeVisible();
  expect(writes).toBe(1);
  expect((await get(page, "/farm-records")).records).toHaveLength(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(tmpdir(), "yunxun-onboarding-mobile.png"), fullPage: true });
});
