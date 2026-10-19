import { expect, test, type Page } from "playwright/test";

const apiURL = "http://127.0.0.1:8011/api";

async function write(page: Page, path: string, data: object, method = "POST") {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const response = await page.request.fetch(`${apiURL}${path}`, { method, data, headers: { "X-CSRF-Token": csrf } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

async function setup(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("main")).toBeVisible();
  const { plot } = await write(page, "/plots", {
    name: "重构试验田", area_mu: 2, crop: "玉米", planted_on: "2026-04-01", soil_type: "壤土", irrigation: "井灌",
  });
  await write(page, "/onboarding", { skipped: true }, "PATCH");
  await page.reload();
  await expect(page.locator(".home-plots")).toContainText("重构试验田");
  return plot;
}

test("列表筛选不重建失败后的表单，已落库但响应丢失的重试保持同一提交标识", async ({ page }) => {
  await setup(page);
  await page.getByRole("navigation", { name: "功能菜单" }).getByRole("button", { name: "农事台账", exact: true }).click();
  const form = page.locator("#ledger-record-form");
  await form.getByLabel("作业日期", { exact: true }).fill("2026-04-15");
  await form.getByLabel("费用（元）").fill("28");
  const submissions: string[] = [];
  await page.route("**/api/farm-records", async (route) => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    submissions.push(route.request().postDataJSON().submission_id);
    const response = await route.fetch();
    if (submissions.length === 1) await route.abort("failed");
    else await route.fulfill({ response });
  });
  await form.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(form).toContainText("本次保存尚未确认");
  await page.getByLabel("按作业类型筛选").selectOption("施肥");
  await expect(page.locator(".stats-record")).toHaveCount(1);
  await expect(form.getByLabel("费用（元）")).toHaveValue("28");
  await expect(form.getByLabel("作业日期", { exact: true })).toHaveValue("2026-04-15");
  await form.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(form.locator(".ledger-save-notice")).toContainText("已记入台账");
  expect(submissions).toHaveLength(2);
  expect(submissions[0]).toBeTruthy();
  expect(submissions[1]).toBe(submissions[0]);
  const records = (await (await page.request.get(`${apiURL}/farm-records`)).json()).records;
  expect(records).toHaveLength(1);
  expect(records[0].cost).toBe(28);
});

test("手机独立记账不查询台账列表，嵌套放弃确认保留输入并恢复焦点和滚动", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  let listRequests = 0;
  await page.route("**/api/farm-records**", async (route) => {
    if (route.request().method() === "GET") listRequests += 1;
    await route.continue();
  });
  const opener = page.getByRole("button", { name: "为重构试验田记农活" });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "记一笔农活", exact: true });
  const cost = dialog.getByLabel("费用（元）");
  await cost.fill("11");
  await page.keyboard.press("Escape");
  const discard = page.getByRole("dialog", { name: "放弃未保存的农活？" });
  await expect(discard).toBeVisible();
  await discard.getByRole("button", { name: "取消", exact: true }).click();
  await expect(cost).toHaveValue("11");
  await expect(cost).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.keyboard.press("Escape");
  await discard.getByRole("button", { name: "放弃并离开" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflow)).not.toBe("hidden");
  expect(listRequests).toBe(0);
});

test("删除当前编辑记录时共用写操作互斥，并复位编辑器而不保存未提交修改", async ({ page }) => {
  const plot = await setup(page);
  const { record } = await write(page, "/farm-records", {
    plot_id: plot.id, happened_on: "2026-04-15", kind: "施肥", cost: 20,
  });
  await page.getByRole("navigation", { name: "功能菜单" }).getByRole("button", { name: "农事台账", exact: true }).click();
  const row = page.locator(".stats-record");
  await row.getByRole("button", { name: "编辑 施肥 记录" }).click();
  const form = page.locator("#ledger-record-form");
  await form.getByLabel("费用（元）").fill("55");
  let arrived!: () => void, release!: () => void;
  const entered = new Promise<void>((resolve) => { arrived = resolve; });
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`**/api/farm-records/${record.id}`, async (route) => {
    arrived();
    await gate;
    await route.continue();
  });
  await row.getByRole("button", { name: "删除 施肥 记录" }).click();
  await page.getByRole("dialog", { name: "删除这条农事记录？" }).getByRole("button", { name: "确认删除" }).click();
  await entered;
  try {
    await expect(form.getByRole("button", { name: "保存中…" })).toBeDisabled();
    await expect(form.getByLabel("费用（元）")).toBeDisabled();
    await expect(page.getByLabel("按地块筛选")).toBeDisabled();
  } finally { release(); }
  await expect(row).toHaveCount(0);
  await expect(form.getByRole("heading", { name: "记一次农事" })).toBeVisible();
  await expect(form.getByLabel("费用（元）")).toHaveValue("");
  await expect(form.getByRole("button", { name: "取消编辑" })).toHaveCount(0);
  await write(page, `/trash/records/${record.id}/restore`, {});
  const records = (await (await page.request.get(`${apiURL}/farm-records`)).json()).records;
  expect(records[0].cost).toBe(20);
});
