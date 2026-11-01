// 把 scene.js 连同 three 一起打成 IIFE，再塞进 shell.html，产出单个自包含的 3d.html。
// 为什么要打包：three 从 r160 起不再提供 UMD 构建，只用 ES module；
// 而 file:// 下 import 会被 CORS 拦掉，所以必须合成一个普通脚本。
import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, '..', 'docs', '3d.html');

const res = await build({
  entryPoints: [join(here, 'scene.js')],
  bundle: true,
  format: 'iife',
  minify: true,
  target: ['chrome100', 'safari15'],
  legalComments: 'none',
  write: false,
});

const code = res.outputFiles[0].text;

// 课表数据在构建时注入：场景里只做渲染，不在运行时 fetch，file:// 才能直接用。
const dataPath = join(here, '..', 'config', 'demo-courses.json');
const raw = JSON.parse(await readFile(dataPath, 'utf8'));
const courses = (raw.courses || []).map(c => ({
  name: c.name, teacher: c.teacher || '', room: c.room || '',
  location: c.location || '', day: c.day,
  startPeriod: c.startPeriod, endPeriod: c.endPeriod,
  weeks: c.weeks || [], weekType: c.weekType || 'all',
}));

// 学期起点与总周数：3D 场景靠它们算「本周是第几周」和建几个槽位。
// 漏了这两个字段时 new Date("undefinedT00:00:00") 会得到 Invalid Date，
// 一路算成 NaN，于是 slots[NaN] === undefined，覆盖层和引线静默失效——
// 而模板里的静态默认文案（第 09 周 / WEEK 09）会假装一切正常。
// 所以这里宁可构建失败，也不产出一个"看起来对"的坏文件。
const start = raw.meta && raw.meta.semesterStart;
if (!/^\d{4}-\d{2}-\d{2}$/.test(String(start || ''))) {
  throw new Error('config 里的 meta.semesterStart 缺失或格式不对：' + start);
}
const allWeeks = courses.flatMap(c => c.weeks || []);
const maxWeek = allWeeks.length ? Math.max(...allWeeks) : 0;
if (!(maxWeek > 0)) {
  throw new Error('课程里没有任何 weeks 数据，无法确定总周数');
}

const payload = {
  meta: raw.meta || {},
  courses,
  start,
  maxWeek,
  periodTimes: {},
};
// 作息表从 config/timetable.json 读，没有就用默认
try {
  Object.assign(payload.periodTimes,
    JSON.parse(await readFile(join(here, '..', 'config', 'timetable.json'), 'utf8')));
} catch { /* 用前端兜底 */ }

const shell = await readFile(join(here, 'shell.html'), 'utf8');
const html = shell
  .replace('/*__DATA__*/null', () => JSON.stringify(payload))
  .replace('/*__BUNDLE__*/', () => code);

await mkdir(dirname(out), { recursive: true });
await writeFile(out, html, 'utf8');
console.log(`已生成 ${out}  ${(Buffer.byteLength(html) / 1024).toFixed(0)} KB`
  + `  · ${courses.length} 个时段 · 起点 ${start} · ${maxWeek} 周`);
