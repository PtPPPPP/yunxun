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

async function createPlot(page: Page, name: string, area: string) {
  await page.getByPlaceholder("例如：东坡三亩地").fill(name);
  await page.getByLabel("面积（亩）").fill(area);
  await page.getByRole("button", { name: "新建地块" }).click();
  await expect(page.locator(".plot-card").filter({ hasText: name })).toBeVisible();
}

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
