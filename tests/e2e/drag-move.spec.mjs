/**
 * 拖拽调课 · 真实浏览器回归测试
 *
 * 为什么不用 @playwright/test：仓库是 Python 项目，这里只需要一个能
 * `npm install && npm test` 的独立脚本。浏览器直接用本机 Edge 二进制，
 * 不下载 Chromium（CI / 离线机器也能跑）。
 *
 *   EDGE_PATH="...\msedge.exe" npm test
 *
 * 产物：artifacts/desktop.png、artifacts/mobile.png、artifacts/drag-edge.png
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const ARTIFACTS = path.join(HERE, 'artifacts');
fs.mkdirSync(ARTIFACTS, { recursive: true });

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript',
               '.css': 'text/css', '.json': 'application/json', '.png': 'image/png' };

const server = http.createServer((req, res) => {
  const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  if (pathname === '/favicon.ico') { res.writeHead(204); res.end(); return; }
  const rel = pathname === '/' ? 'docs/index.html' : pathname.replace(/^\/+/, '');
  const file = path.join(ROOT, rel);
  if (!file.startsWith(ROOT)) { res.writeHead(403); res.end(); return; }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found'); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${server.address().port}`;

const EDGE_CANDIDATES = [
  process.env.EDGE_PATH,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean);
const EXE = EDGE_CANDIDATES.find(p => fs.existsSync(p));
if (!EXE) {
  console.error('找不到 Edge，可用 EDGE_PATH 指定 msedge.exe 路径');
  server.close();
  process.exit(2);
}

const browser = await chromium.launch({
  executablePath: EXE, headless: true,
  args: ['--no-sandbox', '--disable-gpu', '--enable-unsafe-swiftshader'],
});

/* ---------- 页面探针 ---------- */
const state   = p => p.evaluate(() => window.__dragProbe.state());
const ov      = p => p.evaluate(() => window.__dragProbe.ov());
const weeks   = p => p.evaluate(() => window.__dragProbe.weeks());
const bands   = p => p.evaluate(() => window.__dragProbe.bands());
const cell    = (p, d, r) => p.evaluate(([d, r]) => window.__dragProbe.cellRect(d, r), [d, r]);
const course  = (p, date, period) => p.evaluate(([date, period]) => window.__dragProbe.courseRect(date, period), [date, period]);
const dateOf  = (p, w, d) => p.evaluate(([w, d]) => isoOf(dateOfWeekDay(w, d)), [w, d]);
const week3d  = p => p.evaluate(() => {
  const m = /第\s*(\d+)\s*周/.exec(document.getElementById('slotName').textContent);
  return m ? Number(m[1]) : null;
});
const mid     = r => ({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
const sleep   = ms => new Promise(r => setTimeout(r, ms));

async function dragTo(page, from, to, steps = 8) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + 10, from.y, { steps: 1 });   // 鼠标 8px 位移即拾起
  await page.mouse.move(to.x, to.y, { steps });
}
async function edgePoint(page, side, viewportHeight) {
  const b = await bands(page);
  const [a, z] = side === 'right' ? b.r : b.l;
  const y = Math.max(b.frame.top + 20,
    Math.min((b.frame.top + b.frame.bottom) / 2, viewportHeight - 20));
  return { x: (a + z) / 2, y };
}

