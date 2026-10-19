import { expect, test, type Page } from "playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const apiURL = "http://127.0.0.1:8011/api";

async function post(page: Page, path: string, data: Record<string, unknown>, method = "POST") {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const response = await page.request.fetch(`${apiURL}${path}`, { method, data, headers: { "X-CSRF-Token": csrf } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("heading", { name: "首页", exact: true })).toBeVisible();
}

async function prepare(page: Page, misc = false) {
  await login(page);
  const today = await page.evaluate(() => {
    const date = new Date();
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  });
  const { plot } = await post(page, "/plots", { name: "东田", area_mu: 2, soil_type: "壤土", irrigation: "井灌", crop: "玉米", planted_on: "2026-01-01" });
  const { task } = await post(page, "/farm-tasks", { plot_id: misc ? null : plot.id, title: misc ? "去镇上买地膜" : "东田追肥", due_on: today, notes: "核对实际用量" });
  await post(page, "/farm-tasks", { plot_id: plot.id, title: "逾期查苗", due_on: "2025-01-01" });
  await page.reload();
  await expect(page.getByRole("region", { name: "今日待办" }).getByText(task.title)).toBeVisible();
  return { plot, task, today };
}

async function records(page: Page) {
  return (await (await page.request.get(`${apiURL}/farm-records`)).json()).records;
}

async function completeAndOpen(page: Page, title: string, doubleClick = false) {
  const button = page.getByRole("region", { name: "今日待办" }).locator(".task-card").filter({ hasText: title }).getByRole("button", { name: "标记完成" });
  if (doubleClick) await button.evaluate((element: HTMLButtonElement) => { element.click(); element.click(); });
  else await button.click();
  const prompt = page.getByRole("region", { name: "待办完成提示" });
  await expect(prompt).toContainText(title);
  await prompt.getByRole("button", { name: "顺便记入台账" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test("默认首页提供真实空状态和下一步入口", async ({ page }) => {
  await login(page);
  await expect(page.getByText("还没有未完成待办", { exact: true })).toBeVisible();
  await expect(page.getByText("先登记一块地", { exact: true })).toBeVisible();
  await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["0", "0", "0", "0"]);
  await page.getByRole("button", { name: "记一笔农活", exact: true }).click();
  await expect(page.getByRole("heading", { name: "地块档案", exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("请先登记地块");
});

test("首页完成待办再确认记账，重复点击只保存一笔并可查看统计", async ({ page }) => {
  const { plot, task, today } = await prepare(page);
  await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["1", "1", "1", "0"]);
  let completions = 0;
  page.on("request", (request) => { if (request.method() === "PATCH" && request.url().endsWith(`/farm-tasks/${task.id}`)) completions++; });
  await completeAndOpen(page, task.title, true);
  expect(completions).toBe(1);
  expect(await records(page)).toHaveLength(0);
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("记录到地块")).toHaveValue(plot.id);
  await expect(dialog.getByLabel("所属茬次")).toHaveValue(plot.active_season.id);
  await expect(dialog.getByRole("textbox", { name: "作业日期", exact: true })).toHaveValue(today);
  await dialog.getByLabel("作业类型").selectOption("施肥");
  await dialog.getByLabel("费用（元）").fill("35");
  let writes = 0;
  await page.route("**/api/farm-records", async (route) => {
    if (route.request().method() === "POST") { writes++; await new Promise((resolve) => setTimeout(resolve, 150)); }
    await route.continue();
  });
  await dialog.getByRole("button", { name: "记入台账", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(dialog).toHaveCount(0);
  expect(writes).toBe(1);
  expect(await records(page)).toHaveLength(1);
  await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["1", "0", "1", "1"]);
  await expect(page.locator(".home-plots")).toContainText("待办 1 项");
  await page.getByRole("button", { name: "统计面板", exact: true }).click();
  const row = page.locator(".economics-table tbody tr");
  await expect(row).toContainText("1 次");
  await expect(row.locator("td").nth(5)).toContainText("¥35");
});

test("取消记账不创建记录也不撤销完成状态，可以稍后再记", async ({ page }) => {
  const { task } = await prepare(page);
  await completeAndOpen(page, task.title);
  const before = (await (await page.request.get(`${apiURL}/farm-tasks`)).json()).recent_done[0];
  await page.getByRole("dialog").getByRole("button", { name: "取消记账" }).click();
  expect(await records(page)).toHaveLength(0);
  const after = (await (await page.request.get(`${apiURL}/farm-tasks`)).json()).recent_done[0];
  expect(after.done).toBe(true);
  expect(after.done_at).toBe(before.done_at);
  await page.getByRole("region", { name: "待办完成提示" }).getByRole("button", { name: "暂不记账" }).click();
  await page.getByRole("button", { name: "农事待办", exact: true }).click();
  await page.locator(".task-card--done").getByRole("button", { name: "顺便记入台账" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(await records(page)).toHaveLength(0);
});

test("完成待办请求失败时保留未完成状态，不打开记账", async ({ page }) => {
  const { task } = await prepare(page);
  await page.route(`**/api/farm-tasks/${task.id}`, (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ success: false, error: "完成失败，请重试" }) }));
  const card = page.getByRole("region", { name: "今日待办" }).locator(".task-card").filter({ hasText: task.title });
  await card.getByRole("button", { name: "标记完成" }).click();
  await expect(page.locator(".toast-banner")).toContainText("完成失败");
  await expect(card).toBeVisible();
  await expect(page.getByRole("region", { name: "待办完成提示" })).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await records(page)).toHaveLength(0);
  const tasks = (await (await page.request.get(`${apiURL}/farm-tasks`)).json()).tasks;
  expect(tasks.find((item: { id: string; done: boolean }) => item.id === task.id).done).toBe(false);
  await page.unroute(`**/api/farm-tasks/${task.id}`);
  await completeAndOpen(page, task.title);
  expect(await records(page)).toHaveLength(0);
});

test("杂事正常完成，记账必须手动选地块；保存失败后可重试", async ({ page }) => {
  const { task, plot } = await prepare(page, true);
  await completeAndOpen(page, task.title);
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("记录到地块")).toHaveValue("");
  await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("请先选择地块");
  expect(await records(page)).toHaveLength(0);
  await dialog.getByLabel("记录到地块").selectOption(plot.id);
  await page.route("**/api/farm-records", async (route) => {
    if (route.request().method() === "POST") await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "模拟保存失败" }) });
    else await route.continue();
  });
  await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  expect(await records(page)).toHaveLength(0);
  await expect(dialog.getByLabel("作业说明")).toHaveValue(`${task.title}；核对实际用量`);
  const completed = (await (await page.request.get(`${apiURL}/farm-tasks`)).json()).recent_done[0];
  expect(completed.done).toBe(true);
  await page.unroute("**/api/farm-records");
  await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(await records(page)).toHaveLength(1);
  const retried = (await (await page.request.get(`${apiURL}/farm-tasks`)).json()).recent_done[0];
  expect(retried.done_at).toBe(completed.done_at);
});

