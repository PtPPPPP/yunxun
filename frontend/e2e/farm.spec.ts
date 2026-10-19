import { expect, test, type Page } from "playwright/test";

async function guestLogin(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("main")).toBeVisible();
}

async function openPlots(page: Page) {
  await guestLogin(page);
  await page.getByRole("button", { name: "地块档案" }).click();
  await expect(page.getByRole("heading", { name: "地块档案" })).toBeVisible();
}

async function openLedger(page: Page) {
  await page.getByRole("button", { name: "农事台账" }).click();
  await expect(page.getByRole("heading", { name: "农事台账" })).toBeVisible();
}

async function createPlot(page: Page, name: string, area: string) {
  await page.getByPlaceholder("例如：东坡三亩地").fill(name);
  await page.getByLabel("面积（亩）").fill(area);
  await page.getByLabel("播种或定植日期").fill("2026-04-01");
  await page.getByRole("button", { name: "新建地块" }).click();
  await expect(page.locator(".plot-card").filter({ hasText: name })).toBeVisible();
  await expect(page.getByPlaceholder("例如：东坡三亩地")).toHaveValue("");
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

  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("施肥");
  await page.getByPlaceholder("可留空", { exact: true }).fill("300");
  await page.getByRole("button", { name: "记入台账" }).click();
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(1);

  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("采收");
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
  // 差额只代表已录台账，不含未记录的人工、地租等成本。
  await expect(cards.filter({ hasText: "已记录收支差额" })).toContainText("¥4740");

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

  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("打药");
  await page.getByLabel("农药名称").fill("吡虫啉");
  await expect(page.getByLabel("安全间隔期（天）")).toHaveValue("");
  await page.getByLabel("安全间隔期（天）").fill("7");

  await page.getByRole("button", { name: "记入台账" }).click();
  const row = page.locator(".stats-records .stats-record");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("吡虫啉");
  await expect(row).toContainText("最早采收");

  // 施药当天记采收应落在安全期内，给出提醒但不阻断提交
  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("采收");
  await expect(page.locator(".form-warning")).toContainText("安全间隔期 7 天");
  await expect(page.locator(".form-warning")).toContainText("请以产品标签为准");

  await page.getByRole("button", { name: "地块档案" }).click();
  await page.getByRole("dialog", { name: "放弃未保存的农活？" }).getByRole("button", { name: "放弃并离开" }).click();
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

test("结束一茬并开始新茬后，今日农活带出新作物", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "西洼两亩地", "2");
  // 建地块时填的作物就是第一茬
  await expect(page.locator(".plot-card")).toContainText("当前：玉米");

  await page.locator(".plot-card").getByRole("button", { name: "结束本茬" }).click();
  await expect(page.getByRole("heading", { name: "结束本茬" })).toBeVisible();
  await page.getByRole("button", { name: "确认结束本茬" }).click();
  await expect(page.locator(".plot-card")).toContainText("无进行中的茬次");

  await page.locator(".plot-card").getByRole("button", { name: "开始新茬" }).click();
  await expect(page.getByRole("heading", { name: "开始新茬" })).toBeVisible();
  await page.getByLabel("作物").selectOption("大豆");
  await page.getByRole("button", { name: "确认开始新茬" }).click();
  await expect(page.locator(".plot-card")).toContainText("当前：大豆");
  await expect(page.locator(".plot-card")).toContainText("共 2 茬");

  await page.getByRole("button", { name: "今日农活" }).click();
  await page.getByLabel("按地块带入").selectOption({ label: "西洼两亩地" });
  await expect(page.getByLabel("作物")).toHaveValue("大豆");
});

test("同一地块有进行中的茬次时不能再开新茬", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "东坡三亩地", "3");
  // 有进行中的茬次时卡片上只给「结束本茬」，不给「开始新茬」
  await expect(page.locator(".plot-card").getByRole("button", { name: "开始新茬" })).toHaveCount(0);
  await expect(page.locator(".plot-card").getByRole("button", { name: "结束本茬" })).toBeVisible();
});

