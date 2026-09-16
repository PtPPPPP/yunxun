import { expect, test, type Page } from "playwright/test";

async function guestLogin(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("main")).toBeVisible();
}

async function openPlots(page: Page) {
  await guestLogin(page);
  await page.getByRole("button", { name: "地块档案" }).click();
  await expect(page.getByRole("heading", { name: "农事地块" })).toBeVisible();
}

async function openLedger(page: Page) {
  await page.getByRole("button", { name: "农事台账" }).click();
  await expect(page.getByRole("heading", { name: "农事台账" })).toBeVisible();
}

async function createPlot(page: Page, name: string, area: string) {
  await page.getByPlaceholder("例如：东坡三亩地").fill(name);
  await page.getByLabel("面积（亩）").fill(area);
  await page.getByRole("button", { name: "新建地块" }).click();
  await expect(page.locator(".plot-card").filter({ hasText: name })).toBeVisible();
}

async function addRecord(page: Page, quantity: string, cost: string) {
  await page.getByPlaceholder("例如：15 公斤/亩").fill(quantity);
  await page.getByPlaceholder("可留空", { exact: true }).fill(cost);
  await page.getByRole("button", { name: "记入台账" }).click();
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(1);
}

test("采收记录填产量与单价后，统计面板算出投入产出", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "东坡三亩地", "3");
  await openLedger(page);

  await page.getByLabel("作业类型").selectOption("施肥");
  await page.getByPlaceholder("可留空", { exact: true }).fill("300");
  await page.getByRole("button", { name: "记入台账" }).click();
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(1);

  await page.getByLabel("作业类型").selectOption("采收");
  await page.getByPlaceholder("例如：2100").fill("2100");
  await page.getByPlaceholder("例如：2.4").fill("2.4");
  await page.getByRole("button", { name: "记入台账" }).click();

  // 同一天的两条记录按 id 排序，顺序稳定但不是插入序，所以按内容过滤而不是取第一条。
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(2);
  const harvestRow = page.locator(".stats-record").filter({ hasText: "采收" });
  await expect(harvestRow).toContainText("产量 2100 公斤");
  await expect(harvestRow).toContainText("收入 ¥5040");

  await page.getByRole("button", { name: "统计面板" }).click();
  const cards = page.locator(".stat-card");
  await expect(cards.filter({ hasText: "累计投入" })).toContainText("¥300");
  await expect(cards.filter({ hasText: "累计收入" })).toContainText("¥5040");
  await expect(cards.filter({ hasText: "净收益" })).toContainText("¥4740");

  const row = page.locator(".economics-table tbody tr");
  await expect(row).toContainText("东坡三亩地");
  await expect(row).toContainText("3 亩");
  await expect(row).toContainText("¥300");
  await expect(row).toContainText("2100 公斤");
  await expect(row).toContainText("¥5040");
  await expect(row).toContainText("¥4740");
  await expect(row).toContainText("¥100");
  await expect(row).toContainText("700 公斤");
  await expect(row).toContainText("¥1580");
});

test("打药记录安全间隔期，采收时给出安全期提醒", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "东坡三亩地", "3");
  await openLedger(page);

  await page.getByLabel("作业类型").selectOption("打药");
  await page.getByLabel("常见农药参考").selectOption("吡虫啉");
  await expect(page.getByLabel("安全间隔期（天）")).toHaveValue("7");

  await page.getByRole("button", { name: "记入台账" }).click();
  const row = page.locator(".stats-records .stats-record");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("吡虫啉");
  await expect(row).toContainText("最早采收");

  // 施药当天记采收应落在安全期内，给出提醒但不阻断提交
  await page.getByLabel("作业类型").selectOption("采收");
  await expect(page.locator(".form-warning")).toContainText("安全间隔期 7 天");
  await expect(page.locator(".form-warning")).toContainText("请以产品标签为准");

  await page.getByRole("button", { name: "地块档案" }).click();
  await expect(page.locator(".plot-card__safety")).toContainText("安全期内");
});

test("农事台账在还没有地块时给出引导", async ({ page }) => {
  await guestLogin(page);
  await openLedger(page);
  await expect(page.getByRole("heading", { name: "还没有地块" })).toBeVisible();
});

test("可以在地块下记一条农事并在台账中回看", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "东坡三亩地", "3.5");
  await openLedger(page);

  await page.getByPlaceholder("例如：雨后追尿素，重点看低洼处").fill("雨后追尿素");
  await addRecord(page, "15 公斤/亩", "120.5");

  const row = page.locator(".stats-records .stats-record");
  await expect(row).toContainText("施肥");
  await expect(row).toContainText("东坡三亩地");
  await expect(row).toContainText("玉米");
  await expect(row).toContainText("15 公斤/亩");
  await expect(row).toContainText("¥120.5");
  await expect(row).toContainText("雨后追尿素");
});