const results = [];
async function run(name, fn, contextOptions = {}, pagePath = '/docs/index.html') {
  const is3d = pagePath.indexOf('3d.html') >= 0;
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, ...contextOptions });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => {
    const t = m.text();
    if (m.type() === 'error' && !/favicon\.ico/i.test(t)
        && !/WebGL|SwiftShader|GPU stall/i.test(t)) errors.push(`console: ${t}`);
  });
  try {
    await page.goto(`${BASE}${pagePath}`);
    if (is3d) {
      await page.waitForSelector('#slotName');
      await sleep(2200);                      // 等 GLB 解析、Three.js 场景与首帧完成
    } else {
      await page.waitForSelector('#grid .course');
      await page.evaluate(() => localStorage.clear());
      await page.reload();
      await page.waitForSelector('#grid .course');
      /* 首屏切周有 330ms 的 swapin 3D 动画，动画期间网格框带 transform，
         getBoundingClientRect 不是稳定布局坐标。等它结束再取感应带。 */
      await page.waitForFunction(() => {
        const t = getComputedStyle(document.getElementById('gridFrame')).transform;
        return t === 'none' || t === 'matrix(1, 0, 0, 1, 0, 0)';
      });
    }
    await fn({ page, ctx, errors });
    assert.deepEqual(errors, [], `浏览器控制台有报错：${errors.join(' | ')}`);
    results.push({ name, ok: true });
    console.log(`  PASS  ${name}`);
  } catch (err) {
    results.push({ name, ok: false, err: String(err && err.message || err) });
    console.log(`  FAIL  ${name}\n        ${String(err && err.message || err)}`);
  } finally {
    await ctx.close();
  }
}

console.log(`Edge: ${EXE}\n页面: ${BASE}/docs/index.html\n`);

/* ---------- 1. 点击仍然打开详情 ---------- */
await run('点击课程仍打开详情，拖拽不抢 click', async ({ page }) => {
  const r = await course(page, await dateOf(page, 10, 1), 1);
  assert.ok(r, '第 10 周周一第 1 节应该有课');
  await page.mouse.click(...Object.values(mid(r)));
  await page.waitForSelector('#sheet.show');
  assert.match(await page.locator('#sheet').innerText(), /编译原理/);
  await sleep(600);                                     // closeSheet 有 520ms 免疫期
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('#sheet').classList.contains('show'));
  assert.equal((await ov(page)).length, 0, '点击不该写 OV');
});

/* ---------- 2. 长按/位移拾起 ---------- */
await run('位移 8px 拾起：幽灵、抖动、探针状态', async ({ page }) => {
  const r = await course(page, await dateOf(page, 10, 1), 1);
  await dragTo(page, mid(r), { x: mid(r).x + 12, y: mid(r).y + 6 }, 2);
  const s = await state(page);
  assert.ok(s && s.active && s.phase === 'active', '应进入 active');
  assert.equal(await page.locator('body.dragging').count(), 1);
  assert.equal(await page.locator('.drag-ghost').count(), 1);
  await page.mouse.up();
  assert.equal((await ov(page)).length, 0, '原地松手不写 OV');
});

/* ---------- 2b. 回归：拖拽时不选中文字 ---------- */
await run('回归：拖拽过程不产生文本选区（截图里整片蓝的问题）', async ({ page }) => {
  const src = await course(page, await dateOf(page, 10, 1), 1);
  const dst = await cell(page, 4, 2);
  await dragTo(page, mid(src), mid(dst), 10);
  const sel = await page.evaluate(() => ({
    text: window.getSelection() ? window.getSelection().toString() : '',
    ranges: window.getSelection() ? window.getSelection().rangeCount : 0,
    css: getComputedStyle(document.querySelector('.course')).userSelect,
    ghostCss: getComputedStyle(document.querySelector('.drag-ghost')).userSelect,
  }));
  assert.equal(sel.text, '', '拖拽不该选中任何文字');
  assert.equal(sel.ranges, 0, '不该残留 Range');
  assert.equal(sel.css, 'none', '课程块应禁用文本选择');
  assert.equal(sel.ghostCss, 'none', '幽灵卡也应禁用文本选择');
  await page.mouse.up();
});

