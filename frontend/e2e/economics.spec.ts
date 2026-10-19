import { expect, test, type Page } from "playwright/test";

const apiURL = "http://127.0.0.1:8011/api";

async function post(page: Page, path: string, data: Record<string, unknown>, method = "POST") {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const response = await page.request.fetch(`${apiURL}${path}`, { method, data, headers: { "X-CSRF-Token": csrf } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function prepare(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("main")).toBeVisible();
  const { plot } = await post(page, "/plots", { name: "跨年田", area_mu: 2, soil_type: "壤土", irrigation: "井灌", crop: "玉米", planted_on: "2025-10-01" });
  const firstId = plot.active_season.id as string;
  await post(page, `/seasons/${firstId}`, { crop: "玉米", started_on: "2025-10-01", ended_on: "2026-05-31" }, "PATCH");
  const { season: second } = await post(page, "/seasons", { plot_id: plot.id, crop: "大豆", started_on: "2026-10-01" });
  const { plot: other } = await post(page, "/plots", { name: "其他田", area_mu: 1, soil_type: "壤土", irrigation: "井灌", crop: "小麦", planted_on: "2025-01-01" });
  const record = (values: Record<string, unknown>) => post(page, "/farm-records", { plot_id: plot.id, season_id: firstId, kind: "施肥", ...values });
  await record({ happened_on: "2025-11-01", cost: 30, detail: "旧茬支出" });
  await record({ happened_on: "2025-12-31", kind: "采收", yield_kg: 100, detail: "旧茬待补" });
  await record({ happened_on: "2026-01-01", kind: "采收", yield_kg: 100, unit_price: 2, cost: 0, detail: "跨年收入" });
  await record({ happened_on: "2026-10-01", season_id: second.id, cost: 10, detail: "新茬支出" });
  await record({ happened_on: "2025-09-01", season_id: null, cost: 0, detail: "未归茬账" });
  await post(page, "/farm-records", { plot_id: other.id, kind: "施肥", happened_on: "2026-01-01", cost: 99, detail: "其他田账目" });
  // 外部 API 准备测试数据后重载，让地块与历史茬次列表反映同一份数据。
  await page.reload();
  await expect(page.getByRole("main")).toBeVisible();
  if (await page.getByRole("button", { name: "打开导航" }).isVisible()) {
    await page.getByRole("button", { name: "打开导航" }).click();
  }
  await page.getByRole("button", { name: "统计面板" }).click();
  await expect(page.locator(".economics-table tbody tr")).toHaveCount(4);
  return { plotId: plot.id as string, firstId };
}

async function selectHistory(page: Page, plotId: string, seasonId: string, year = "2025") {
  await page.getByLabel("统计地块").selectOption(plotId);
  await page.getByLabel("统计茬次").selectOption(seasonId);
  await page.getByLabel("作业年份").selectOption(year);
  await expect(page.locator(".economics-table tbody tr")).toHaveCount(1);
}

test("历史茬次按作业年份查看并准确提示缺失账目", async ({ page }) => {
  const { plotId, firstId } = await prepare(page);
  await selectHistory(page, plotId, firstId);
  const row = page.locator(".economics-table tbody tr");
  await expect(row).toContainText("2025/10/1 ~ 2026/5/31");
  await expect(row).toContainText("2 亩");
  await expect(row).toContainText("2 次");
  await expect(row).toContainText("费用未填 1 条");
  await expect(row).toContainText("采收待补录 1 条");
  await expect(row.locator("td").nth(7)).toHaveText("待补录");
  await expect(page.locator(".economics-panel .stat-card").filter({ hasText: "已记录收入" })).toContainText("待补录");
  await expect(page.locator(".economics-panel")).toContainText("未记录的人工、地租等成本不包含在内");
  await expect(page.getByText("净收益", { exact: true })).toHaveCount(0);
  await page.getByLabel("作业年份").selectOption("2026");
  await expect(row).toContainText("1 次");
  await expect(row).toContainText("费用未填 0 条");
  await expect(row.locator("td").nth(7)).toHaveText("¥200");
  await page.getByLabel("作业年份").selectOption("");
  await expect(row).toContainText("3 次");
  await expect(row.locator("td").nth(7)).toHaveText("¥200");
});

test("从金额和缺失数量追溯台账并补录后保留筛选", async ({ page }) => {
  const { plotId, firstId } = await prepare(page);
  await selectHistory(page, plotId, firstId);
  await page.getByRole("button", { name: "查看当前范围支出台账", exact: true }).click();
  const records = page.locator(".stats-records .stats-record");
  await expect(records).toHaveCount(1);
  await expect(records).toContainText("旧茬支出");
  await expect(page.getByLabel("按茬次筛选")).toHaveValue(firstId);
  await expect(page.getByLabel("筛选开始日期")).toHaveValue("2025-01-01");
  await page.getByRole("button", { name: "返回收支统计" }).click();
  await expect(page.getByLabel("统计地块")).toHaveValue(plotId);
  await expect(page.getByLabel("统计茬次")).toHaveValue(firstId);
  await expect(page.getByLabel("作业年份")).toHaveValue("2025");
  const row = page.locator(".economics-table tbody tr");
  await row.locator(".economics-quality").getByRole("button", { name: /^查看采收待补录台账/ }).click();
  await expect(records).toHaveCount(1);
  await expect(records).toContainText("旧茬待补");
  await expect(records).toContainText("费用未填");
  await expect(records).toContainText("采收待补录：单价");
  await page.getByRole("button", { name: "编辑 采收 记录" }).click();
  await page.getByLabel("单价（元/公斤）").fill("2");
  await page.getByLabel("费用（元）").fill("0");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(records).toHaveCount(0);
  await page.getByRole("button", { name: "返回收支统计" }).click();
  await expect(row.locator("td").nth(7)).toHaveText("¥200");
  await expect(row).toContainText("费用未填 0 条");
  await expect(row).toContainText("采收待补录 0 条");
  await expect(row.locator("td").nth(8)).toHaveText("¥170");
  await expect(page.getByLabel("作业年份")).toHaveValue("2025");
});

test("离开统计面板再返回仍保留历史茬次筛选", async ({ page }) => {
  const { plotId, firstId } = await prepare(page);
  await selectHistory(page, plotId, firstId);
  await page.getByRole("button", { name: "地块档案" }).click();
  await page.getByRole("button", { name: "统计面板" }).click();
  await expect(page.getByLabel("统计地块")).toHaveValue(plotId);
  await expect(page.getByLabel("统计茬次")).toHaveValue(firstId);
  await expect(page.getByLabel("作业年份")).toHaveValue("2025");
  await expect(page.locator(".economics-table tbody tr")).toHaveCount(1);
});

test("未归茬和零费用独立展示并能追溯", async ({ page }) => {
  await prepare(page);
  await page.getByLabel("统计茬次").selectOption("unassigned");
  const row = page.locator(".economics-table tbody tr");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("未归茬");
  await expect(row.locator("td").nth(5)).toHaveText("¥0");
  await expect(row).toContainText("费用未填 0 条");
  await row.getByRole("button", { name: /^查看已记录支出台账/ }).click();
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(1);
  await expect(page.locator(".stats-records .stats-record")).toContainText("未归茬账");
  await expect(page.locator(".stats-records .stats-record")).toContainText("¥0");
});

test("手机端使用完整茬次卡片且无页面横向溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { plotId, firstId } = await prepare(page);
  await selectHistory(page, plotId, firstId);
  await expect(page.locator(".economics-table-wrap")).toBeHidden();
  const card = page.locator(".economics-season-card");
  await expect(card).toHaveCount(1);
  await expect(card).toBeVisible();
  await expect(card).toContainText("跨年田 · 玉米");
  await expect(card).toContainText("2025/10/1 ~ 2026/5/31");
  await expect(card).toContainText("2 亩");
  await expect(card).toContainText("已记录收支差额");
  await expect(card).toContainText("亩均指标");
  const overflow = await page.evaluate(() => ({
    width: window.innerWidth, scrollWidth: document.documentElement.scrollWidth,
    elements: Array.from(document.querySelectorAll("body *")).filter((element) => {
      const rect = element.getBoundingClientRect();
      return rect.left >= 0 && rect.right > window.innerWidth + 1;
    }).slice(0, 15).map((element) => ({ tag: element.tagName, class: element.className, width: element.getBoundingClientRect().width })),
  }));
  expect(overflow.scrollWidth, JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.width);
  await card.getByRole("button", { name: /^查看费用未填台账/ }).click();
  await expect(page.locator(".stats-records .stats-record")).toContainText("旧茬待补");
  await page.getByRole("button", { name: "返回收支统计" }).click();
  await expect(page.getByLabel("统计茬次")).toHaveValue(firstId);
});

test("统计接口失败时不展示虚假的零金额", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/farm-records/economics**", (route) => route.fulfill({
    status: 500, contentType: "application/json", body: JSON.stringify({ success: false, error: "统计暂不可用" }),
  }));
  await page.getByLabel("作业年份").selectOption("2025");
  await expect(page.locator(".economics-panel").getByRole("alert")).toHaveText("统计暂不可用");
  await expect(page.locator(".economics-panel .stat-card")).toHaveCount(0);
});

test("快速切换年份后忽略旧的统计响应", async ({ page }) => {
  const { plotId, firstId } = await prepare(page);
  await selectHistory(page, plotId, firstId, "");
  let release!: () => void;
  let intercepted!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  const ready = new Promise<void>((resolve) => { intercepted = resolve; });
  await page.route("**/api/farm-records/economics?**", async (route) => {
    if (new URL(route.request().url()).searchParams.get("year") === "2025") {
      const response = await route.fetch();
      intercepted();
      await held;
      await route.fulfill({ response });
    } else await route.continue();
  });
  try {
    await page.getByLabel("作业年份").selectOption("2025");
    await ready;
    await page.getByLabel("作业年份").selectOption("2026");
    const row = page.locator(".economics-table tbody tr");
    await expect(row.locator("td").nth(7)).toHaveText("¥200");
    const late = page.waitForResponse((response) => new URL(response.url()).searchParams.get("year") === "2025");
    release();
    await late;
    await page.waitForLoadState("networkidle");
    await expect(row.locator("td").nth(7)).toHaveText("¥200");
    await expect(row).toContainText("费用未填 0 条");
    await expect(page.getByLabel("作业年份")).toHaveValue("2026");
  } finally { release(); }
});
