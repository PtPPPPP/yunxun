import { expect, test, type Page } from "playwright/test";

async function guestLogin(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("main")).toBeVisible();
}

test("访客可以进入聊天工作台", async ({ page }) => {
  await guestLogin(page);
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.locator(".app-version")).toHaveText(/^V\d+(?:\.\d+)+$/);
});

test("可以发送演示消息并刷新会话", async ({ page }) => {
  await guestLogin(page);
  await page.locator("textarea").fill("请给出玉米浇水建议");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("main")).toContainText("云寻AI");
  await page.reload();
  await expect(page.getByRole("main")).toBeVisible();
});

test("会话搜索支持无结果状态、帮助和关于软件", async ({ page }) => {
  await guestLogin(page);
  const search = page.getByLabel("搜索会话");
  await search.fill("不存在的会话");
  await expect(page.getByText("没有匹配的会话")).toBeVisible();
  await search.fill("");
  await page.getByRole("button", { name: "使用帮助" }).click();
  await expect(page.getByRole("dialog")).toContainText("使用帮助");
  await page.getByRole("button", { name: "关闭" }).click();
  await page.getByRole("button", { name: "关于软件" }).click();
  await expect(page.getByRole("dialog")).toContainText("云寻 AI");
});

test("移动端可以打开侧栏并使用搜索", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await guestLogin(page);
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("complementary", { name: "主导航" })).toHaveClass(/is-open/);
  await page.getByLabel("搜索会话").fill("玉米");
});

test("聊天界面不提供个人 API Key 入口", async ({ page }) => {
  await guestLogin(page);
  await expect(page.getByText(/API Key/i)).toHaveCount(0);
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.waitForTimeout(200);
  expect(requests.some((url) => url.includes("/api/model-configs"))).toBe(false);
});

test("会话工具栏提供复制、导出、清空和重新生成入口", async ({ page }) => {
  await guestLogin(page);
  await page.locator("textarea").fill("请给出今日农活建议");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "复制 AI 回复" })).toBeVisible();
  await expect(page.getByLabel("导出当前会话格式")).toBeVisible();
  await expect(page.getByRole("button", { name: "清空当前会话" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新生成最近回复" })).toBeVisible();
});
