import { expect, test, type Page } from "playwright/test";

const apiURL = "http://127.0.0.1:8011/api";
test.use({ viewport: { width: 390, height: 844 } });

async function write(page: Page, path: string, data: Record<string, unknown>, method = "POST") {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const response = await page.request.fetch(`${apiURL}${path}`, { method, data, headers: { "X-CSRF-Token": csrf } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

async function navigate(page: Page, name: string) {
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("navigation", { name: "功能菜单" }).getByRole("button", { name, exact: true }).click();
}

async function setup(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("heading", { name: "首页", exact: true })).toBeVisible();
  const { plot } = await write(page, "/plots", { name: "手机试验田", area_mu: 2, crop: "玉米", planted_on: "2025-10-01", soil_type: "壤土", irrigation: "井灌" });
  const historicalId = plot.active_season.id as string;
  await write(page, `/seasons/${historicalId}`, { crop: "玉米", started_on: "2025-10-01", ended_on: "2026-05-31" }, "PATCH");
  const { season } = await write(page, "/seasons", { plot_id: plot.id, crop: "大豆", started_on: "2026-10-01" });
  await write(page, "/onboarding", { skipped: true }, "PATCH");
  await page.reload();
  await expect(page.locator(".home-plots")).toContainText("手机试验田");
  return { plotId: plot.id as string, historicalId, currentId: season.id as string };
}

async function records(page: Page) {
  return (await (await page.request.get(`${apiURL}/farm-records`)).json()).records;
}

async function noOverflow(page: Page) {
  const sizes = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: innerWidth,
    dialogs: [...document.querySelectorAll<HTMLElement>(".record-dialog")].map((element) => ({ scroll: element.scrollWidth, client: element.clientWidth })) }));
  expect(sizes.page, JSON.stringify(sizes)).toBeLessThanOrEqual(sizes.viewport);
  for (const dialog of sizes.dialogs) expect(dialog.scroll).toBeLessThanOrEqual(dialog.client);
}

test("390px 从首页和地块快速记账，历史日期重匹配茬次且单茬收支可读", async ({ page }) => {
  const { plotId, historicalId, currentId } = await setup(page);
  await expect(page.getByRole("button", { name: "记一笔农活", exact: true })).toBeInViewport();
  await page.getByRole("button", { name: "为手机试验田记农活" }).click();
  const dialog = page.getByRole("dialog", { name: "记一笔农活", exact: true });
  await expect(dialog.getByLabel("记录到地块")).toHaveValue(plotId);
  await expect(dialog.getByLabel("所属茬次")).toHaveValue(currentId);
  const today = await page.evaluate(() => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10));
  await expect(dialog.getByLabel("作业日期", { exact: true })).toHaveValue(today);
  await dialog.getByLabel("作业日期", { exact: true }).fill("2026-04-30");
  await expect(dialog.locator(".season-hint")).toContainText("玉米（2025-10-01 至 2026-05-31）");
  await dialog.getByRole("group", { name: "快捷农活" }).getByRole("button", { name: "采收", exact: true }).click();
  await dialog.getByLabel("产量（公斤）").fill("100");
  await dialog.getByLabel("单价（元/公斤）").fill("2");
  await dialog.getByLabel("费用（元）").fill("30");
  expect(await dialog.getByLabel("费用（元）").getAttribute("inputmode")).toBe("decimal");
  await noOverflow(page);
  await page.screenshot({ path: test.info().outputPath("mobile-create.png") });
  let requests = 0;
  await page.route("**/api/farm-records", async (route) => {
    if (route.request().method() === "POST") { requests++; await new Promise((resolve) => setTimeout(resolve, 180)); }
    await route.continue();
  });
  await dialog.getByRole("button", { name: "记入台账", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(dialog).toHaveCount(0);
  expect(requests).toBe(1);
  const saved = await records(page);
  expect(saved).toHaveLength(1);
  expect(saved[0]).toMatchObject({ season_id: historicalId, cost: 30, yield_kg: 100, unit_price: 2 });
  await expect(page.locator(".home-summary .stat-card strong").last()).toHaveText("1");
  await navigate(page, "地块档案");
  await page.locator(".plot-card").getByRole("button", { name: "记一笔农活", exact: true }).click();
  await expect(dialog.getByLabel("记录到地块")).toHaveValue(plotId);
  await expect(dialog.getByLabel("所属茬次")).toHaveValue(currentId);
  await expect(dialog.getByLabel("费用（元）")).toHaveValue("");
  await dialog.getByRole("group", { name: "快捷农活" }).getByRole("button", { name: "采收", exact: true }).click();
  await expect(dialog.getByLabel("产量（公斤）")).toHaveValue("");
  await expect(dialog.getByLabel("单价（元/公斤）")).toHaveValue("");
  await dialog.getByRole("button", { name: "取消记账" }).click();
  await page.getByRole("dialog", { name: "放弃未保存的农活？" }).getByRole("button", { name: "放弃并离开" }).click();
  await navigate(page, "统计面板");
  await page.getByLabel("统计地块").selectOption(plotId);
  await page.getByLabel("统计茬次").selectOption(historicalId);
  const card = page.locator(".economics-season-card");
  await expect(card).toHaveCount(1);
  await expect(card).toContainText("¥30");
  await expect(card).toContainText("¥200");
  await expect(card).toContainText("¥170");
  await expect(card).toContainText("亩均指标");
  await expect(page.locator(".economics-table-wrap")).toBeHidden();
  await noOverflow(page);
  await page.screenshot({ path: test.info().outputPath("mobile-economics.png"), fullPage: true });
});

test("390px 编辑失败保留输入，重试及切换类型不残留收入，可用键盘保存", async ({ page }) => {
  const { plotId, currentId } = await setup(page);
  const { record } = await write(page, "/farm-records", { plot_id: plotId, season_id: currentId, kind: "采收", happened_on: "2026-10-15", cost: 30, yield_kg: 50, unit_price: 4 });
  await navigate(page, "农事台账");
  await page.getByRole("button", { name: "编辑 采收 记录" }).click();
  await page.getByLabel("费用（元）").fill("80");
  await page.route(`**/api/farm-records/${record.id}`, (route) => route.fulfill({ status: 503, json: { success: false, error: "暂时无法保存，请重试" } }));
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.locator(".toast-banner")).toContainText("暂时无法保存");
  await expect(page.getByLabel("费用（元）")).toHaveValue("80");
  await expect(page.getByLabel("产量（公斤）")).toHaveValue("50");
  const kinds = page.getByRole("group", { name: "快捷农活" });
  await kinds.getByRole("button", { name: "施肥", exact: true }).click();
  await expect(page.getByLabel("产量（公斤）")).toHaveCount(0);
  await kinds.getByRole("button", { name: "采收", exact: true }).click();
  await expect(page.getByLabel("产量（公斤）")).toHaveValue("");
  await expect(page.getByLabel("单价（元/公斤）")).toHaveValue("");
  await kinds.getByRole("button", { name: "施肥", exact: true }).click();
  await page.getByLabel("肥料名称").fill("复合肥");
  await noOverflow(page);
  await page.screenshot({ path: test.info().outputPath("mobile-edit-retry.png"), fullPage: true });
  await page.unroute(`**/api/farm-records/${record.id}`);
  await page.getByLabel("费用（元）").press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "修改已保存" })).toBeVisible();
  expect((await records(page))[0]).toMatchObject({ id: record.id, kind: "施肥", cost: 80, yield_kg: null, unit_price: null });
  await navigate(page, "统计面板");
  await page.getByLabel("统计茬次").selectOption(currentId);
  await expect(page.locator(".economics-season-card")).toContainText("¥80");
  await expect(page.locator(".economics-season-card")).not.toContainText("¥200");
  await noOverflow(page);
});

