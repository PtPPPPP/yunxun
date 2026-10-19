import { expect, test, type Page } from "playwright/test";

async function guestLogin(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("main")).toBeVisible();
}

test("访客可以进入今日农活工作台", async ({ page }) => {
  await guestLogin(page);
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByRole("heading", { name: "首页", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "今日农活", exact: true }).click();
  await expect(page.getByRole("heading", { name: "今日农活" })).toBeVisible();
  await expect(page.locator(".app-version")).toHaveText(/^V\d+(?:\.\d+)+$/);
});

test("可以生成今日农活建议", async ({ page }) => {
  await guestLogin(page);
  await page.getByRole("button", { name: "今日农活", exact: true }).click();
  await page.getByRole("button", { name: "生成今日建议" }).click();
  await expect(page.locator(".report-block")).toContainText("今日建议");
  await expect(page.locator(".report-block")).toContainText("降雨概率");
});

test("建议会写入统计面板的历史记录与趋势", async ({ page }) => {
  await guestLogin(page);
  await page.getByRole("button", { name: "今日农活", exact: true }).click();
  await page.getByRole("button", { name: "生成今日建议" }).click();
  await expect(page.locator(".report-block")).toContainText("今日建议");

  await page.getByRole("button", { name: "统计面板" }).click();
  await expect(page.locator(".stats-records .stats-record")).toHaveCount(1);
  await expect(page.locator(".stats-records")).toContainText("玉米");
  await expect(page.locator(".stats-crops")).toContainText("玉米");
  await expect(page.locator(".stat-card").filter({ hasText: "农活建议" })).toContainText("1");
});

test("帮助与关于软件使用去 AI 后的名称", async ({ page }) => {
  await guestLogin(page);
  await page.getByRole("button", { name: "使用帮助" }).click();
  await expect(page.getByRole("dialog")).toContainText("使用帮助");
  await expect(page.getByRole("dialog")).toContainText("费用未填与 0 元分别提示");
  await expect(page.getByRole("dialog")).toContainText("统计年度按作业日期划分");
  await expect(page.getByRole("dialog")).toContainText("回收站没有自动清理");
  await page.getByRole("button", { name: "关闭" }).click();

  await page.getByRole("button", { name: "关于软件" }).click();
  const about = page.getByRole("dialog");
  await expect(about).toContainText("云寻");
  for (const capability of ["地块与茬次档案", "农事台账与待办", "每茬已记录收支及追溯", "本机农活建议", "CSV 导出", "回收站", "账号安全"]) {
    await expect(about).toContainText(capability);
  }
  await expect(about).toContainText("软件版本：V1.0.0");
  await expect(about).not.toContainText("AI");
});

test("移动端可以打开侧栏并切换功能", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await guestLogin(page);
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("complementary", { name: "主导航" })).toHaveClass(/is-open/);
  await page.getByRole("button", { name: "统计面板" }).click();
  await expect(page.getByRole("heading", { name: "使用汇总" })).toBeVisible();
});

test("界面不提供个人 API Key 入口", async ({ page }) => {
  await guestLogin(page);
  await expect(page.getByText(/API Key/i)).toHaveCount(0);
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.waitForTimeout(200);
  expect(requests.some((url) => url.includes("/api/model-configs"))).toBe(false);
});
