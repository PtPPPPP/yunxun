import { expect, test, type Page } from "playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const apiURL = "http://127.0.0.1:8011/api";
const panel = (page: Page) => page.getByRole("region", { name: "保存访客账号" });
const username = () => `saved_${Date.now().toString(16)}`;
const password = "upgrade-test-password";
async function get(page: Page, path: string) { return (await page.request.get(`${apiURL}${path}`)).json(); }
async function write(page: Page, path: string, data?: Record<string, unknown>, method = "POST") {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const response = await page.request.fetch(`${apiURL}${path}`, { method, data, headers: { "X-CSRF-Token": csrf } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function guest(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录", exact: true }).click();
  await expect(panel(page).getByRole("button", { name: "保存账号", exact: true })).toBeVisible();
  return (await get(page, "/me")).user;
}
async function fill(page: Page, name = username()) {
  await panel(page).getByRole("button", { name: "保存账号", exact: true }).click();
  await panel(page).getByLabel("正式用户名").fill(name);
  await panel(page).getByLabel("账号显示名称").fill("保存后的农户");
  await panel(page).getByLabel("登录密码", { exact: true }).fill(password);
  await panel(page).getByLabel("再次输入密码").fill(password);
  return name;
}
async function seed(page: Page) {
  const { plot } = await write(page, "/plots", { name: "访客的真实田", area_mu: 2, soil_type: "壤土", irrigation: "井灌", crop: "玉米", planted_on: "2026-01-01" });
  await write(page, "/farm-records", { plot_id: plot.id, kind: "施肥", happened_on: "2026-10-19", cost: 35, detail: "真实记录保留" });
  await write(page, "/farm-tasks", { plot_id: plot.id, title: "访客自己的待办", due_on: "2026-10-19" });
  await write(page, "/decision", { crop: "玉米", stage: "快速生长期", rain_prob: 55, soil_moisture: 42, temperature: 25 });
  return plot;
}
async function snapshot(page: Page) {
  const [plots, seasons, records, tasks, suggestions] = await Promise.all([
    get(page, "/plots"), get(page, "/seasons"), get(page, "/farm-records"), get(page, "/farm-tasks"), get(page, "/tool-records"),
  ]);
  return { plots: plots.plots, seasons: seasons.seasons, records: records.records, tasks: tasks.tasks, suggestions: suggestions.records };
}
async function login(page: Page, name: string) {
  await expect(page.getByRole("button", { name: "登录并继续" })).toBeVisible();
  await page.getByLabel("用户名", { exact: true }).fill(name);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录并继续" }).click();
  await expect(page.getByRole("main")).toBeVisible();
}

test("访客保留全部业务数据原地升级，重复点击只提交一次，退出后新凭据可登录", async ({ page }) => {
  const original = await guest(page);
  await seed(page);
  await page.reload();
  const before = await snapshot(page);
  const cookiesBefore = await page.context().cookies();
  const name = await fill(page);
  let requests = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/auth/upgrade-guest")) requests++; });
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(panel(page)).toHaveCount(0);
  expect(requests).toBe(1);
  const current = (await get(page, "/me")).user;
  expect(current.id).toBe(original.id);
  expect(current.is_guest).toBe(false);
  expect(current.username).toBe(name);
  expect(current.display_name).toBe("保存后的农户");
  expect(await snapshot(page)).toEqual(before);
  const cookiesAfter = await page.context().cookies();
  for (const cookieName of ["yunxun_session", "yunxun_csrf"]) {
    expect(cookiesAfter.find((cookie) => cookie.name === cookieName)!.value).not.toBe(cookiesBefore.find((cookie) => cookie.name === cookieName)!.value);
  }
  await expect(page.getByRole("status").filter({ hasText: `账号已保存为 ${name}` })).toBeVisible();
  const logout = page.waitForResponse((response) => response.url().endsWith("/api/auth/logout") && response.request().method() === "POST");
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  expect((await logout).status()).toBe(200);
  await login(page, name);
  expect((await get(page, "/me")).user.id).toBe(original.id);
  expect(await snapshot(page)).toEqual(before);
});

test("用户名冲突保留访客数据和表单，换名后成功", async ({ page, request }) => {
  const taken = username();
  expect((await request.post(`${apiURL}/auth/register`, { data: { username: taken, password, display_name: "已注册农户" } })).ok()).toBeTruthy();
  const original = await guest(page);
  await seed(page);
  const before = await snapshot(page);
  await fill(page, taken.toUpperCase());
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page).getByRole("alert")).toContainText("用户名已存在");
  expect((await get(page, "/me")).user.id).toBe(original.id);
  expect((await get(page, "/me")).user.is_guest).toBe(true);
  expect(await snapshot(page)).toEqual(before);
  await expect(panel(page).getByLabel("登录密码", { exact: true })).toHaveValue(password);
  await panel(page).getByLabel("正式用户名").fill(username());
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page)).toHaveCount(0);
  expect(await snapshot(page)).toEqual(before);
});

test("打开后取消不升级，无效输入不发送请求，取消后不保留密码", async ({ page }) => {
  const original = await guest(page);
  let writes = 0;
  page.on("request", (request) => { if (request.url().endsWith("/api/auth/upgrade-guest")) writes++; });
  await fill(page, "bad-name");
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page).getByRole("alert")).toContainText("用户名需为");
  await panel(page).getByLabel("正式用户名").fill(username());
  await panel(page).getByLabel("再次输入密码").fill("different-password");
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page).getByRole("alert")).toContainText("密码不一致");
  expect(writes).toBe(0);
  await panel(page).getByRole("button", { name: "取消", exact: true }).click();
  expect((await get(page, "/me")).user).toEqual(original);
  await panel(page).getByRole("button", { name: "保存账号", exact: true }).click();
  await expect(panel(page).getByLabel("登录密码", { exact: true })).toHaveValue("");
});