test("已落库但响应丢失后重试仍只有一笔", async ({ page }) => {
  const { task } = await prepare(page);
  await completeAndOpen(page, task.title);
  let first = true;
  await page.route("**/api/farm-records", async (route) => {
    if (route.request().method() === "POST" && first) {
      first = false;
      const response = await route.fetch();
      expect(response.ok()).toBeTruthy();
      await route.abort("failed");
    } else await route.continue();
  });
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  const saved = await records(page);
  expect(saved).toHaveLength(1);
  await dialog.getByRole("button", { name: "取消记账" }).click();
  await page.getByRole("dialog", { name: "放弃未保存的农活？" }).getByRole("button", { name: "放弃并离开" }).click();
  await page.reload();
  await page.getByRole("button", { name: "农事待办", exact: true }).click();
  await page.locator(".task-card--done").getByRole("button", { name: "顺便记入台账" }).click();
  await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect((await records(page))[0].id).toBe(saved[0].id);
  expect(await records(page)).toHaveLength(1);
});

test("首页直接记账刷新计数，间隔提醒复用登记结果，手机导航和帮助可用", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  // 模拟手机通过局域网 HTTP 访问时缺少 randomUUID 的环境。
  await page.addInitScript(() => Object.defineProperty(crypto, "randomUUID", { value: undefined }));
  const { plot } = await prepare(page);
  await page.getByRole("button", { name: "记一笔农活", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("记录到地块").selectOption(plot.id);
  await dialog.getByRole("group", { name: "快捷农活" }).getByRole("button", { name: "打药", exact: true }).click();
  await dialog.getByLabel("农药名称").fill("已登记产品");
  await dialog.getByLabel("安全间隔期（天）").fill("30");
  await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.locator(".home-summary .stat-card strong").last()).toHaveText("1");
  const plots = (await (await page.request.get(`${apiURL}/plots`)).json()).plots;
  await expect(page.getByRole("region", { name: "登记间隔期提醒" })).toContainText(plots[0].harvest_safety.earliest_harvest_on);
  await expect(page.getByRole("region", { name: "登记间隔期提醒" })).toContainText("按登记数据计算");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(tmpdir(), "yunxun-home-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name: "使用帮助" }).click();
  await expect(page.getByRole("dialog")).toContainText("使用帮助");
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "关于软件" }).click();
  await expect(page.getByRole("dialog")).toContainText("云寻");
});