/* ---------- 2c. 回归：状态栏在课表下方，调课后课表不位移 ---------- */
await run('回归：调课状态栏在课表下方，课表 top/height 不位移', async ({ page }) => {
  const layout = await page.evaluate(() => {
    const bar = document.getElementById('ovbar');
    const frame = document.getElementById('gridFrame');
    const r = frame.getBoundingClientRect();
    return {
      after: !!(frame.compareDocumentPosition(bar) & Node.DOCUMENT_POSITION_FOLLOWING),
      top: r.top, height: r.height,
    };
  });
  assert.equal(layout.after, true, 'ovbar 必须排在 gridFrame 之后');
  const d1 = await dateOf(page, 10, 1);
  await dragTo(page, mid(await course(page, d1, 1)), mid(await cell(page, 4, 2)), 8);
  await page.mouse.up();
  assert.equal((await ov(page)).length, 1);
  assert.equal(await page.locator('#ovbar.show').count(), 1, '状态栏应出现');
  const after = await page.evaluate(() => {
    const r = document.getElementById('gridFrame').getBoundingClientRect();
    return { top: r.top, height: r.height };
  });
  assert.ok(Math.abs(after.top - layout.top) < 1, `课表 top 不该变：${layout.top} → ${after.top}`);
  assert.ok(Math.abs(after.height - layout.height) < 1,
    `课表高度不该变：${layout.height} → ${after.height}`);
  await page.screenshot({ path: path.join(ARTIFACTS, 'desktop-after-move.png') });
});

/* ---------- 2d. 回归：无动画切周清掉旧定时器，不二次重绘 ---------- */
await run('回归：无动画切周清掉旧 _flipTimer，不二次重绘课表', async ({ page }) => {
  await page.evaluate(() => {
    window.__gridMutations = 0;
    window.__gridObserver = new MutationObserver(() => window.__gridMutations++);
    window.__gridObserver.observe(document.getElementById('grid'), { childList: true });
  });
  /* 先起一次带动画切周（160ms 后才 renderGrid），立刻用无动画切周覆盖。
     这正是拖拽翻周的调用顺序；不清定时器就会在 160ms 把旧一周重新画一遍。 */
  await page.evaluate(() => { showWeek(11, true); showWeek(12, false); });
  await sleep(80);
  const m1 = await page.evaluate(() => window.__gridMutations);
  await sleep(420);                              // 覆盖 160ms 定时器 + 330ms swapin
  const m2 = await page.evaluate(() => window.__gridMutations);
  assert.equal(m2, m1, '旧 _flipTimer 不该再触发一次 renderGrid');
  const state = await page.evaluate(() => ({
    week: window.__dragProbe.weeks().cur,
    cls: document.getElementById('gridFrame').className,
    courses: document.querySelectorAll('#grid .course').length,
    expected: DATA.weeks['12'].reduce((n, d) => n + d.courses.length, 0),
  }));
  assert.equal(state.week, 12);
  assert.ok(!/swapin|swapout/.test(state.cls), `不该残留动画 class：${state.cls}`);
  assert.equal(state.courses, state.expected, '课表内容必须是第 12 周');
});

/* ---------- 2e. 回归：拖拽翻周后不重播动画 ---------- */
await run('回归：拖拽翻周后不残留 swapin/swapout、不重播动画', async ({ page }) => {
  await page.locator('#next').click();
  await sleep(560);                               // 等带动画切周完成（swapin 会常驻）
  const w0 = (await weeks(page)).cur;
  const src = await course(page, await dateOf(page, w0, 1), 1);
  assert.ok(src, '该周周一应有课');
  assert.match(await page.evaluate(() => document.getElementById('gridFrame').className),
    /swapin/, '前置条件：此时 frame 上应挂着 swapin');
  const p = await edgePoint(page, 'right', 900);
  await dragTo(page, mid(src), p, 8);
  const target = w0 + 1;
  await page.waitForFunction(t => window.__dragProbe.weeks().cur === t,
    target, { timeout: 2000 });
  await page.mouse.up();
  await sleep(420);                               // 等 200ms WAAPI 动画结束
  const state = await page.evaluate(() => ({
    cls: document.getElementById('gridFrame').className,
    anims: document.getElementById('gridFrame').getAnimations().length,
    week: window.__dragProbe.weeks().cur,
  }));
  assert.equal(state.week, target);
  assert.ok(!/swapin|swapout|slide-next|slide-prev/.test(state.cls),
    `不该残留动画 class：${state.cls}`);
  assert.equal(state.anims, 0, '动画结束后不该有残留 animation');
});