test("390px 新增响应丢失后不自动重试，明确重试沿用提交标识", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: "记一笔农活", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "记一笔农活", exact: true });
  await dialog.getByLabel("记录到地块").selectOption({ label: "手机试验田" });
  await dialog.getByLabel("费用（元）").fill("12.5");
  await dialog.getByText("补充用量、作物与说明（选填）", { exact: true }).click();
  await dialog.getByLabel("作业说明").fill("仅在页面内暂存的农活");
  const submissions: string[] = [];
  await page.route("**/api/farm-records", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submissions.push(route.request().postDataJSON().submission_id);
    if (submissions.length === 1) {
      expect((await route.fetch()).ok()).toBeTruthy();
      return route.abort("failed");
    }
    await route.continue();
  });
  await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(dialog.getByLabel("费用（元）")).toHaveValue("12.5");
  await expect(dialog.getByLabel("作业说明")).toHaveValue("仅在页面内暂存的农活");
  await page.context().setOffline(true);
  await page.context().setOffline(false);
  expect(submissions).toHaveLength(1);
  expect(await records(page)).toHaveLength(1);
  await dialog.getByRole("button", { name: "记入台账", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(dialog).toHaveCount(0);
  expect(submissions).toHaveLength(2);
  expect(submissions[1]).toBe(submissions[0]);
  expect(await records(page)).toHaveLength(1);
});

