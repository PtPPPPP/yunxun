import { expect, test, type Page } from "playwright/test";

async function guestLogin(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "访客登录" }).click();
  await expect(page.getByRole("heading", { name: "智能问答工作台" })).toBeVisible();
}

test("桌面端聊天持久化、重命名和删除确认", async ({ page }) => {
  await guestLogin(page);
  let releaseRequest!: () => void;
  const gate = new Promise<void>((resolve) => { releaseRequest = resolve; });
  let requestCount = 0;
  await page.route("**/api/chat/sessions/*/messages", async (route) => {
    requestCount += 1;
    await gate;
    await route.continue();
  });
  const input = page.getByPlaceholder(/输入你的问题/);
  await input.fill("端到端测试问题");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(input).toHaveValue("");
  await expect(page.getByText("正在生成回复…")).toBeVisible();
  await expect(page.getByRole("button", { name: /生成中/ })).toBeDisabled();
  releaseRequest();
  await expect(page.getByRole("main").getByText(/这个问题我先给稳妥建议/)).toBeVisible();
  expect(requestCount).toBe(1);
  await page.reload();
  await Promise.all([
    page.waitForResponse((response) => response.request().method() === "GET" && /\/api\/chat\/sessions\/[^?]+\?/.test(response.url())),
    page.getByRole("button", { name: /端到端测试问题/ }).click(),
  ]);
  await expect(page.getByRole("main").getByText(/这个问题我先给稳妥建议/)).toBeVisible();
  const titleInput = page.getByLabel("会话标题");
  await titleInput.fill("已重命名会话");
  await expect(titleInput).toHaveValue("已重命名会话");
  await Promise.all([
    page.waitForResponse((response) => response.request().method() === "PATCH" && response.url().includes("/api/chat/sessions/")),
    page.getByRole("button", { name: "保存标题" }).click(),
  ]);
  const renamedSession = page.getByRole("button", { name: /已重命名会话/ });
  await expect(renamedSession).toBeVisible();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "取消" }).click();
  await expect(renamedSession).toBeVisible();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(renamedSession).toHaveCount(0);
});

test("移动端导航、输入和布局", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await guestLogin(page);
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("complementary", { name: "主导航" })).toHaveClass(/is-open/);
  await page.getByRole("complementary", { name: "主导航" }).getByLabel("关闭导航").click();
  await expect(page.getByRole("complementary", { name: "主导航" })).not.toHaveClass(/is-open/);
  await page.getByPlaceholder(/输入你的问题/).fill("手机端问题");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("main").getByText(/这个问题我先给稳妥建议/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test("消息失败后恢复输入并用同一幂等键重试", async ({ page }) => {
  await guestLogin(page);
  const keys: string[] = [];
  let first = true;
  await page.route("**/api/chat/sessions/*/messages", async (route) => {
    keys.push(route.request().headers()["x-idempotency-key"]);
    if (first) {
      first = false;
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  const input = page.getByPlaceholder(/输入你的问题/);
  await input.fill("需要重试的问题");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("未完成")).toHaveCount(2);
  await expect(input).toHaveValue("需要重试的问题");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("main").getByText(/这个问题我先给稳妥建议/)).toBeVisible();
  await expect(page.getByText("未完成")).toHaveCount(0);
  expect(keys).toHaveLength(2);
  expect(keys[1]).toBe(keys[0]);
});

test("长会话暂停跟随、回到最新并保持历史加载位置", async ({ page }) => {
  test.setTimeout(60_000);
  await guestLogin(page);
  const token = await page.evaluate(() => localStorage.getItem("yunxun.auth.token"));
  const headers = { Authorization: `Bearer ${token}` };
  const created = await page.request.post("http://127.0.0.1:8011/api/chat/sessions", {
    headers, data: { title: "滚动测试", feature: "chat", model_name: "doubao-seed-1-6-250615" },
  });
  const sessionId = (await created.json()).session.id;
  for (let index = 0; index < 55; index += 1) {
    await page.request.post(`http://127.0.0.1:8011/api/chat/sessions/${sessionId}/messages`, {
      headers: { ...headers, "X-Idempotency-Key": `scroll-${index}` },
      data: { message: `历史消息 ${index} `.repeat(8), model_name: "doubao-seed-1-6-250615" },
    });
  }
  await page.reload();
  await page.getByRole("button", { name: /滚动测试/ }).click();
  const thread = page.locator(".chat-thread");
  await expect(page.getByRole("button", { name: "加载更早消息" })).toBeVisible();
  await thread.evaluate((node) => { node.scrollTop = 0; node.dispatchEvent(new Event("scroll")); });
  const before = await thread.evaluate((node) => ({ top: node.scrollTop, height: node.scrollHeight }));
  await page.getByRole("button", { name: "加载更早消息" }).click();
  await expect(page.getByText(/历史消息 0/)).toBeVisible();
  await expect.poll(() => thread.evaluate((node) => node.scrollHeight)).toBeGreaterThan(before.height);
  const afterLoad = await thread.evaluate((node) => node.scrollTop);
  expect(afterLoad).toBeGreaterThan(0);

  await thread.evaluate((node) => { node.scrollTop = Math.max(0, node.scrollHeight - node.clientHeight - 600); node.dispatchEvent(new Event("scroll")); });
  const readingTop = await thread.evaluate((node) => node.scrollTop);
  await page.getByPlaceholder(/输入你的问题/).fill("滚动期间的新消息");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "回到最新消息" })).toBeVisible();
  const afterReply = await thread.evaluate((node) => node.scrollTop);
  expect(Math.abs(afterReply - readingTop)).toBeLessThan(120);
  await page.getByRole("button", { name: "回到最新消息" }).click();
  await expect(page.getByRole("button", { name: "回到最新消息" })).toBeHidden();
  await expect.poll(() => thread.evaluate((node) => node.scrollHeight - node.scrollTop - node.clientHeight)).toBeLessThan(100);
});