/* ---------- 3. 网格外松手取消回弹 ---------- */
await run('拖到网格外松手：取消、不写数据', async ({ page }) => {
  const r = await course(page, await dateOf(page, 10, 1), 1);
  const b = await bands(page);
  const outside = { x: Math.max(12, b.frame.left - 120), y: Math.max(12, b.frame.top - 120) };
  await dragTo(page, mid(r), outside, 6);
  await page.mouse.up();
  assert.equal((await ov(page)).length, 0);
  assert.equal(await weeks(page).then(w => w.cur), 10, '不该翻周');
  await sleep(260);
  assert.equal(await page.locator('.drag-ghost').count(), 0, '幽灵应已回弹移除');
});

/* ---------- 4. 普通移动 + 5. 撤销 ---------- */
await run('同周移动：OV 正确、源格消失、目标格出现、可撤销', async ({ page }) => {
  const d1 = await dateOf(page, 10, 1), d4 = await dateOf(page, 10, 4);
  const src = await course(page, d1, 1);
  const dst = await cell(page, 4, 2);                  // 周四 3-4 节，空
  await dragTo(page, mid(src), mid(dst), 8);
  await page.mouse.up();

  const list = await ov(page);
  assert.equal(list.length, 1, '应只写一条 OV');
  assert.equal(list[0].type, 'move');
  assert.equal(list[0].fromDate, d1);
  assert.equal(list[0].fromPeriod, 1);
  assert.equal(list[0].toDate, d4);
  assert.equal(list[0].toPeriod, 3);
  assert.equal(list[0].span, 2, '保持原节数');
  assert.equal(await course(page, d1, 1), null, '源周那节课应消失');
  assert.ok(await course(page, d4, 3), '目标格应出现课程');
  assert.equal(await page.locator('#toast.show').count(), 1, '应出现撤销提示');

  await page.locator('#toast [data-undo]').click();
  assert.equal((await ov(page)).length, 0, '撤销只回退这一次');
  assert.ok(await course(page, d1, 1), '源课应回来');
  assert.equal(await course(page, d4, 3), null, '目标课应撤走');
});

/* ---------- 6. 交换占位 ---------- */
await run('目标格已有课：两节交换，写两条 OV', async ({ page }) => {
  const d2 = await dateOf(page, 10, 2);
  const before = await page.locator('#grid .course').count();
  const src = await course(page, d2, 1);               // 算法设计与分析 207
  const dst = await cell(page, 2, 2);                  // 周二 3-4 节，已有 316
  await dragTo(page, mid(src), mid(dst), 8);
  await page.mouse.up();
  const list = await ov(page);
  assert.equal(list.length, 2, '交换应写两条 OV');
  const a = list.find(o => o.fromPeriod === 1), b = list.find(o => o.fromPeriod === 3);
  assert.ok(a && b, '两条记录的原始节次应分别为 1 和 3');
  assert.equal(a.toPeriod, 3);
  assert.equal(b.toPeriod, 1);
  assert.equal(await page.locator('#grid .course').count(), before, '不该多出或丢课');
});

/* ---------- 7. 右边缘翻周 ---------- */
await run('拖出右侧感应带：停留 500ms 翻到下一周', async ({ page }) => {
  const src = await course(page, await dateOf(page, 10, 1), 1);
  const p = await edgePoint(page, 'right', 900);
  await dragTo(page, mid(src), p, 8);
  await page.waitForFunction(() => window.__dragProbe.weeks().cur === 11,
    null, { timeout: 2000 });
  assert.equal((await weeks(page)).cur, 11, '应从 W10 翻到 W11');
  assert.equal(await page.locator('#edgeR.hot').count(), 1, '右感应带应高亮');
  await page.screenshot({ path: path.join(ARTIFACTS, 'drag-edge.png') });
  await page.mouse.up();
  assert.equal((await ov(page)).length, 0, '在感应带松手应取消');
});