test("390px 未保存表单保护取消、导航、刷新和退出，换账号无草稿泄漏", async ({ page }) => {
  const { plotId } = await setup(page);
  await navigate(page, "农事台账");
  await page.getByLabel("作业说明").fill("甲账号的未保存田间细节");
  await page.getByLabel("费用（元）").fill("999");
  await navigate(page, "统计面板");
  const confirm = page.getByRole("dialog", { name: "放弃未保存的农活？" });
  await expect(confirm).toBeVisible();
  await confirm.press("Escape");
  await expect(page.getByLabel("费用（元）")).toHaveValue("999");
  let unloadSeen = false;
  page.once("dialog", async (dialog) => { unloadSeen = dialog.type() === "beforeunload"; await dialog.dismiss(); });
  // A dismissed beforeunload cancels navigation; bound the navigation wait itself.
  await page.reload({ timeout: 1500 }).catch(() => {});
  expect(unloadSeen).toBe(true);
  await expect(page.getByLabel("作业说明")).toHaveValue("甲账号的未保存田间细节");
  const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(storage).not.toContain("甲账号");
  expect(storage).not.toContain(plotId);
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "放弃并离开" }).click();
  await expect(page.getByRole("button", { name: "访客登录" })).toBeVisible();
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["0", "0", "0", "0"]);
  await write(page, "/plots", { name: "乙账号的地", area_mu: 1, crop: "小麦", planted_on: "2026-01-01", soil_type: "壤土", irrigation: "井灌" });
  await page.reload();
  await page.getByRole("button", { name: "为乙账号的地记农活" }).click();
  const dialog = page.getByRole("dialog", { name: "记一笔农活", exact: true });
  await dialog.getByText("补充用量、作物与说明（选填）", { exact: true }).click();
  await expect(dialog.getByLabel("费用（元）")).toHaveValue("");
  await expect(dialog.getByLabel("作业说明")).toHaveValue("");
  await expect(dialog.getByLabel("记录到地块")).not.toContainText("手机试验田");
  await noOverflow(page);
});

test("390px 保存中禁止改动与离开，完成后可取消空表单且不误报未保存", async ({ page }) => {
  const { plotId } = await setup(page);
  await navigate(page, "农事台账");
  await page.getByLabel("费用（元）").fill("0");
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/farm-records", async (route) => {
    if (route.request().method() === "POST") await gate;
    await route.continue();
  });
  await page.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(page.getByRole("button", { name: "保存中…", exact: true })).toBeDisabled();
  await expect(page.getByLabel("费用（元）")).toBeDisabled();
  await navigate(page, "首页");
  await expect(page.getByRole("heading", { name: "农事台账", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  release();
  await expect(page.getByRole("status").filter({ hasText: "已记入台账，可随时" })).toBeVisible();
  await expect(page.getByLabel("费用（元）")).toHaveValue("");
  expect((await records(page))[0]).toMatchObject({ plot_id: plotId, cost: 0 });
  await navigate(page, "首页");
  await expect(page.getByRole("heading", { name: "首页", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("390px 取消或 Esc 离开草稿先确认，继续填写和键盘焦点均保留", async ({ page }) => {
  await setup(page);
  const opener = page.getByRole("button", { name: "为手机试验田记农活" });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "记一笔农活", exact: true });
  await dialog.getByLabel("费用（元）").fill("18");
  await dialog.getByText("补充用量、作物与说明（选填）", { exact: true }).click();
  await dialog.getByLabel("作业说明").fill("尚未确认保存");
  await dialog.getByRole("button", { name: "取消记账" }).click();
  const confirm = page.getByRole("dialog", { name: "放弃未保存的农活？" });
  await expect(confirm).toBeVisible();
  await confirm.press("Tab");
  await expect(confirm.getByRole("button", { name: "取消", exact: true })).toBeFocused();
  await confirm.press("Shift+Tab");
  await expect(confirm.getByRole("button", { name: "放弃并离开" })).toBeFocused();
  await confirm.getByRole("button", { name: "取消", exact: true }).click();
  await expect(dialog.getByLabel("费用（元）")).toHaveValue("18");
  await expect(dialog.getByLabel("作业说明")).toHaveValue("尚未确认保存");
  await dialog.press("Escape");
  await confirm.getByRole("button", { name: "放弃并离开" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  expect(await records(page)).toHaveLength(0);
  await opener.click();
  await dialog.getByText("补充用量、作物与说明（选填）", { exact: true }).click();
  await expect(dialog.getByLabel("费用（元）")).toHaveValue("");
  await expect(dialog.getByLabel("作业说明")).toHaveValue("");
  await dialog.getByRole("button", { name: "取消记账" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("390px 换账号后迟到的旧账号地块刷新不能污染新表单", async ({ page }) => {
  await setup(page);
  let release!: () => void;
  let captured!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const ready = new Promise<void>((resolve) => { captured = resolve; });
  let holdNext = true;
  await page.route("**/api/plots", async (route) => {
    if (route.request().method() !== "GET" || !holdNext) return route.continue();
    holdNext = false;
    const response = await route.fetch();
    captured();
    await gate;
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "为手机试验田记农活" }).click();
  const dialog = page.getByRole("dialog", { name: "记一笔农活", exact: true });
  await dialog.getByLabel("费用（元）").fill("9");
  await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await ready;
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name: "退出登录" }).click();
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["0", "0", "0", "0"]);
  const delivered = page.waitForResponse((response) => response.request().method() === "GET" && response.url().endsWith("/api/plots"));
  release();
  await (await delivered).finished();
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["0", "0", "0", "0"]);
  await page.getByRole("button", { name: "记一笔农活", exact: true }).click();
  await expect(page.getByRole("heading", { name: "地块档案", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