test("补录上一季采收按作业日期归茬并使用历史作物", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "历史补录田", "3");
  await page.locator(".plot-card").getByRole("button", { name: "结束本茬" }).click();
  await page.getByLabel("结束或收获日期").fill("2026-05-31");
  await page.getByRole("button", { name: "确认结束本茬" }).click();
  await page.locator(".plot-card").getByRole("button", { name: "开始新茬" }).click();
  await page.getByLabel("作物").selectOption("大豆");
  await page.getByLabel("播种或定植日期").fill("2026-10-01");
  await page.getByRole("button", { name: "确认开始新茬" }).click();
  await expect(page.locator(".plot-card")).toContainText("当前：大豆");

  await openLedger(page);
  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("采收");
  await page.getByLabel("作业日期", { exact: true }).fill("2026-04-30");
  await expect(page.getByLabel("作物")).toHaveValue("");
  await page.getByLabel("产量（公斤）").fill("100");
  await page.getByLabel("单价（元/公斤）").fill("2");
  await page.getByRole("button", { name: "记入台账" }).click();
  const record = page.locator(".stats-records .stats-record");
  await expect(record).toHaveCount(1);
  await expect(record).toContainText("玉米");
  await expect(record).not.toContainText("未归茬");
  await page.getByRole("button", { name: "统计面板" }).click();
  const rows = page.locator(".economics-table tbody tr");
  await expect(rows.filter({ hasText: "玉米" })).toContainText("¥200");
  await expect(rows.filter({ hasText: "大豆" })).not.toContainText("¥200");
});

test("日期不明时保留未归茬并允许显式选择茬次", async ({ page }) => {
  await openPlots(page);
  await page.getByPlaceholder("例如：东坡三亩地").fill("日期不明田");
  await page.getByRole("button", { name: "新建地块" }).click();
  await expect(page.locator(".plot-card")).toBeVisible();
  await openLedger(page);
  await page.getByRole("button", { name: "记入台账" }).click();
  await expect(page.locator(".toast-banner")).toContainText("无法按日期唯一确定茬次");
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(0);
  await page.getByLabel("所属茬次").selectOption("unassigned");
  await page.getByRole("button", { name: "记入台账" }).click();
  await expect(page.locator(".stats-records .stats-record")).toContainText("未归茬");
  await page.getByLabel("所属茬次").selectOption({ label: "玉米（开始日未填 至 进行中）" });
  await page.getByRole("button", { name: "记入台账" }).click();
  const records = page.locator(".stats-records .stats-record");
  await expect(records).toHaveCount(2);
  await expect(records.filter({ hasText: "未归茬" })).toHaveCount(1);
  await expect(records.filter({ hasText: "玉米" })).toHaveCount(1);
});

test("可以取消编辑或纠正费用并刷新统计", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "费用核对田", "3");
  await openLedger(page);
  await addRecord(page, "10 公斤", "30");
  await page.getByRole("button", { name: "统计面板" }).click();
  await expect(page.locator(".economics-table tbody tr")).toContainText("¥30");

  await openLedger(page);
  await page.getByRole("button", { name: "编辑 施肥 记录" }).click();
  await expect(page.getByRole("heading", { name: "编辑农事记录" })).toBeVisible();
  await expect(page.getByLabel("费用（元）")).toHaveValue("30");
  await page.getByLabel("费用（元）").fill("999");
  await page.getByRole("button", { name: "取消编辑" }).click();
  await page.getByRole("dialog", { name: "放弃未保存的农活？" }).getByRole("button", { name: "放弃并离开" }).click();
  await expect(page.locator(".stats-records .stats-record")).toContainText("¥30");
  await page.getByRole("button", { name: "编辑 施肥 记录" }).click();
  await page.getByLabel("费用（元）").fill("80");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.getByRole("heading", { name: "记一次农事" })).toBeVisible();
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(1);
  await expect(page.locator(".stats-records .stats-record")).toContainText("¥80");
  await page.getByRole("button", { name: "统计面板" }).click();
  await expect(page.locator(".economics-table tbody tr")).toContainText("¥80");
  await expect(page.locator(".economics-table tbody tr")).not.toContainText("¥30");
});