/* ---------- 8. 按住连翻 ---------- */
await run('按住不放：每 800ms 连翻一周', async ({ page }) => {
  const src = await course(page, await dateOf(page, 10, 1), 1);
  const p = await edgePoint(page, 'right', 900);
  await dragTo(page, mid(src), p, 8);
  await page.waitForFunction(() => window.__dragProbe.weeks().cur >= 12,
    null, { timeout: 4000 });
  const w = (await weeks(page)).cur;
  assert.ok(w >= 12, `应连翻至少到 W12，实际 W${w}`);
  await page.mouse.up();
});

/* ---------- 9. 左边缘翻周 ---------- */
await run('拖出左侧感应带：翻到上一周', async ({ page }) => {
  const src = await course(page, await dateOf(page, 10, 1), 1);
  const p = await edgePoint(page, 'left', 900);
  await dragTo(page, mid(src), p, 8);
  await page.waitForFunction(() => window.__dragProbe.weeks().cur === 9,
    null, { timeout: 2000 });
  assert.equal((await weeks(page)).cur, 9, '应从 W10 翻到 W9');
  await page.mouse.up();
});

/* ---------- 10 / 11. 首尾周停住 ---------- */
await run('W1 继续往左：停住不回卷，感应带显示 dead', async ({ page }) => {
  /* 数据里第 1 周本来就没课（weeks 从 2 起），从 W2 起拖再翻到 W1 */
  await page.evaluate(() => showWeek(2, false));
  const src = await course(page, await dateOf(page, 2, 1), 1);
  assert.ok(src, 'W2 周一应有课');
  const p = await edgePoint(page, 'left', 900);
  await dragTo(page, mid(src), p, 8);
  await page.waitForFunction(() => window.__dragProbe.weeks().cur === 1,
    null, { timeout: 2000 });
  await sleep(900);                                // 再等一个连翻周期，确认没回卷
  assert.equal((await weeks(page)).cur, 1);
  assert.equal(await page.locator('#edgeL.dead').count(), 1);
  await page.mouse.up();
});
await run('W17 继续往右：停住不回卷', async ({ page }) => {
  await page.evaluate(() => showWeek(DATA.maxWeek, false));
  const src = await course(page, await dateOf(page, 17, 1), 1);
  assert.ok(src, 'W17 周一应有课');
  const p = await edgePoint(page, 'right', 900);
  await dragTo(page, mid(src), p, 8);
  await page.waitForSelector('#edgeR.dead', { timeout: 2000 });
  assert.equal((await weeks(page)).cur, 17);
  await page.mouse.up();
});

/* ---------- 12. 跨周落位 ---------- */
await run('翻周后松手：源周是起拖那一周，目标落在当前周', async ({ page }) => {
  const d1 = await dateOf(page, 10, 1), w11d4 = await dateOf(page, 11, 4);
  const src = await course(page, d1, 1);
  const p = await edgePoint(page, 'right', 900);
  await dragTo(page, mid(src), p, 8);
  await page.waitForFunction(() => window.__dragProbe.weeks().cur === 11,
    null, { timeout: 2000 });
  assert.equal((await weeks(page)).cur, 11);
  const dst = await cell(page, 4, 2);
  await page.mouse.move(dst.left + dst.width / 2, dst.top + dst.height / 2, { steps: 6 });
  await page.mouse.up();
  const list = await ov(page);
  assert.equal(list.length, 1);
  assert.equal(list[0].fromDate, d1, '源周必须是起拖的 W10');
  assert.equal(list[0].toDate, w11d4, '目标必须是松手时的 W11');
  assert.equal(list[0].toPeriod, 3);
  assert.ok(await course(page, w11d4, 3), 'W11 目标格应出现课程');
});

/* ---------- 13. localStorage 持久化 ---------- */
await run('刷新页面：调课记录仍在', async ({ page }) => {
  const d1 = await dateOf(page, 10, 1), d4 = await dateOf(page, 10, 4);
  await dragTo(page, mid(await course(page, d1, 1)), mid(await cell(page, 4, 2)), 8);
  await page.mouse.up();
  assert.equal((await ov(page)).length, 1);
  await page.reload();
  await page.waitForSelector('#grid .course');
  assert.equal((await ov(page)).length, 1);
  assert.equal(await course(page, d1, 1), null);
  assert.ok(await course(page, d4, 3));
});