test("记录会同步到地块卡片的作业次数与统计面板", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "西洼两亩地", "2");
  await openLedger(page);
  await addRecord(page, "20 毫升/亩", "");

  await page.getByRole("button", { name: "地块档案" }).click();
  await expect(page.locator(".plot-card")).toContainText("本季 1 次作业");

  await page.getByRole("button", { name: "统计面板" }).click();
  const cards = page.locator(".stat-card");
  await expect(cards.filter({ hasText: "地块数" })).toContainText("1");
  await expect(cards.filter({ hasText: "作业记录" })).toContainText("1");
});

test("可以按地块筛选台账记录", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "东坡三亩地", "3.5");
  await createPlot(page, "西洼两亩地", "2");
  await openLedger(page);

  // 表单的记录目标和列表筛选是两个独立控件，这里显式指定要记到哪块地。
  await page.getByLabel("记录到地块").selectOption({ label: "东坡三亩地" });
  await page.getByLabel("按地块筛选").selectOption({ label: "东坡三亩地" });
  await addRecord(page, "15 公斤/亩", "");
  await expect(page.locator(".stats-record")).toContainText("东坡三亩地");

  await page.getByLabel("按地块筛选").selectOption({ label: "西洼两亩地" });
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(0);
  await expect(page.locator(".stats-empty")).toContainText("暂无台账记录");
});

test("删除台账记录需要二次确认", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "北坡一亩地", "1");
  await openLedger(page);
  await addRecord(page, "10 公斤/亩", "");

  await page.getByRole("button", { name: "删除 施肥 记录" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("删除这条农事记录？");
  await expect(dialog).toContainText("北坡一亩地");

  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(0);
  await expect(page.locator(".stats-empty")).toContainText("暂无台账记录");
});

test("删除有记录的地块会提示连带删除的条数", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "东坡三亩地", "3.5");
  await openLedger(page);
  await addRecord(page, "15 公斤/亩", "");

  await page.getByRole("button", { name: "地块档案" }).click();
  await expect(page.locator(".plot-card")).toContainText("本季 1 次作业");
  await page.getByRole("button", { name: "删除" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("东坡三亩地");
  await expect(dialog).toContainText("1 条农事台账记录");
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(page.locator(".plot-card")).toHaveCount(0);

  await openLedger(page);
  await expect(page.getByRole("heading", { name: "还没有地块" })).toBeVisible();
});

test("今日农活可以选地块带出作物", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "西洼两亩地", "2");

  await page.getByRole("button", { name: "编辑" }).click();
  await page.getByLabel("当前作物").selectOption("大豆");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.locator(".plot-card")).toContainText("大豆");

  await page.getByRole("button", { name: "今日农活" }).click();
  await page.getByLabel("按地块带入").selectOption({ label: "西洼两亩地" });
  await expect(page.getByLabel("作物")).toHaveValue("大豆");
});

test("地块档案初始为空状态", async ({ page }) => {
  await openPlots(page);
  await expect(page.locator(".stats-empty")).toContainText("还没有地块");
});

test("可以新建地块并显示在档案列表", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "东坡三亩地", "3.5");

  const card = page.locator(".plot-card");
  await expect(card).toHaveCount(1);
  await expect(card).toContainText("东坡三亩地");
  await expect(card).toContainText("3.5 亩");
  await expect(card).toContainText("玉米");
  await expect(card).toContainText("本季 0 次作业");
  await expect(page.locator(".stats-empty")).toHaveCount(0);
});

test("可以编辑地块面积", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "西洼两亩地", "2");

  await page.getByRole("button", { name: "编辑" }).click();
  await expect(page.getByRole("heading", { name: "编辑地块" })).toBeVisible();
  await page.getByLabel("面积（亩）").fill("2.8");
  await page.getByRole("button", { name: "保存修改" }).click();

  await expect(page.locator(".plot-card")).toContainText("2.8 亩");
  await expect(page.getByRole("heading", { name: "新建地块" })).toBeVisible();
});

test("删除空地块需要二次确认", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "北坡一亩地", "1");

  await page.getByRole("button", { name: "删除" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("删除这个地块？");
  await expect(dialog).toContainText("北坡一亩地");
  await expect(dialog).toContainText("0 条农事台账记录");

  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(page.locator(".plot-card")).toHaveCount(0);
  await expect(page.locator(".stats-empty")).toContainText("还没有地块");
});
