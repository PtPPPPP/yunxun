import { expect, test, type Page, type Route } from "playwright/test";

const apiURL = "http://127.0.0.1:8011/api";
const password = "session-test-password";
const profile = (page: Page) => page.getByRole("complementary", { name: "主导航" });
const pending = (page: Page) => page.getByRole("region", { name: "退出确认" });

async function write(page: Page, path: string, data?: object, method = "POST") {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")?.value;
  return page.request.fetch(`${apiURL}${path}`, { method, data, headers: csrf ? { "X-CSRF-Token": csrf } : {} });
}
async function register(page: Page, name = "农户A") {
  const username = `session_${Date.now().toString(16)}_${Math.random().toString(16).slice(2, 8)}`;
  const result = await write(page, "/auth/register", { username, password, display_name: name });
  expect(result.ok()).toBeTruthy();
  return { ...(await result.json()), username };
}
async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("main")).toBeVisible();
}
async function login(page: Page, username: string) {
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录并继续" }).click();
  await expect(page.getByRole("main")).toBeVisible();
}
async function logout(page: Page) {
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
}
async function loggedOut(page: Page) {
  await expect(page.getByRole("button", { name: "登录并继续" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("已确认退出");
}
function latch() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}
async function delay(page: Page, url: string, response: "success" | "error" = "success") {
  const arrived = latch(), release = latch(), finished = latch();
  await page.route(url, async (route: Route) => {
    const result = response === "success" ? await route.fetch() : null;
    arrived.resolve();
    await release.promise;
    if (result) await route.fulfill({ response: result });
    else await route.fulfill({ status: 500, json: { success: false, error: "旧会话迟到的错误" } });
    finished.resolve();
  });
  return { arrived: arrived.promise, release: async () => { release.resolve(); await finished.promise; } };
}
async function settle(page: Page) {
  // 等待网络响应进入 React，而不是依赖固定毫秒数。
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

test("正常退出撤销会话，保留 HttpOnly 且浏览器存储没有 Token", async ({ page }) => {
  const account = await register(page);
  await open(page);
  const cookie = (await page.context().cookies()).find((item) => item.name === "yunxun_session")!;
  expect(cookie.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain(cookie.value);
  await logout(page);
  await loggedOut(page);
  expect((await page.request.get(`${apiURL}/me`)).status()).toBe(401);
  const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(storage).not.toContain(account.token);
  expect(storage).not.toContain("yunxun.logout-pending");
  await page.reload();
  await expect(page.getByRole("button", { name: "登录并继续" })).toBeVisible();
  await expect(page.getByRole("main")).toHaveCount(0);
});

test("退出请求未送达：隐藏资料、明确失败、刷新与重新打开仍阻止恢复并可重试", async ({ page }) => {
  const account = await register(page);
  await open(page);
  await page.route("**/api/auth/logout", (route) => route.abort("failed"));
  await logout(page);
  await expect(pending(page).getByRole("alert")).toContainText("退出尚未确认");
  await expect(page.getByRole("main")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "登录并继续" })).toHaveCount(0);
  expect((await page.request.get(`${apiURL}/me`)).status()).toBe(200);
  const storage = await page.evaluate(() => ({ ...localStorage }));
  expect(storage["yunxun.logout-pending"]).toBe(account.session_id);
  expect(JSON.stringify(storage)).not.toContain(account.token);
  await page.reload();
  await expect(pending(page).getByRole("alert")).toContainText("退出尚未确认");
  await page.goto("about:blank");
  await page.goto("/");
  await expect(pending(page).getByRole("alert")).toContainText("退出尚未确认");
  await expect(page.getByRole("main")).toHaveCount(0);
  await page.unroute("**/api/auth/logout");
  await pending(page).getByRole("button", { name: "重试退出" }).click();
  await loggedOut(page);
  expect((await page.request.get(`${apiURL}/me`)).status()).toBe(401);
});

test("服务端已退出但响应丢失：核对 401 后确认退出，可以重新登录同一个账号", async ({ page }) => {
  const account = await register(page);
  await open(page);
  await page.route("**/api/auth/logout", async (route) => { await route.fetch(); await route.abort("failed"); });
  await logout(page);
  await loggedOut(page);
  expect((await page.request.get(`${apiURL}/me`)).status()).toBe(401);
  await login(page, account.username);
  expect((await (await page.request.get(`${apiURL}/me`)).json()).user.id).toBe(account.user.id);
});

test("退出响应与身份核对都失败：保留标记，刷新后幂等重试确认", async ({ page }) => {
  await register(page);
  await open(page);
  await page.route("**/api/auth/logout", async (route) => { await route.fetch(); await route.abort("failed"); });
  await page.route("**/api/me", (route) => route.abort("failed"));
  await logout(page);
  await expect(pending(page).getByRole("alert")).toContainText("退出尚未确认");
  await page.unroute("**/api/auth/logout");
  await page.unroute("**/api/me");
  await page.reload();
  await loggedOut(page);
  expect((await page.request.get(`${apiURL}/me`)).status()).toBe(401);
});

test("网络恢复事件继续完成待确认退出", async ({ page }) => {
  await register(page);
  await open(page);
  await page.route("**/api/auth/logout", (route) => route.abort("failed"));
  await logout(page);
  await expect(pending(page).getByRole("alert")).toContainText("退出尚未确认");
  await page.unroute("**/api/auth/logout");
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await loggedOut(page);
});

test("退出响应延迟时禁止重新认证与重复提交，旧响应不能删除其后登录的 Cookie", async ({ page }) => {
  await register(page);
  await open(page);
  const held = await delay(page, "**/api/auth/logout");
  await page.getByRole("button", { name: "退出登录", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await held.arrived;
  await expect(pending(page).getByRole("button")).toBeDisabled();
  await expect(page.getByRole("button", { name: "登录并继续" })).toHaveCount(0);
  // 另一个页面在同一浏览器中登录 B；随后才把 A 的退出响应交给页面。
  const next = await register(page, "农户B");
  await held.release();
  await loggedOut(page);
  const current = await (await page.request.get(`${apiURL}/me`)).json();
  expect(current.user.id).toBe(next.user.id);
  expect(current.session_id).toBe(next.session_id);
});

for (const sameAccount of [false, true]) {
  test(`旧退出重试不能撤销新登录${sameAccount ? "同一账号" : "另一账号"}的会话`, async ({ page }) => {
    const account = await register(page);
    await open(page);
    await page.route("**/api/auth/logout", (route) => route.abort("failed"));
    await logout(page);
    await expect(pending(page).getByRole("alert")).toContainText("退出尚未确认");
    let next;
    if (sameAccount) next = await (await write(page, "/auth/login", { username: account.username, password })).json();
    else next = await register(page, "农户B");
    await page.unroute("**/api/auth/logout");
    const responsePromise = page.waitForResponse("**/api/auth/logout");
    await pending(page).getByRole("button", { name: "重试退出" }).click();
    expect((await responsePromise).status()).toBe(409);
    await expect(pending(page).getByRole("alert")).toContainText("当前会话已变化");
    const current = await (await page.request.get(`${apiURL}/me`)).json();
    expect(current.session_id).toBe(next.session_id);
    expect(current.user.id).toBe(next.user.id);
  });
}

for (const destination of ["退出", "B", "A"] as const) {
  for (const response of ["success", "error"] as const) {
    test(`姓名保存迟到${response}不能污染 A→${destination === "退出" ? "退出" : `退出→${destination}`} 的状态`, async ({ page }) => {
      const other = destination === "B" ? await register(page, "农户B") : null;
      const account = await register(page);
      await open(page);
      const held = await delay(page, "**/api/me/profile", response);
      await profile(page).getByLabel("显示名称", { exact: true }).fill("旧轮次的迟到姓名");
      await profile(page).getByRole("button", { name: "保存设置" }).click();
      await held.arrived;
      // 同一账号的新轮次必须有不同姓名，才能检测仅比较 user.id 的错误实现。
      if (destination === "A" && response === "success") {
        expect((await write(page, "/me/profile", { display_name: "新轮次姓名" }, "PATCH")).ok()).toBeTruthy();
      }
      await logout(page);
      await loggedOut(page);
      if (destination !== "退出") {
        await login(page, other?.username ?? account.username);
        const expected = destination === "B" ? "农户B" : response === "success" ? "新轮次姓名" : "农户A";
        await expect(profile(page).getByLabel("显示名称", { exact: true })).toHaveValue(expected);
        await held.release();
        await settle(page);
        await expect(profile(page).getByLabel("显示名称", { exact: true })).toHaveValue(expected);
        await expect(profile(page).locator(".profile-card__name")).toHaveText(expected);
        const current = await (await page.request.get(`${apiURL}/me`)).json();
        expect(current.user.id).toBe(other?.user.id ?? account.user.id);
      } else {
        await held.release();
        await settle(page);
        await expect(page.getByRole("main")).toHaveCount(0);
        await loggedOut(page);
      }
      await expect(page.getByText("旧会话迟到的错误", { exact: true })).toHaveCount(0);
    });
  }
}
