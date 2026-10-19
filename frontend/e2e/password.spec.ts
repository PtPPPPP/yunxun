import { expect, test, type Page } from "playwright/test";

const apiURL = "http://127.0.0.1:8011/api";
const initialPassword = "original-password";
const newPassword = "changed-password";
const security = (page: Page) => page.getByRole("region", { name: "账号安全设置" });

async function register(page: Page) {
  const username = `password_${Date.now().toString(16)}_${Math.random().toString(16).slice(2, 6)}`;
  const response = await page.request.post(`${apiURL}/auth/register`, { data: { username, password: initialPassword, display_name: "密码测试农户" } });
  expect(response.ok()).toBeTruthy();
  const { user } = await response.json();
  await page.goto("/");
  await expect(page.getByRole("main")).toBeVisible();
  return { username, user };
}

async function openSecurity(page: Page) {
  await page.getByRole("button", { name: "账号安全", exact: true }).click();
  await expect(security(page)).toBeVisible();
}

async function generate(page: Page) {
  await security(page).getByLabel("生成恢复码用的当前密码").fill(initialPassword);
  await security(page).getByRole("button", { name: "生成或更换恢复码" }).click();
  const output = security(page).getByLabel("本次恢复码");
  await expect(output).toBeVisible();
  const code = (await output.textContent())!;
  expect(code).toMatch(/^[A-Za-z0-9_-]{43}$/);
  await security(page).getByRole("button", { name: "我已离线保存，关闭" }).click();
  await expect(output).toHaveCount(0);
  return code;
}

async function login(page: Page, username: string, password: string) {
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录并继续" }).click();
  await expect(page.getByRole("main")).toBeVisible();
}

async function fillRecovery(page: Page, username: string, code: string) {
  await page.getByLabel("账号用户名", { exact: true }).fill(username);
  await page.getByLabel("离线恢复码", { exact: true }).fill(code);
  await page.getByLabel("新密码", { exact: true }).fill(newPassword);
  await page.getByLabel("再次输入新密码", { exact: true }).fill(newPassword);
}

test("原密码错误可纠正，改密重复点击只提交一次，其他设备退出且业务归属保留", async ({ page, browser }) => {
  const { username, user } = await register(page);
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "yunxun_csrf")!.value;
  const created = await page.request.post(`${apiURL}/plots`, { headers: { "X-CSRF-Token": csrf }, data: { name: "改密前的地块", crop: "玉米", area_mu: 2, soil_type: "壤土", irrigation: "井灌" } });
  expect(created.ok()).toBeTruthy();
  const before = (await (await page.request.get(`${apiURL}/plots`)).json()).plots;
  const other = await browser.newContext();
  try {
    expect((await other.request.post(`${apiURL}/auth/login`, { data: { username, password: initialPassword } })).ok()).toBeTruthy();
    await openSecurity(page);
    await security(page).getByLabel("原密码", { exact: true }).fill("incorrect-password");
    await security(page).getByLabel("新密码", { exact: true }).fill(newPassword);
    await security(page).getByLabel("再次输入新密码", { exact: true }).fill(newPassword);
    await security(page).getByRole("button", { name: "修改密码并退出全部设备" }).click();
    await expect(security(page).getByRole("alert")).toContainText("原密码不正确");
    expect((await page.request.get(`${apiURL}/me`)).status()).toBe(200);
    let submissions = 0;
    page.on("request", (request) => { if (request.url().endsWith("/api/auth/change-password")) submissions++; });
    await security(page).getByLabel("原密码", { exact: true }).fill(initialPassword);
    await security(page).getByRole("button", { name: "修改密码并退出全部设备" }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
    await expect(page.getByRole("button", { name: "登录并继续" })).toBeVisible();
    expect(submissions).toBe(1);
    await expect(page.getByRole("status")).toContainText("全部设备已退出登录");
    expect((await other.request.get(`${apiURL}/me`)).status()).toBe(401);
    await login(page, username, newPassword);
    expect((await (await page.request.get(`${apiURL}/me`)).json()).user.id).toBe(user.id);
    expect((await (await page.request.get(`${apiURL}/plots`)).json()).plots).toEqual(before);
  } finally { await other.close(); }
});