test("服务失败后核对仍为访客，可以安全重试", async ({ page }) => {
  const original = await guest(page);
  const name = await fill(page);
  await page.route("**/api/auth/upgrade-guest", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "暂时无法保存" }) }));
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page).getByRole("alert")).toContainText("当前仍是访客");
  expect((await get(page, "/me")).user).toEqual(original);
  await expect(panel(page).getByLabel("正式用户名")).toHaveValue(name);
  await page.unroute("**/api/auth/upgrade-guest");
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page)).toHaveCount(0);
  expect((await get(page, "/me")).user.id).toBe(original.id);
});

test("升级落库但响应丢失时保留新凭据提示，重新登录仍取回原数据", async ({ page }) => {
  const original = await guest(page);
  await seed(page);
  const before = await snapshot(page);
  const oldCookies = await page.context().cookies();
  const name = await fill(page);
  await page.route("**/api/auth/upgrade-guest", async (route) => {
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    // 模拟客户端完全没收到新会话响应头，继续持有已被撤销的访客 Cookie。
    await page.context().addCookies(oldCookies);
    await route.abort("failed");
  });
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page).getByRole("alert")).toContainText("账号可能已经保存");
  await expect(panel(page).getByRole("button", { name: "确认保存账号", exact: true })).toBeDisabled();
  await panel(page).getByRole("button", { name: "返回登录", exact: true }).click();
  await expect(page.getByLabel("用户名", { exact: true })).toHaveValue(name);
  await login(page, name);
  expect((await get(page, "/me")).user.id).toBe(original.id);
  expect(await snapshot(page)).toEqual(before);
});

test("网络未恢复时先核对，不误报保存失败或丢弃填写凭据", async ({ page }) => {
  const original = await guest(page);
  await fill(page);
  await page.route("**/api/auth/upgrade-guest", (route) => route.abort("failed"));
  await page.route("**/api/me", (route) => route.abort("failed"));
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page).getByRole("alert")).toContainText("不要退出当前访客会话");
  await expect(panel(page).getByRole("button", { name: "确认保存账号", exact: true })).toBeDisabled();
  await expect(panel(page).getByRole("button", { name: "取消", exact: true })).toHaveCount(0);
  await page.unroute("**/api/me");
  await page.unroute("**/api/auth/upgrade-guest");
  await panel(page).getByRole("button", { name: "核对保存结果", exact: true }).click();
  await expect(panel(page).getByRole("alert")).toContainText("当前仍是访客");
  await expect(panel(page).getByRole("button", { name: "确认保存账号", exact: true })).toBeEnabled();
  expect((await get(page, "/me")).user).toEqual(original);
});

test("升级后演示来源不变，正式账号仍能只清空演示资料", async ({ page }) => {
  const original = await guest(page);
  await seed(page);
  await page.getByRole("region", { name: "首次使用引导" }).getByRole("button", { name: "加载演示数据", exact: true }).click();
  await expect(page.getByRole("button", { name: "只清空演示数据", exact: true })).toBeVisible();
  const before = await snapshot(page);
  await fill(page);
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page)).toHaveCount(0);
  expect(await snapshot(page)).toEqual(before);
  await expect(page.getByText("已保留的演示资料", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "只清空演示数据", exact: true }).click();
  await expect(page.getByRole("button", { name: "只清空演示数据", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "加载演示数据", exact: true })).toHaveCount(0);
  const after = await snapshot(page);
  expect(after.records).toHaveLength(1);
  expect(after.tasks).toHaveLength(1);
  expect(after.suggestions).toHaveLength(1);
  expect((await get(page, "/me")).user.id).toBe(original.id);
});

test("手机可保存 guest_ 开头的正式用户名，按服务端身份隐藏升级入口", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await guest(page);
  await fill(page, `guest_${Date.now().toString(16)}`);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(tmpdir(), "yunxun-upgrade-mobile.png"), fullPage: true });
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page)).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("main")).toBeVisible();
  await expect(panel(page)).toHaveCount(0);
  const user = (await get(page, "/me")).user;
  expect(user.username.startsWith("guest_")).toBe(true);
  expect(user.is_guest).toBe(false);
});

test("会话已升级而页面仍显示访客时，核对身份后收起入口，不覆盖凭据", async ({ page }) => {
  const original = await guest(page);
  const name = await fill(page);
  await write(page, "/auth/upgrade-guest", { username: name, password, display_name: "已保存的名称" });
  await panel(page).getByLabel("正式用户名").fill("must_not_overwrite");
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page)).toHaveCount(0);
  const user = (await get(page, "/me")).user;
  expect(user.id).toBe(original.id);
  expect(user.username).toBe(name);
  expect(user.display_name).toBe("已保存的名称");
});

test("缺少 CSRF 时保留拒绝提示和访客身份，刷新后可正常保存", async ({ page }) => {
  const original = await guest(page);
  await fill(page);
  await page.context().clearCookies({ name: "yunxun_csrf" });
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page).getByRole("alert")).toContainText("安全校验未通过，请刷新页面后重试");
  expect((await get(page, "/me")).user).toEqual(original);
  await page.reload();
  await fill(page);
  await panel(page).getByRole("button", { name: "确认保存账号", exact: true }).click();
  await expect(panel(page)).toHaveCount(0);
  expect((await get(page, "/me")).user.id).toBe(original.id);
});
