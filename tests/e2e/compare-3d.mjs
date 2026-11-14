/**
 * 两个 3D 构建的视觉对比：同一视角、同一周、关掉动效后各截一张。
 *
 *   node compare-3d.mjs /tmp/before.html /tmp/after.html
 *
 * 用 file:// 直接开——单文件版本来就支持双击打开，不需要起服务。
 * 动效用 prefers-reduced-motion 关掉：idleBreath 吃时间参数，
 * 不关的话两张图必然不一样，diff 就没有意义了。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ARTIFACTS = path.join(HERE, 'artifacts');
fs.mkdirSync(ARTIFACTS, { recursive: true });

const [before, after] = process.argv.slice(2);
if (!before || !after) { console.error('用法: node compare-3d.mjs <before.html> <after.html>'); process.exit(1); }

const CANDIDATES = [
  process.env.EDGE_PATH,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
].filter(Boolean);
const exe = CANDIDATES.find(p => fs.existsSync(p));
if (!exe) { console.error('找不到 Edge/Chrome，可用 EDGE_PATH 指定'); process.exit(1); }

const browser = await chromium.launch({
  executablePath: exe,
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--disable-gpu-sandbox'],
});

async function shot(file, out, query) {
  const page = await browser.newPage({
    viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1, reducedMotion: 'reduce',
  });
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  await page.goto('file:///' + file.replace(/\\/g, '/') + query, { waitUntil: 'load' });
  await page.waitForFunction('window.__sceneReady === true', { timeout: 20000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: out });
  /* 老构建没有探针，量不到就算了；这个脚本只负责出图 */
  const stats = await page.evaluate(
    'typeof window.__stats === "function" ? window.__stats() : null');
  await page.close();
  return { stats, errs };
}

const racks = '?still=1&reduce=1';
const b = await shot(before, path.join(ARTIFACTS, 'before.png'), racks);
const a = await shot(after, path.join(ARTIFACTS, 'after.png'), racks);
/* 详情态：档案被抽出、其余压暗，走的是另一条透明度分支 */
const detail = '?still=1&w=11';
const bd = await shot(before, path.join(ARTIFACTS, 'before-detail.png'), detail);
const ad = await shot(after, path.join(ARTIFACTS, 'after-detail.png'), detail);
console.log(JSON.stringify({
  rackCalls: { before: b.stats && b.stats.calls, after: a.stats && a.stats.calls },
  detailCalls: { before: bd.stats && bd.stats.calls, after: ad.stats && ad.stats.calls },
  errs: [...b.errs, ...a.errs, ...bd.errs, ...ad.errs],
}));
await browser.close();
