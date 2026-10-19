import { expect, test, type Download, type Page } from "playwright/test";

const apiURL = "http://127.0.0.1:8011/api";
const ledgerLabel = "导出当前筛选台账 CSV";

async function write(page: Page, path: string, data: Record<string, unknown>, method = "POST") {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const response = await page.request.fetch(`${apiURL}${path}`, { method, data, headers: { "X-CSRF-Token": csrf } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function prepare(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录", exact: true }).click();
  await expect(page.getByRole("main")).toBeVisible();
  const { plot } = await write(page, "/plots", { name: '中文田,"甲区"', crop: "玉米", area_mu: 2, soil_type: "壤土", irrigation: "井灌", planted_on: "2025-10-01" });
  const first = plot.active_season.id as string;
  await write(page, `/seasons/${first}`, { crop: "玉米", started_on: "2025-10-01", ended_on: "2026-05-31" }, "PATCH");
  const { season } = await write(page, "/seasons", { plot_id: plot.id, crop: "大豆", started_on: "2026-10-01" });
  // API 准备资料不会触发页面的地块刷新，重载后再开始用户操作。
  await page.reload();
  await expect(page.getByRole("main")).toBeVisible();
  return { plot, first, second: season.id as string };
}

async function navigate(page: Page, name: string) {
  if (await page.getByRole("button", { name: "打开导航" }).isVisible()) await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name, exact: true }).click();
}

async function readCsv(download: Download) {
  const stream = await download.createReadStream();
  expect(stream).toBeTruthy();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const bytes = Buffer.concat(chunks);
  expect([...bytes.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
  const text = bytes.toString("utf8").slice(1);
  // 测试端解析带引号的多行字段，不引入运行时 CSV 依赖。
  const records: string[][] = [];
  let row: string[] = [], field = "", quoted = false;
  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    if (char === '"') {
      if (quoted && text[index + 1] === '"') { field += '"'; index++; } else quoted = !quoted;
    } else if (char === "," && !quoted) { row.push(field); field = ""; }
    else if (char === "\r" && text[index + 1] === "\n" && !quoted) {
      row.push(field); records.push(row); row = []; field = ""; index++;
    } else field += char;
  }
  expect(quoted).toBe(false);
  const [headers, ...values] = records;
  return values.map((cells) => Object.fromEntries(headers.map((header, index) => [header, cells[index]])));
}

async function download(page: Page, label: string) {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: label, exact: true }).click();
  const file = await pending;
  expect(await file.failure()).toBeNull();
  return { file, rows: await readCsv(file) };
}

test("台账按当前筛选跨分页全部导出，下载中防重复，中文特殊字符与缺失值保持", async ({ page }) => {
  const { plot, first, second } = await prepare(page);
  for (let index = 0; index < 27; index++) await write(page, "/farm-records", {
    plot_id: plot.id, season_id: first, kind: "施肥", happened_on: "2025-12-31",
    material: '复合肥,"甲"', quantity: "2 袋", cost: index === 0 ? null : 0,
    detail: index === 0 ? '中文,"引号"\n第二行' : index === 1 ? "=1+1" : `第 ${index} 笔`,
  });
  await write(page, "/farm-records", { plot_id: plot.id, season_id: first, kind: "采收", happened_on: "2026-01-01", yield_kg: 100, unit_price: 2 });
  await write(page, "/farm-records", { plot_id: plot.id, season_id: second, kind: "施肥", happened_on: "2026-10-01", cost: 999 });
  await page.reload();
  await navigate(page, "农事台账");
  await page.getByLabel("按地块筛选").selectOption(plot.id);
  await page.getByLabel("按茬次筛选").selectOption(first);
  await page.getByLabel("按作业类型筛选").selectOption("施肥");
  await page.getByLabel("筛选开始日期").fill("2025-12-01");
  await page.getByLabel("筛选结束日期").fill("2025-12-31");
  await expect(page.locator(".stats-record")).toHaveCount(20);
  let calls = 0;
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/farm-records/export.csv?**", async (route) => { calls++; await gate; await route.continue(); });
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: ledgerLabel }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(page.getByRole("button", { name: "导出中…" })).toBeDisabled();
  release();
  const file = await pending;
  const rows = await readCsv(file);
  expect(calls).toBe(1);
  expect(rows).toHaveLength(27);
  expect(new Set(rows.map((row) => row["作业类型"]))).toEqual(new Set(["施肥"]));
  expect(rows.find((row) => row["说明"] === '中文,"引号"\n第二行')!["费用（元）"]).toBe("");
  expect(rows.find((row) => row["说明"] === "\t'=1+1")!["费用（元）"]).toBe("0.0");
  expect(file.suggestedFilename()).toContain("2025-12-01至2025-12-31");
  expect(file.suggestedFilename()).toContain("玉米");
  await expect(page.getByRole("status").filter({ hasText: "27 条台账" })).toBeVisible();
  await expect(page.locator(".stats-record")).toHaveCount(20);
  await expect(page.getByLabel("按茬次筛选")).toHaveValue(first);
});