/* ---------- 14. Escape 取消 ---------- */
await run('拖拽中按 Escape：取消，不留幽灵', async ({ page }) => {
  const src = await course(page, await dateOf(page, 10, 1), 1);
  await dragTo(page, mid(src), { x: mid(src).x + 40, y: mid(src).y + 40 }, 4);
  assert.ok((await state(page)).active);
  await page.keyboard.press('Escape');
  assert.equal(await state(page), null);
  assert.equal((await ov(page)).length, 0);
  await sleep(260);
  assert.equal(await page.locator('.drag-ghost').count(), 0);
});

/* ---------- 15. 桌面截图 ---------- */
await run('桌面 1440x900 截图', async ({ page }) => {
  await page.screenshot({ path: path.join(ARTIFACTS, 'desktop.png') });
  assert.ok(fs.statSync(path.join(ARTIFACTS, 'desktop.png')).size > 10000);
});

/* ---------- 16. 手机视口 + 触摸长按 + 横滑锁 ---------- */
await run('手机 390x844：触摸长按拾起、横滑被锁、截图', async ({ page, ctx }) => {
  const cdp = await ctx.newCDPSession(page);
  const d1 = await dateOf(page, 10, 1);
  const r = await course(page, d1, 1);
  assert.ok(r, '手机上第一门课应可见');
  const c = mid(r);
  const beforeScroll = await page.evaluate(() => document.getElementById('gridFrame').scrollLeft);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: c.x, y: c.y }] });
  await sleep(320);                                   // 触屏长按 220ms
  const s = await state(page);
  assert.ok(s && s.active, '长按应拾起课程');
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove',
    touchPoints: [{ x: Math.min(388, c.x + 30), y: c.y + 30 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  const afterScroll = await page.evaluate(() => document.getElementById('gridFrame').scrollLeft);
  assert.equal(afterScroll, beforeScroll, '拖拽期间课表不应横滑');
  await sleep(300);                                    // 等回弹动画与感应带淡出结束
  assert.equal(await page.locator('.drag-ghost').count(), 0, '幽灵应已移除');
  await page.screenshot({ path: path.join(ARTIFACTS, 'mobile.png') });
}, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1 });

/* ---------- 17~19. 明暗主题：跟随系统 → 深色 → 浅色 ---------- */
await run('明暗主题：跟随系统 → 深色 → 浅色 → 跟随系统', async ({ page }) => {
  const mode = p => p.evaluate(() => document.documentElement.dataset.theme);
  const bg = p => p.evaluate(() => getComputedStyle(document.body).backgroundColor);
  assert.equal(await mode(page), 'auto', '默认应跟随系统');
  const before = await bg(page);
  await page.locator('#themeBtn').click();
  assert.equal(await mode(page), 'dark', '第一下应该直接给深色');
  assert.equal(await bg(page), 'rgb(21, 23, 19)', '深色背景');
  await sleep(320);                                // 等 .cell 的 220ms 背景过渡走完
  const cellBg = await page.evaluate(() =>
    getComputedStyle(document.querySelector('.cell')).backgroundColor);
  assert.equal(cellBg, 'rgb(29, 31, 26)', '格子也应切到深色 surface');
  await page.screenshot({ path: path.join(ARTIFACTS, 'desktop-dark.png') });
  await page.locator('#themeBtn').click();
  assert.equal(await mode(page), 'light', '第二下到强制浅色');
  assert.equal(await bg(page), 'rgb(232, 229, 225)', '浅色背景');
  await page.locator('#themeBtn').click();
  assert.equal(await mode(page), 'auto', '第三下回到跟随系统');
  assert.equal(await bg(page), before, '回到跟随系统应恢复系统背景');
});

