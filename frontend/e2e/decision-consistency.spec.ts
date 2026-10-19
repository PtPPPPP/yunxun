import { expect, test, type Page } from "playwright/test";

const apiURL = "http://127.0.0.1:8011/api";
const report = (page: Page) => page.locator(".report-block");
const generate = (page: Page) => page.getByRole("button", { name: "生成今日建议", exact: true });
const save = (page: Page) => page.getByRole("button", { name: "把建议存为待办", exact: true });
const plotSelect = (page: Page) => page.getByRole("combobox", { name: "按地块带入", exact: true });

async function setRange(page: Page, label: RegExp, value: number) {
  await page.getByLabel(label).evaluate((input: HTMLInputElement, nextValue) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, String(nextValue));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}

async function write(page: Page, path: string, data: object) {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const response = await page.request.post(`${apiURL}${path}`, { data, headers: { "X-CSRF-Token": csrf } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function setup(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录", exact: true }).click();
  await expect(page.getByRole("main")).toBeVisible();
  const first = (await write(page, "/plots", { name: "玉米试验田", crop: "玉米", area_mu: 2, soil_type: "壤土", irrigation: "井灌" })).plot;
  const second = (await write(page, "/plots", { name: "番茄试验田", crop: "番茄", area_mu: 3, soil_type: "壤土", irrigation: "滴灌" })).plot;
  await page.reload();
  await page.getByRole("button", { name: "今日农活", exact: true }).click();
  await expect(plotSelect(page)).toBeVisible();
  await plotSelect(page).selectOption(first.id);
  return { first, second };
}
async function tasks(page: Page) {
  return (await (await page.request.get(`${apiURL}/farm-tasks`)).json()).tasks;
}
async function ready(page: Page, crop = "玉米") {
  await generate(page).click();
  await expect(report(page)).toContainText(`作物为 ${crop}`);
  await expect(save(page)).toBeVisible();
}
function latch() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}
async function delayFirst(page: Page, path: string, error = false) {
  const arrived = latch(), release = latch(), finished = latch();
  let requests = 0;
  await page.route(`**/api/${path}`, async (route) => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    requests++;
    if (requests > 1) { await route.continue(); return; }
    const response = error ? null : await route.fetch();
    arrived.resolve();
    await release.promise;
    if (response) await route.fulfill({ response });
    else await route.fulfill({ status: 500, json: { error: "旧条件请求失败" } });
    finished.resolve();
  });
  return { arrived: arrived.promise, release: async () => { release.resolve(); await finished.promise; }, count: () => requests };
}
async function settle(page: Page) {
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

test("F3：从玉米地切换番茄地必须重新生成，待办标题、内容与地块一致", async ({ page }) => {
  const { second } = await setup(page);
  await ready(page);
  await expect(page.getByRole("status").filter({ hasText: "生成时地块" })).toContainText("玉米试验田");
  await plotSelect(page).selectOption(second.id);
  await expect(save(page)).toHaveCount(0);
  await expect(report(page)).not.toContainText("作物为 玉米");
  expect(await tasks(page)).toHaveLength(0);
  await ready(page, "番茄");
  await save(page).click();
  await expect(page.getByRole("button", { name: "已存为待办" })).toBeDisabled();
  const saved = await tasks(page);
  expect(saved).toHaveLength(1);
  expect(saved[0]).toMatchObject({ plot_id: second.id, title: "番茄：按今日建议安排农活" });
  expect(saved[0].notes).toContain("生成时地块：番茄试验田");
  expect(saved[0].notes).toContain("作物为 番茄");
  expect(saved[0].notes).not.toContain("玉米");
});

const changes = [
  { label: "作物", change: (page: Page) => page.getByRole("combobox", { name: "作物", exact: true }).selectOption("番茄") },
  { label: "生长期", change: (page: Page) => page.getByRole("combobox", { name: "生长期", exact: true }).selectOption("采收期") },
  { label: "气温", change: (page: Page) => page.getByLabel("气温 ℃", { exact: true }).fill("30") },
  { label: "降雨概率", change: (page: Page) => setRange(page, /未来降雨概率/, 80) },
  { label: "土壤湿度", change: (page: Page) => setRange(page, /土壤湿度/, 70) },
];
for (const { label, change } of changes) {
  test(`修改${label}立即清除旧结果与保存入口`, async ({ page }) => {
    await setup(page);
    await ready(page);
    await change(page);
    await expect(save(page)).toHaveCount(0);
    await expect(report(page)).toContainText("旧建议在条件变更或重新生成时清除");
    expect(await tasks(page)).toHaveLength(0);
  });
}

test("取消地块选择也清除旧建议，未关联地块的生成结果保留明确归属", async ({ page }) => {
  await setup(page);
  await ready(page);
  await plotSelect(page).selectOption("");
  await expect(save(page)).toHaveCount(0);
  await ready(page);
  await expect(page.getByRole("status").filter({ hasText: "生成时地块" })).toContainText("未关联地块");
  await save(page).click();
  await expect(page.getByRole("button", { name: "已存为待办" })).toBeVisible();
  const saved = await tasks(page);
  expect(saved[0].plot_id).toBeNull();
  expect(saved[0].notes).toContain("生成时地块：未关联地块");
});

for (const error of [false, true]) {
  test(`请求中修改地块可立即生成新建议，迟到${error ? "错误" : "成功"}不覆盖新条件`, async ({ page }) => {
    const { second } = await setup(page);
    const held = await delayFirst(page, "decision", error);
    await generate(page).click();
    await held.arrived;
    await plotSelect(page).selectOption(second.id);
    await setRange(page, /土壤湿度/, 70);
    await expect(generate(page)).toBeEnabled();
    await ready(page, "番茄");
    await expect(report(page)).toContainText("土壤湿度：70%");
    await held.release();
    await settle(page);
    await expect(report(page)).toContainText("作物为 番茄");
    await expect(page.getByText("旧条件请求失败", { exact: true })).toHaveCount(0);
    await save(page).click();
    await expect(page.getByRole("button", { name: "已存为待办" })).toBeVisible();
    const saved = await tasks(page);
    expect(saved).toHaveLength(1);
    expect(saved[0]).toMatchObject({ plot_id: second.id, title: "番茄：按今日建议安排农活" });
    expect(saved[0].notes).toContain("土壤湿度：70%");
    expect(saved[0].notes).not.toContain("玉米");
  });
}

for (const error of [false, true]) {
  test(`生成中修改湿度再改回原值，旧${error ? "错误" : "成功"}仍失效`, async ({ page }) => {
    await setup(page);
    const held = await delayFirst(page, "decision", error);
    await generate(page).click();
    await held.arrived;
    await setRange(page, /土壤湿度/, 70);
    await setRange(page, /土壤湿度/, 42);
    await held.release();
    await settle(page);
    await expect(save(page)).toHaveCount(0);
    await expect(report(page)).toContainText("请核对当前条件");
    await expect(page.getByText("旧条件请求失败", { exact: true })).toHaveCount(0);
    await ready(page);
  });
}

for (const networkFailure of [false, true]) {
  test(`重新生成${networkFailure ? "网络失败" : "服务失败"}不能保留旧建议，修正后可重试`, async ({ page }) => {
    await setup(page);
    await ready(page);
    await page.route("**/api/decision", (route) => networkFailure ? route.abort("failed") : route.fulfill({ status: 500, json: { error: "本次生成失败" } }));
    await generate(page).click();
    await expect(page.locator(".toast-banner")).toBeVisible();
    await expect(generate(page)).toBeEnabled();
    await expect(save(page)).toHaveCount(0);
    await expect(report(page)).not.toContainText("作物为 玉米");
    await page.unroute("**/api/decision");
    await ready(page);
  });
}

test("新请求失败后旧成功响应不能复活可保存的建议", async ({ page }) => {
  const { second } = await setup(page);
  const held = await delayFirst(page, "decision");
  await generate(page).click();
  await held.arrived;
  await plotSelect(page).selectOption(second.id);
  await page.route("**/api/decision", (route) => route.fulfill({ status: 500, json: { error: "新条件生成失败" } }));
  await generate(page).click();
  await expect(page.locator(".toast-banner")).toContainText("新条件生成失败");
  await held.release();
  await settle(page);
  await expect(save(page)).toHaveCount(0);
  await expect(report(page)).not.toContainText("作物为 玉米");
  await expect(page.locator(".toast-banner")).toContainText("新条件生成失败");
});

test("生成与保存重复点击只提交一次，保存期间条件锁定，条件变化后新结果可再次保存", async ({ page }) => {
  const { second } = await setup(page);
  const heldGeneration = await delayFirst(page, "decision");
  await generate(page).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await heldGeneration.arrived;
  await expect(page.getByRole("button", { name: "生成中…" })).toBeDisabled();
  expect(heldGeneration.count()).toBe(1);
  await heldGeneration.release();
  await expect(save(page)).toBeVisible();
  const heldSave = await delayFirst(page, "farm-tasks");
  await save(page).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await heldSave.arrived;
  await expect(page.getByRole("button", { name: "正在存为待办…" })).toBeDisabled();
  await expect(plotSelect(page)).toBeDisabled();
  await expect(page.getByRole("combobox", { name: "作物", exact: true })).toBeDisabled();
  await expect(generate(page)).toBeDisabled();
  expect(heldSave.count()).toBe(1);
  await heldSave.release();
  const savedButton = page.getByRole("button", { name: "已存为待办" });
  await expect(savedButton).toBeDisabled();
  await savedButton.evaluate((button: HTMLButtonElement) => button.click());
  expect(heldSave.count()).toBe(1);
  expect(await tasks(page)).toHaveLength(1);
  await plotSelect(page).selectOption(second.id);
  await ready(page, "番茄");
  await save(page).click();
  await expect(savedButton).toBeDisabled();
  expect(await tasks(page)).toHaveLength(2);
});

test("保存请求未送达可重试，标题使用实际输入而非地块原作物，API 字段保持不变", async ({ page }) => {
  const { first } = await setup(page);
  await page.getByRole("combobox", { name: "作物", exact: true }).selectOption("番茄");
  const requestPromise = page.waitForRequest("**/api/decision");
  await ready(page, "番茄");
  expect((await requestPromise).postDataJSON()).toEqual({ crop: "番茄", stage: "快速生长期", rain_prob: 55, soil_moisture: 42, temperature: 24.5 });
  await page.route("**/api/farm-tasks", (route) => route.request().method() === "POST" ? route.abort("failed") : route.continue());
  await save(page).click();
  await expect(page.locator(".toast-banner")).toBeVisible();
  await expect(save(page)).toBeEnabled();
  await expect(report(page)).toContainText("作物为 番茄");
  expect(await tasks(page)).toHaveLength(0);
  await page.unroute("**/api/farm-tasks");
  await save(page).click();
  await expect(page.getByRole("button", { name: "已存为待办" })).toBeVisible();
  const saved = await tasks(page);
  expect(saved).toHaveLength(1);
  expect(saved[0]).toMatchObject({ plot_id: first.id, title: "番茄：按今日建议安排农活" });
  expect(saved[0].notes).toContain("作物为 番茄");
});

test("产品与帮助明确用户输入及规则范围，手机端不横向溢出", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByText(/条件由你填写或估计，初始数值仅为示例/)).toBeVisible();
  await expect(page.getByText(/作物、生长期和气温只作记录，不参与分支判断/)).toBeVisible();
  await ready(page);
  await expect(report(page)).toContainText("没有自动天气或传感器数据");
  await expect(report(page)).toContainText("不是综合风险评估或用药依据");
  await expect(report(page)).not.toContainText("当前风险");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name: "使用帮助", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("修改任一条件后旧建议清除");
  await expect(page.getByRole("dialog")).toContainText("不是综合风险评估或用药依据");
});
