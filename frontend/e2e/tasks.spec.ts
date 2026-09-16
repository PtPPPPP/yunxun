import { expect, test, type Page } from "playwright/test";

function isoOffset(days: number): string {
  const now = new Date();
  now.setDate(now.getDate() + days);
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

async function guestLogin(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("main")).toBeVisible();
}

async function openTasks(page: Page) {
  await guestLogin(page);
  await page.getByRole("button", { name: "农事待办" }).click();
  await expect(page.getByRole("heading", { name: "农事待办" })).toBeVisible();
}

async function addTask(page: Page, title: string, dueOn: string) {
  await page.getByPlaceholder("例如：追肥后 7 天复查长势").fill(title);
  await page.getByLabel("到期日").fill(dueOn);
  await page.getByRole("button", { name: "新增待办" }).click();
  await expect(page.locator(".task-card").filter({ hasText: title })).toBeVisible();
}

test("待办清单初始为空状态", async ({ page }) => {
  await openTasks(page);
  await expect(page.locator(".stats-empty")).toContainText("没有待办事项");
  await expect(page.locator(".status-chip").filter({ hasText: "待办" })).toHaveCount(0);
});

test("新增待办后出现在清单与顶栏计数", async ({ page }) => {
  await openTasks(page);
  await addTask(page, "复查追肥后长势", isoOffset(1));

  await expect(page.locator(".task-card")).toHaveCount(1);
  await expect(page.locator(".task-group__title")).toContainText("本周内");
  await expect(page.locator(".status-chip").filter({ hasText: "待办" })).toContainText("待办 1 项");
});

test("逾期待办会被单独分组并在顶栏提示", async ({ page }) => {
  await openTasks(page);
  await addTask(page, "补打一次药", isoOffset(-3));

  await expect(page.locator(".task-group__title--overdue")).toContainText("已逾期（1）");
  await expect(page.locator(".status-chip").filter({ hasText: "逾期" })).toContainText("1 项逾期");
});

test("待办可以标记完成并重新打开", async ({ page }) => {
  await openTasks(page);
  await addTask(page, "复查追肥后长势", isoOffset(1));

  await page.getByRole("button", { name: "标记完成" }).click();
  await expect(page.locator(".task-card--done")).toContainText("复查追肥后长势");
  await expect(page.locator(".status-chip").filter({ hasText: "待办" })).toHaveCount(0);

  await page.getByRole("button", { name: "重新打开" }).click();
  await expect(page.locator(".task-card--done")).toHaveCount(0);
  await expect(page.locator(".status-chip").filter({ hasText: "待办" })).toContainText("待办 1 项");
});

test("删除待办需要二次确认", async ({ page }) => {
  await openTasks(page);
  await addTask(page, "去镇上买地膜", isoOffset(2));

  await page.getByRole("button", { name: "删除" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("删除这条待办？");
  await expect(dialog).toContainText("去镇上买地膜");
  await page.getByRole("button", { name: "确认删除" }).click();

  await expect(page.locator(".task-card")).toHaveCount(0);
  await expect(page.locator(".stats-empty")).toContainText("没有待办事项");
});

test("今日农活可以把整段建议存为待办", async ({ page }) => {
  await guestLogin(page);
  await page.getByRole("button", { name: "生成今日建议" }).click();
  await expect(page.locator(".report-block")).toContainText("今日建议");

  await page.getByRole("button", { name: "把建议存为待办" }).click();
  await expect(page.getByRole("button", { name: "已存为待办" })).toBeVisible();

  await page.getByRole("button", { name: "农事待办" }).click();
  const card = page.locator(".task-card");
  await expect(card).toContainText("按今日建议安排农活");
  await expect(card).toContainText("今日建议");
});

test("台账记完后可以一键加为待办", async ({ page }) => {
  await guestLogin(page);
  await page.getByRole("button", { name: "地块档案" }).click();
  await page.getByPlaceholder("例如：东坡三亩地").fill("东坡三亩地");
  await page.getByRole("button", { name: "新建地块" }).click();
  await expect(page.locator(".plot-card")).toBeVisible();

  await page.getByRole("button", { name: "农事台账" }).click();
  await page.getByLabel("作业类型").selectOption("施肥");
  await page.getByRole("button", { name: "记入台账" }).click();
  await expect(page.locator(".follow-up")).toContainText("已记入台账");

  await page.getByRole("button", { name: /加为待办/ }).click();
  await expect(page.locator(".follow-up")).toHaveCount(0);

  await page.getByRole("button", { name: "农事待办" }).click();
  await expect(page.locator(".task-card")).toContainText("复查追肥后长势");
});