test("编辑切换采收为施肥会清理隐藏收入字段", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "类型纠正田", "3");
  await openLedger(page);
  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("采收");
  await page.getByLabel("产量（公斤）").fill("100");
  await page.getByLabel("单价（元/公斤）").fill("2");
  await page.getByLabel("费用（元）").fill("30");
  await page.getByRole("button", { name: "记入台账" }).click();
  await expect(page.locator(".stats-records .stats-record")).toContainText("收入 ¥200");
  await page.getByRole("button", { name: "编辑 采收 记录" }).click();
  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("施肥");
  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("采收");
  await expect(page.getByLabel("产量（公斤）")).toHaveValue("");
  await expect(page.getByLabel("单价（元/公斤）")).toHaveValue("");
  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("施肥");
  await page.getByLabel("肥料名称").fill("尿素");
  await page.getByRole("button", { name: "保存修改" }).click();
  const row = page.locator(".stats-records .stats-record");
  await expect(row).toContainText("施肥");
  await expect(row).toContainText("尿素");
  await expect(row).not.toContainText("收入");
  await expect(row).not.toContainText("产量");
  await page.getByRole("button", { name: "统计面板" }).click();
  await expect(page.locator(".economics-table tbody tr")).not.toContainText("¥200");
  await expect(page.locator(".economics-table tbody tr")).toContainText("¥-30");
});

test("编辑时可以改地块日期和茬次并刷新两块地计数", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "原田", "3");
  await page.getByRole("combobox", { name: "第一茬作物", exact: true }).selectOption("大豆");
  await createPlot(page, "目标田", "2");
  await openLedger(page);
  await page.getByLabel("记录到地块").selectOption({ label: "原田" });
  await addRecord(page, "10 公斤", "30");
  await page.getByRole("button", { name: "编辑 施肥 记录" }).click();
  await page.getByLabel("记录到地块").selectOption({ label: "目标田" });
  await page.getByLabel("所属茬次").selectOption({ label: "大豆（2026-04-01 至 进行中）" });
  await page.getByLabel("作业日期", { exact: true }).fill("2026-04-30");
  await page.getByRole("button", { name: "保存修改" }).click();
  const row = page.locator(".stats-records .stats-record");
  await expect(row).toContainText("目标田");
  await expect(row).toContainText("大豆");
  await expect(row).toContainText("2026/4/30");
  await page.getByRole("button", { name: "地块档案" }).click();
  await expect(page.locator(".plot-card").filter({ hasText: "原田" })).toContainText("本季 0 次作业");
  await expect(page.locator(".plot-card").filter({ hasText: "目标田" })).toContainText("本季 1 次作业");
});

async function seedRecords(page: Page, count: number) {
  // 仍走真实 API 和临时测试数据库，准备超过一页的记录。
  const response = await page.request.get("http://127.0.0.1:8011/api/plots");
  const plots = (await response.json()).plots as Array<{ id: string; name: string }>;
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const create = async (plotId: string, kind: string, day: string, detail: string) => {
    const result = await page.request.post("http://127.0.0.1:8011/api/farm-records", {
      headers: { "X-CSRF-Token": csrf },
      data: { plot_id: plotId, kind, happened_on: day, detail, cost: 30 },
    });
    expect(result.ok()).toBeTruthy();
  };
  const first = plots.find((plot) => plot.name === "原田")!;
  const second = plots.find((plot) => plot.name === "目标田")!;
  for (let i = 0; i < count; i += 1) await create(first.id, "施肥", "2026-04-15", `页内记录 ${i}`);
  await create(first.id, "打药", "2026-04-15", "不同类型");
  await create(first.id, "施肥", "2026-04-01", "早于范围");
  await create(second.id, "施肥", "2026-04-15", "其他地块");
  return { first, second };
}