test("恢复码只展示一次，重新生成使旧码失效，成功恢复后不能重复使用", async ({ page }) => {
  const { username, user } = await register(page);
  await openSecurity(page);
  const oldCode = await generate(page);
  const code = await generate(page);
  expect(code).not.toBe(oldCode);
  expect(await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain(code);
  await page.reload();
  await openSecurity(page);
  await expect(security(page).getByLabel("本次恢复码")).toHaveCount(0);
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await page.getByRole("button", { name: "用恢复码重置密码", exact: true }).click();
  await fillRecovery(page, username, oldCode);
  await page.getByRole("button", { name: "确认重置密码" }).click();
  await expect(page.getByRole("alert")).toContainText("账号或恢复凭据无效");
  await page.getByLabel("离线恢复码", { exact: true }).fill(code);
  await page.getByRole("button", { name: "确认重置密码" }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(page.getByRole("button", { name: "登录并继续" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("恢复码已使用");
  await page.getByRole("button", { name: "用恢复码重置密码", exact: true }).click();
  await fillRecovery(page, username, code);
  await page.getByRole("button", { name: "确认重置密码" }).click();
  await expect(page.getByRole("alert")).toContainText("账号或恢复凭据无效");
  await page.getByRole("button", { name: "返回登录", exact: true }).click();
  await login(page, username, newPassword);
  expect((await (await page.request.get(`${apiURL}/me`)).json()).user.id).toBe(user.id);
});

test("恢复表单取消与校验不发请求，不根据公开信息假装找回", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "用恢复码重置密码", exact: true }).click();
  await expect(page.getByText("用户名和显示名称不能作为恢复凭据", { exact: false })).toBeVisible();
  let writes = 0;
  page.on("request", (request) => { if (request.url().endsWith("/api/auth/recover-password")) writes++; });
  await fillRecovery(page, "not_an_account", "not-a-real-code");
  await page.getByLabel("再次输入新密码", { exact: true }).fill("different-password");
  await page.getByRole("button", { name: "确认重置密码" }).click();
  await expect(page.getByRole("alert")).toContainText("不一致");
  await page.getByRole("button", { name: "返回登录", exact: true }).click();
  expect(writes).toBe(0);
  await page.getByRole("button", { name: "用恢复码重置密码", exact: true }).click();
  await expect(page.getByLabel("离线恢复码", { exact: true })).toHaveValue("");
});

test("改密响应中断后明确提示核对，用户可用新密码重新登录", async ({ page }) => {
  const { username } = await register(page);
  await openSecurity(page);
  await page.route("**/api/auth/change-password", async (route) => { await route.fetch(); await route.abort("failed"); });
  await security(page).getByLabel("原密码", { exact: true }).fill(initialPassword);
  await security(page).getByLabel("新密码", { exact: true }).fill(newPassword);
  await security(page).getByLabel("再次输入新密码", { exact: true }).fill(newPassword);
  await security(page).getByRole("button", { name: "修改密码并退出全部设备" }).click();
  await expect(security(page).getByRole("alert")).toContainText("改密结果未确认");
  await security(page).getByRole("button", { name: "返回登录核对" }).click();
  await login(page, username, newPassword);
});

test("手机可管理密码与查看帮助，访客须先保存账号", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await register(page);
  await page.getByRole("button", { name: "打开导航" }).click();
  await openSecurity(page);
  await expect(security(page).getByLabel("原密码", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name: "使用帮助", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("恢复码");
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  // 帮助沿用原有行为：关闭对话框后导航仍打开，先关闭再验证重新打开。
  await page.getByRole("complementary", { name: "主导航" }).getByRole("button", { name: "关闭导航", exact: true }).click();
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await page.getByRole("button", { name: "访客登录", exact: true }).click();
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("button", { name: "账号安全", exact: true })).toHaveCount(0);
});
