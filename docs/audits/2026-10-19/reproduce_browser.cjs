const { createRequire } = require('node:module');
const { writeFileSync } = require('node:fs');
const requireProject = createRequire(process.cwd() + '/frontend/package.json');
const { chromium, expect } = requireProject('playwright/test');
const api = 'http://127.0.0.1:8019/api';
const base = 'http://127.0.0.1:5179';
(async () => {
  const browser = await chromium.launch({headless:true});
  const results = {};
  async function session() {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(base);
    await page.getByRole('button',{name:'访客登录',exact:true}).click();
    await expect(page.getByRole('heading',{name:'首页',exact:true})).toBeVisible();
    return {context,page};
  }
  try {
    {
      const {context,page} = await session();
      let release, arrived;
      const held = new Promise(resolve => { release=resolve; });
      const ready = new Promise(resolve => { arrived=resolve; });
      await page.route('**/api/me/profile',async route => {
        if(route.request().method() !== 'PATCH') return route.continue();
        const response = await route.fetch();
        arrived();
        await held;
        await route.fulfill({response});
      });
      await page.getByLabel('显示名称').fill('delayed-old-account');
      await page.getByRole('button',{name:'保存设置',exact:true}).click();
      await ready;
      await page.getByRole('button',{name:'退出登录',exact:true}).click();
      await expect(page.getByRole('button',{name:'访客登录',exact:true})).toBeVisible();
      // A new guest has a distinct account and session; only the old PATCH response is delayed.
      await page.getByRole('button',{name:'访客登录',exact:true}).click();
      await expect(page.getByRole('heading',{name:'首页',exact:true})).toBeVisible();
      const currentUser = (await (await page.request.get(api+'/me')).json()).user;
      release();
      await expect(page.locator('.profile-card__name')).toHaveText('delayed-old-account');
      const serverUser = (await (await page.request.get(api+'/me')).json()).user;
      results.stale_profile = {ui_name:await page.locator('.profile-card__name').innerText(),server_name:serverUser.display_name,server_session_unchanged:serverUser.id===currentUser.id};
      await context.close();
    }
    {
      const {context,page} = await session();
      await page.route('**/api/auth/logout',route => route.request().method()==='POST' ? route.abort('failed') : route.continue());
      await page.getByRole('button',{name:'退出登录',exact:true}).click();
      await expect(page.getByRole('button',{name:'访客登录',exact:true})).toBeVisible();
      const me = await page.request.get(api+'/me');
      await page.reload();
      await expect(page.getByRole('heading',{name:'首页',exact:true})).toBeVisible();
      results.failed_logout={server_me_status:me.status(),authenticated_again_after_reload:true};
      await context.close();
    }
    {
      const {context,page} = await session();
      const csrf=(await context.cookies()).find(c=>c.name==='yunxun_csrf').value;
      async function plot(name,crop) {
        const r=await page.request.post(api+'/plots',{headers:{'X-CSRF-Token':csrf},data:{name,crop,area_mu:2,soil_type:'壤土',irrigation:'井灌',planted_on:'2026-04-01'}});
        expect(r.ok()).toBeTruthy(); return (await r.json()).plot;
      }
      const a=await plot('audit-A','玉米'), b=await plot('audit-B','番茄');
      await page.reload();
      await page.getByRole('button',{name:'今日农活',exact:true}).click();
      await page.getByLabel('按地块带入').selectOption(a.id);
      await page.getByRole('button',{name:'生成今日建议',exact:true}).click();
      await expect(page.locator('.report-block')).toContainText('玉米');
      const advice=await page.locator('.report-block').innerText();
      await page.getByLabel('按地块带入').selectOption(b.id);
      await page.getByRole('button',{name:'把建议存为待办',exact:true}).click();
      await expect(page.getByRole('button',{name:'已存为待办',exact:true})).toBeVisible();
      const body=await (await page.request.get(api+'/farm-tasks')).json();
      const task=body.tasks.find(t=>t.plot_id===b.id);
      results.advice_mismatch={saved_to_plot_b:!!task,title:task.title,notes_are_plot_a_advice:task.notes===advice.slice(0,1000),notes:task.notes};
      await context.close();
    }
    writeFileSync(process.argv[2],JSON.stringify(results,null,2));
    console.log(JSON.stringify(results,null,2));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
