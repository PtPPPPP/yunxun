import { expect, test, type Download, type Page } from "playwright/test";

const apiURL = "http://127.0.0.1:8011/api";
async function get(page: Page, path: string) { return (await page.request.get(`${apiURL}${path}`)).json(); }
async function navigate(page: Page, name: string) {
  await expect(page.getByRole("main")).toBeVisible();
  if (await page.getByRole("button", { name: "打开导航" }).isVisible()) await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name, exact: true }).click();
}
async function csvText(download: Download) {
  expect(await download.failure()).toBeNull();
  const chunks: Buffer[] = [];
  for await (const chunk of (await download.createReadStream())!) chunks.push(Buffer.from(chunk));
  const bytes = Buffer.concat(chunks);
  expect([...bytes.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
  return bytes.toString("utf8").slice(1);
}
async function snapshot(page: Page) {
  const [plots, seasons, records, tasks] = await Promise.all([
    get(page, "/plots"), get(page, "/seasons"), get(page, "/farm-records"), get(page, "/farm-tasks"),
  ]);
  return { plots: plots.plots, seasons: seasons.seasons, records: records.records, tasks };
}
async function fit(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const width of [1280, 390]) {
  test(`${width}px 当前版全链路：建地建茬→待办记账→编辑→换茬补录→收支导出→删除恢复→重登`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const username = `accept_${width}_${Date.now().toString(16)}`;
    const password = "acceptance-only-password";
    await page.goto("/");
    await page.getByRole("button", { name: "注册", exact: true }).click();
    await page.getByLabel("显示名称", { exact: true }).fill("验收样例农户");
    await page.getByLabel("用户名", { exact: true }).fill(username);
    await page.getByLabel("密码", { exact: true }).fill(password);
    await page.getByRole("button", { name: "注册并进入" }).click();
    await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["0", "0", "0", "0"]);
    const userId = (await get(page, "/me")).user.id;
    await page.getByRole("button", { name: "去登记地块", exact: true }).click();
    await page.getByLabel("地块名称").fill("验收样例田");
    await page.getByLabel("面积（亩）").fill("2");
    await page.getByLabel("播种或定植日期").fill("2026-04-01");
    await page.getByRole("button", { name: "新建地块", exact: true }).click();
    await expect(page.locator(".plot-card")).toHaveCount(1);
    const plot = (await get(page, "/plots")).plots[0];
    const firstId = plot.active_season.id as string;
    expect((await get(page, "/seasons")).seasons).toHaveLength(1);

    await navigate(page, "农事待办");
    await page.getByLabel("要做的事").fill("验收追肥");
    const today = await page.evaluate(() => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10));
    await page.getByLabel("到期日").fill(today);
    await page.getByLabel("关联地块（可不选）").selectOption(plot.id);
    await page.getByRole("button", { name: "新增待办", exact: true }).click();
    await navigate(page, "首页");
    const due = page.getByRole("region", { name: "今日待办" });
    await expect(due).toContainText("验收追肥");
    await due.getByRole("button", { name: "标记完成" }).click();
    await page.getByRole("region", { name: "待办完成提示" }).getByRole("button", { name: "顺便记入台账" }).click();
    const dialog = page.getByRole("dialog", { name: "从已完成待办记账" });
    await expect(dialog.getByLabel("所属茬次")).toHaveValue(firstId);
    await dialog.getByRole("group", { name: "快捷农活" }).getByRole("button", { name: "施肥", exact: true }).click();
    await dialog.getByLabel("费用（元）").fill("50");
    await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["0", "0", "1", "1"]);

    await navigate(page, "农事台账");
    await page.getByRole("button", { name: "编辑 施肥 记录" }).click();
    await page.getByLabel("费用（元）").fill("80");
    await page.getByLabel("作业日期", { exact: true }).fill("2026-04-30");
    await page.getByRole("button", { name: "保存修改" }).click();
    await expect(page.locator(".stats-records .stats-record")).toContainText("¥80");
    await navigate(page, "地块档案");
    await page.locator(".plot-card").getByRole("button", { name: "结束本茬" }).click();
    await page.getByLabel("结束或收获日期").fill("2026-05-31");
    await page.getByRole("button", { name: "确认结束本茬" }).click();
    await expect(page.locator(".plot-card")).toContainText("无进行中的茬次");
    await page.locator(".plot-card").getByRole("button", { name: "开始新茬" }).click();
    await page.getByRole("combobox", { name: "作物", exact: true }).selectOption("大豆");
    await page.getByLabel("播种或定植日期").fill("2026-10-01");
    await page.getByRole("button", { name: "确认开始新茬" }).click();
    await expect(page.locator(".plot-card")).toContainText("当前：大豆");
    await page.locator(".plot-card").getByRole("button", { name: "记一笔农活", exact: true }).click();
    const harvest = page.getByRole("dialog", { name: "记一笔农活", exact: true });
    await harvest.getByLabel("作业日期", { exact: true }).fill("2026-05-20");
    await expect(harvest.locator(".season-hint")).toContainText("玉米");
    await harvest.getByRole("group", { name: "快捷农活" }).getByRole("button", { name: "采收", exact: true }).click();
    await harvest.getByLabel("费用（元）").fill("0");
    await harvest.getByLabel("产量（公斤）").fill("100");
    await harvest.getByLabel("单价（元/公斤）").fill("3");
    await harvest.getByRole("button", { name: "记入台账", exact: true }).click();
    await expect(harvest).toHaveCount(0);

    await navigate(page, "农事台账");
    await page.getByRole("group", { name: "快捷农活" }).getByRole("button", { name: "采收", exact: true }).click();
    await page.getByLabel("作业日期", { exact: true }).fill("2026-05-21");
    await page.getByLabel("产量（公斤）").fill("10");
    await page.getByRole("button", { name: "记入台账", exact: true }).click();
    await expect(page.locator(".stats-records .stats-record")).toHaveCount(3);
    expect((await get(page, "/farm-records")).records.every((row: { season_id: string }) => row.season_id === firstId)).toBe(true);
    await navigate(page, "统计面板");
    await page.getByLabel("统计地块").selectOption(plot.id);
    await page.getByLabel("统计茬次").selectOption(firstId);
    await page.getByLabel("作业年份").selectOption("2026");
    const summary = width === 390 ? page.locator(".economics-season-card") : page.locator(".economics-table tbody tr");
    await expect(summary).toHaveCount(1);
    for (const value of ["¥80", "¥300", "¥220", "110 公斤", "费用未填 1 条", "采收待补录 1 条"]) await expect(summary).toContainText(value);
    await fit(page);
    await page.screenshot({ path: test.info().outputPath(`acceptance-${width}-economics.png`), fullPage: true });
    await summary.getByRole("button", { name: /^查看已完整记录收入台账/ }).click();
    await expect(page.locator(".stats-records .stats-record")).toHaveCount(1);
    await expect(page.locator(".stats-records .stats-record")).toContainText("收入 ¥300");
    await page.getByRole("button", { name: "返回收支统计" }).click();
    await expect(page.getByLabel("统计茬次")).toHaveValue(firstId);
    for (const label of ["导出收支汇总 CSV", "导出对应台账 CSV"]) {
      const pending = page.waitForEvent("download");
      await page.getByRole("button", { name: label, exact: true }).click();
      const file = await pending;
      expect(file.suggestedFilename()).toContain("作业2026年");
      const csv = await csvText(file);
      expect(csv).toContain("验收样例田");
      if (label.includes("汇总")) { expect(csv).toContain("220.0"); expect(csv.trim().split("\r\n")).toHaveLength(2); }
      else expect(csv.trim().split("\r\n")).toHaveLength(4);
    }
    const before = await snapshot(page);
    await navigate(page, "农事台账");
    await page.getByRole("button", { name: "删除 施肥 记录" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(page.locator(".stats-records .stats-record")).toHaveCount(2);
    await navigate(page, "回收站");
    await page.getByRole("button", { name: "恢复台账 施肥 2026-04-30" }).click();
    await expect(page.getByRole("region", { name: "回收站台账" }).locator(".trash-card")).toHaveCount(0);
    await navigate(page, "地块档案");
    await page.locator(".plot-card").getByRole("button", { name: "删除", exact: true }).click();
    const deletion = page.getByRole("dialog");
    await expect(deletion).toContainText("2 茬");
    await expect(deletion).toContainText("3 条农事台账记录");
    await expect(deletion).toContainText("1 项待办（含已完成）");
    await deletion.getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(page.locator(".plot-card")).toHaveCount(0);
    expect((await get(page, "/farm-records/stats")).record_count).toBe(0);
    await navigate(page, "回收站");
    await page.getByRole("button", { name: "恢复地块 验收样例田", exact: true }).click();
    await expect(page.getByRole("region", { name: "回收站地块" }).locator(".trash-card")).toHaveCount(0);
    expect(await snapshot(page)).toEqual(before);
    await navigate(page, "统计面板");
    await page.getByLabel("统计茬次").selectOption(firstId);
    await expect(page.locator(".economics-panel .stat-card").filter({ hasText: "已记录收支差额" })).toContainText("¥220");
    if (width === 390) await page.getByRole("button", { name: "打开导航" }).click();
    await page.getByRole("button", { name: "退出登录" }).click();
    await page.getByLabel("用户名", { exact: true }).fill(username);
    await page.getByLabel("密码", { exact: true }).fill(password);
    await page.getByRole("button", { name: "登录并继续" }).click();
    await expect(page.getByRole("heading", { name: "首页", exact: true })).toBeVisible();
    expect((await get(page, "/me")).user.id).toBe(userId);
    expect(await snapshot(page)).toEqual(before);
  });

  test(`${width}px 当前版状态：空数据、加载、403、断网、保存中与成功`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await page.getByRole("button", { name: "访客登录" }).click();
    await expect(page.locator(".home-summary .stat-card strong")).toHaveText(["0", "0", "0", "0"]);
    await expect(page.getByText("先登记一块地", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "记一笔农活", exact: true }).click();
    await page.getByLabel("地块名称").fill("状态验收样例田");
    await page.getByLabel("播种或定植日期").fill("2026-01-01");
    await page.getByRole("button", { name: "新建地块", exact: true }).click();
    await expect(page.locator(".plot-card")).toHaveCount(1);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/farm-records?**", async (route) => { await gate; await route.continue(); });
    await navigate(page, "农事台账");
    await expect(page.getByRole("status").filter({ hasText: "正在加载台账" })).toBeVisible();
    release();
    await expect(page.getByText("暂无台账记录，先在上面记一次农事吧。", { exact: true })).toBeVisible();
    await navigate(page, "首页");
    await page.getByRole("button", { name: "为状态验收样例田记农活" }).click();
    const dialog = page.getByRole("dialog", { name: "记一笔农活", exact: true });
    await dialog.getByLabel("费用（元）").fill("9");
    let mode = "permission", writes = 0;
    let finish!: () => void;
    const saving = new Promise<void>((resolve) => { finish = resolve; });
    await page.route("**/api/farm-records", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      writes++;
      if (mode === "permission") return route.fulfill({ status: 403, json: { success: false, error: "验收模拟：当前账号没有权限" } });
      if (mode === "offline") return route.abort("internetdisconnected");
      await saving; await route.continue();
    });
    await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("没有权限");
    await expect(dialog.getByLabel("费用（元）")).toHaveValue("9");
    mode = "offline";
    await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("无法连接");
    await expect(dialog.getByLabel("费用（元）")).toHaveValue("9");
    expect((await get(page, "/farm-records")).records).toHaveLength(0);
    mode = "save";
    await dialog.getByRole("button", { name: "记入台账", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "保存中…" })).toBeDisabled();
    finish();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("status").filter({ hasText: "已记入台账，可到统计面板" })).toBeVisible();
    expect(writes).toBe(3);
    expect((await get(page, "/farm-records")).records).toHaveLength(1);
    await fit(page);
    // Both already rendered advice and a delayed response belong to the old account.
    await navigate(page, "今日农活");
    await page.getByRole("combobox", { name: "作物", exact: true }).selectOption("柑橘");
    await page.getByRole("button", { name: "生成今日建议" }).click();
    await expect(page.locator(".report-block")).toContainText("柑橘");
    let releaseAdvice!: () => void, capturedAdvice!: () => void;
    const adviceGate = new Promise<void>((resolve) => { releaseAdvice = resolve; });
    const adviceReady = new Promise<void>((resolve) => { capturedAdvice = resolve; });
    await page.route("**/api/decision", async (route) => {
      const response = await route.fetch(); capturedAdvice(); await adviceGate; await route.fulfill({ response });
    });
    await page.getByRole("button", { name: "生成今日建议" }).click();
    await adviceReady;
    if (width === 390) await page.getByRole("button", { name: "打开导航" }).click();
    await page.getByRole("button", { name: "退出登录" }).click();
    await page.getByRole("button", { name: "访客登录" }).click();
    await navigate(page, "今日农活");
    await expect(page.locator(".report-block")).toHaveText("填写条件后，这里会生成建议。");
    await expect(page.getByRole("combobox", { name: "作物", exact: true })).toHaveValue("玉米");
    const oldResponse = page.waitForResponse((response) => response.url().endsWith("/api/decision"));
    releaseAdvice(); await (await oldResponse).finished();
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await expect(page.locator(".report-block")).toHaveText("填写条件后，这里会生成建议。");
  });
}