await run('明暗主题：选择会记住、按钮不显眼', async ({ page }) => {
  const box = await page.locator('#themeBtn').boundingBox();
  assert.ok(box.width <= 28 && box.height <= 28, `按钮要小：${box.width}x${box.height}`);
  const op = await page.locator('#themeBtn').evaluate(el => Number(getComputedStyle(el).opacity));
  assert.ok(op <= 0.6, `按钮不该太显眼：opacity ${op}`);
  await page.locator('#themeBtn').click();          // → dark
  await page.reload();
  await page.waitForSelector('#grid .course');
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'dark',
    '刷新后应保持深色');
  assert.equal(await page.locator('#themeBtn').getAttribute('aria-label'),
    '主题：深色（点击切换）');
});

/* ---------- 20~24. 3D 档案架：滚轮切周 ---------- */
await run('3D：滚轮向下切到下一周', async ({ page }) => {
  const before = await week3d(page);
  assert.ok(before, '应能读到当前周次');
  await page.mouse.move(720, 450);
  await page.mouse.wheel(0, 120);
  await page.waitForFunction(b => {
    const m = /第\s*(\d+)\s*周/.exec(document.getElementById('slotName').textContent);
    return m && Number(m[1]) !== b;
  }, before, { timeout: 2000 });
  assert.equal(await week3d(page), before + 1, '向下滚一格应到下一周');
}, {}, '/docs/3d.html');

await run('3D：滚轮向上退回上一周', async ({ page }) => {
  await page.mouse.move(720, 450);
  await page.mouse.wheel(0, 120);
  await sleep(300);                              // 跨过 240ms 冷却
  const w1 = await week3d(page);
  await page.mouse.wheel(0, -120);
  await sleep(300);
  assert.equal(await week3d(page), w1 - 1, '向上滚一格应回上一周');
}, {}, '/docs/3d.html');

await run('3D：触控板惯性一次手势最多翻一周', async ({ page }) => {
  const before = await week3d(page);
  const seen = await page.evaluate(() => {
    window.__wheelSeen = 0;
    window.addEventListener('wheel', () => window.__wheelSeen++, { capture: true });
    /* 触控板惯性：一次手势连发多个小 wheel。这里用页面内派发而不是 page.mouse.wheel——
       这条用例验的是「累积阈值 + 冷却」的语义，不是指针链路；真鼠标事件在
       窗口被前一个 context 的窗口遮挡时会丢，跑起来时绿时红。 */
    for (let i = 0; i < 8; i++) {
      window.dispatchEvent(new WheelEvent('wheel', { deltaY: 40, bubbles: true, cancelable: true }));
    }
    return window.__wheelSeen;
  });
  assert.equal(seen, 8, '8 个 wheel 事件应全部送达');
  assert.equal(await week3d(page), before + 1,
    '一次手势只该翻一周（累积到 48 翻一格，240ms 冷却内不再翻）');
}, {}, '/docs/3d.html');

await run('3D：抽出课表纸后滚轮同样切周', async ({ page }) => {
  assert.match(await page.evaluate(() => document.body.className), /sheet-open/,
    '前置条件：应处于抽出课表纸的状态');
  const before = await week3d(page);
  await page.mouse.move(720, 450);
  await page.mouse.wheel(0, 120);
  await page.waitForFunction(b => {
    const m = /第\s*(\d+)\s*周/.exec(document.getElementById('slotName').textContent);
    return m && Number(m[1]) !== b;
  }, before, { timeout: 2000 });
  assert.equal(await week3d(page), before + 1, '纸面上滚轮也应切到下一周');
  assert.match(await page.locator('#wsFile').textContent(), /W-11/,
    '纸上的档案编号也要跟着换');
  assert.match(await page.evaluate(() => document.body.className), /sheet-open/,
    '切周后课表纸应保持展开');
  await page.screenshot({ path: path.join(ARTIFACTS, '3d-paper-after-wheel.png') });
}, {}, '/docs/3d.html?w=10');

await run('3D：保持自己的印刷配色，不引入 2D 主题按钮', async ({ page }) => {
  assert.equal(await page.locator('#themeBtn').count(), 0);
}, {}, '/docs/3d.html');

await browser.close();
server.close();

const failed = results.filter(r => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} 通过`);
if (failed.length) {
  console.log('失败用例：');
  failed.forEach(f => console.log(`  - ${f.name}: ${f.err}`));
  process.exit(1);
}