test("历史单茬汇总与对应明细遵守作业年度，差额为可计算负数", async ({ page }) => {
  const { plot, first, second } = await prepare(page);
  await write(page, "/farm-records", { plot_id: plot.id, season_id: first, kind: "施肥", happened_on: "2025-12-31", cost: 30 });
  await write(page, "/farm-records", { plot_id: plot.id, season_id: first, kind: "采收", happened_on: "2026-01-01", yield_kg: 100, unit_price: 2, cost: 0 });
  await write(page, "/farm-records", { plot_id: plot.id, season_id: second, kind: "施肥", happened_on: "2026-10-01", cost: 999 });
  await page.reload();
  await navigate(page, "统计面板");
  await page.getByLabel("统计地块").selectOption(plot.id);
  await page.getByLabel("统计茬次").selectOption(first);
  await page.getByLabel("作业年份").selectOption("2025");
  await expect(page.locator(".economics-table tbody tr")).toHaveCount(1);
  const summary = await download(page, "导出收支汇总 CSV");
  expect(summary.rows).toHaveLength(1);
  expect(summary.rows[0]["已记录收支差额（元）"]).toBe("-30.0");
  expect(summary.rows[0]["茬次开始日期"]).toBe("2025-10-01");
  expect(summary.rows[0]["作业年份"]).toBe("2025");
  expect(summary.file.suggestedFilename()).toContain("作业2025年");
  const detail = await download(page, "导出对应台账 CSV");
  expect(detail.rows).toHaveLength(1);
  expect(detail.rows[0]["作业日期"]).toBe("2025-12-31");
  await expect(page.getByLabel("统计茬次")).toHaveValue(first);
  await page.getByLabel("作业年份").selectOption("2026");
  const next = await download(page, "导出收支汇总 CSV");
  expect(next.rows[0]["已记录收入（元）"]).toBe("200.0");
  expect(next.rows[0]["记录次数"]).toBe("1");
});

test("导出失败显示服务提示并可重试，空结果仍可下载表头", async ({ page }) => {
  await prepare(page);
  await navigate(page, "农事台账");
  await page.route("**/api/farm-records/export.csv?**", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ success: false, error: "导出暂时不可用" }) }));
  await page.getByRole("button", { name: ledgerLabel }).click();
  await expect(page.getByRole("alert")).toHaveText("导出暂时不可用");
  await expect(page.getByRole("button", { name: ledgerLabel })).toBeEnabled();
  await page.unroute("**/api/farm-records/export.csv?**");
  let downloads = 0;
  page.on("download", () => { downloads++; });
  await page.route("**/api/farm-records/export.csv?**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<html>unexpected page</html>" }));
  await page.getByRole("button", { name: ledgerLabel }).click();
  await expect(page.getByRole("alert")).toContainText("导出响应格式异常");
  expect(downloads).toBe(0);
  await page.unroute("**/api/farm-records/export.csv?**");
  const { rows } = await download(page, ledgerLabel);
  expect(rows).toHaveLength(0);
  await expect(page.getByRole("status").filter({ hasText: "仅含表头" })).toBeVisible();
  await expect(page.getByText("CSV 用于留档和分析，不能作为完整数据库恢复备份。", { exact: false })).toBeVisible();
});

test("手机收支页可下载，演示来源与真实记录明确区分", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录", exact: true }).click();
  await page.getByRole("button", { name: "加载演示数据", exact: true }).click();
  await expect(page.getByText("演示已加载", { exact: false })).toBeVisible();
  await navigate(page, "统计面板");
  await page.getByLabel("收支数据来源").selectOption("demo");
  const { rows, file } = await download(page, "导出对应台账 CSV");
  expect(rows).toHaveLength(3);
  expect(rows.every((row) => row["记录来源"] === "演示记录")).toBe(true);
  expect(file.suggestedFilename()).toContain("演示记录");
  await page.getByLabel("收支数据来源").selectOption("real");
  const real = await download(page, "导出对应台账 CSV");
  expect(real.rows).toHaveLength(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