test("组合筛选跨页加载且编辑移出日期范围后重置列表", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "原田", "3");
  await createPlot(page, "目标田", "2");
  await seedRecords(page, 25);
  await openLedger(page);
  await page.getByLabel("按地块筛选").selectOption({ label: "原田" });
  await page.getByLabel("按作业类型筛选").selectOption("施肥");
  await page.getByLabel("筛选开始日期").fill("2026-04-10");
  await page.getByLabel("筛选结束日期").fill("2026-04-20");
  const rows = page.locator(".stats-records .stats-record");
  await expect(rows).toHaveCount(20);
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(rows).toHaveCount(25);
  await expect(rows.filter({ hasText: "其他地块" })).toHaveCount(0);
  await expect(rows.filter({ hasText: "不同类型" })).toHaveCount(0);
  await expect(rows.filter({ hasText: "早于范围" })).toHaveCount(0);
  await rows.first().getByRole("button", { name: "编辑 施肥 记录" }).click();
  await page.getByLabel("作业日期", { exact: true }).fill("2026-04-25");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(rows).toHaveCount(20);
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(rows).toHaveCount(24);
  await page.getByLabel("筛选结束日期").fill("2026-04-14");
  await expect(rows).toHaveCount(0);
  await expect(page.getByRole("button", { name: "加载更多" })).toHaveCount(0);
});

test("切换地块筛选后忽略旧的加载更多响应", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "原田", "3");
  await createPlot(page, "目标田", "2");
  const { first } = await seedRecords(page, 21);
  await openLedger(page);
  await page.getByLabel("按地块筛选").selectOption({ label: "原田" });
  const rows = page.locator(".stats-records .stats-record");
  await expect(rows).toHaveCount(20);
  let release!: () => void;
  let intercepted!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  const ready = new Promise<void>((resolve) => { intercepted = resolve; });
  await page.route("**/api/farm-records?**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.has("cursor") && url.searchParams.get("plot_id") === first.id) {
      const response = await route.fetch();
      intercepted();
      await held;
      await route.fulfill({ response });
    } else {
      await route.continue();
    }
  });
  try {
    await page.getByRole("button", { name: "加载更多" }).click();
    await ready;
    await page.getByLabel("按地块筛选").selectOption({ label: "目标田" });
    await expect(rows).toHaveCount(1);
    await expect(rows).toContainText("其他地块");
    const lateResponse = page.waitForResponse((response) => new URL(response.url()).searchParams.has("cursor"));
    release();
    await lateResponse;
    await page.waitForLoadState("networkidle");
    await expect(rows).toHaveCount(1);
    await expect(rows).toContainText("其他地块");
  } finally {
    release();
  }
});

test("投入产出按茬次分开算，不混季", async ({ page }) => {
  await openPlots(page);
  await createPlot(page, "东坡三亩地", "3");
  await openLedger(page);

  // 第一茬：施一次肥
  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("施肥");
  await page.getByPlaceholder("可留空", { exact: true }).fill("300");
  await page.getByRole("button", { name: "记入台账" }).click();
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(1);

  // 换茬：结束玉米，开始大豆，再施一次肥
  await page.getByRole("button", { name: "地块档案" }).click();
  await page.locator(".plot-card").getByRole("button", { name: "结束本茬" }).click();
  await page.getByRole("button", { name: "确认结束本茬" }).click();
  await page.locator(".plot-card").getByRole("button", { name: "开始新茬" }).click();
  await page.getByLabel("作物").selectOption("大豆");
  await page.getByRole("button", { name: "确认开始新茬" }).click();
  await expect(page.locator(".plot-card")).toContainText("当前：大豆");

  await openLedger(page);
  await page.getByRole("combobox", { name: "作业类型", exact: true }).selectOption("施肥");
  // 两茬在同一天交接，日期有重叠时由用户明确选择。
  const seasonLabel = await page.getByLabel("所属茬次").getByRole("option", { name: /^大豆（/ }).innerText();
  await page.getByLabel("所属茬次").selectOption({ label: seasonLabel });
  await page.getByPlaceholder("可留空", { exact: true }).fill("150");
  await page.getByRole("button", { name: "记入台账" }).click();
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(2);

  await page.getByRole("button", { name: "统计面板" }).click();
  const rows = page.locator(".economics-table tbody tr");
  await expect(rows).toHaveCount(2);
  // 玉米那一茬只算 300，大豆那一茬只算 150
  await expect(rows.filter({ hasText: "玉米" })).toContainText("¥300");
  await expect(rows.filter({ hasText: "大豆" })).toContainText("¥150");
  await expect(rows.filter({ hasText: "玉米" })).not.toContainText("¥150");
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
