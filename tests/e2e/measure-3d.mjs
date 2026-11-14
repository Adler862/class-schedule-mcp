/**
 * 3D 档案架性能探针：量 draw call / 纹理内存 / 网格数，并出两张截图。
 *
 *   node measure-3d.mjs            量当前 docs/3d.html
 *   node measure-3d.mjs --shot     顺便存截图到 artifacts/3d-before.png
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const ARTIFACTS = path.join(HERE, 'artifacts');
fs.mkdirSync(ARTIFACTS, { recursive: true });

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript',
               '.css': 'text/css', '.json': 'application/json', '.png': 'image/png',
               '.glb': 'model/gltf-binary' };

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
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const errs = [];
page.on('pageerror', e => errs.push(String(e)));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

/* --page 可指定仓库内的另一个产物，例如 --page dist/我的课表3d.html */
const pageArg = (() => {
  const i = process.argv.indexOf('--page');
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1].replace(/^\/+/, '') : 'docs/3d.html';
})();
await page.goto(`${BASE}/${encodeURI(pageArg)}`, { waitUntil: 'load' });
await page.waitForFunction('window.__sceneReady === true', { timeout: 20000 });
await page.waitForTimeout(1200);

const rack = await page.evaluate('window.__stats()');
const title = await page.title();
if (process.argv.includes('--shot')) {
  await page.screenshot({ path: path.join(ARTIFACTS, '3d-rack.png') });
}

// 抽出一份档案（详情态），再量一次：这一刻会生成/显示高清课表纸
await page.mouse.move(720, 450);
await page.waitForTimeout(300);
await page.mouse.click(720, 450);
await page.waitForTimeout(1200);
const detail = await page.evaluate('window.__stats()');
if (process.argv.includes('--shot')) {
  await page.screenshot({ path: path.join(ARTIFACTS, '3d-detail.png') });
}

console.log(JSON.stringify({ title, rack, detail, errors: errs.slice(0, 3) }, null, 2));
await browser.close();
server.close();
