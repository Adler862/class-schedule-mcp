// 把 scene.js 连同 three 一起打成 IIFE，再塞进 shell.html，产出单个自包含的 3d.html。
// 为什么要打包：three 从 r160 起不再提供 UMD 构建，只用 ES module；
// 而 file:// 下 import 会被 CORS 拦掉，所以必须合成一个普通脚本。
import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

/* --courses / --out 用来给自己导出的课表单独出一份：
     node build.mjs --courses ../output/mine.json --out ../dist/我的课表3d.html
   不带参数时维持原行为（读演示数据、写 docs/3d.html），单测与 Pages 都不受影响。 */
function argOf(name, fallback) {
  const i = process.argv.indexOf(name);
  return i > 0 && process.argv[i + 1] ? resolve(process.argv[i + 1]) : fallback;
}
const DATA_PATH = argOf('--courses', join(here, '..', 'config', 'demo-courses.json'));
const OUT = argOf('--out', join(here, '..', 'docs', '3d.html'));

/* 详情态那个「完整学期表格」按钮指向谁。默认 index.html（Pages 布局）；
   自己导出的个人页如果叫别的名字（dist/我的课表.html），用 --index 指过去，
   否则点进去就是 404。这个值是 href，不能走 resolve。 */
const indexHref = (() => {
  const i = process.argv.indexOf('--index');
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : 'index.html';
})();

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
const raw = JSON.parse(await readFile(DATA_PATH, 'utf8'));
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
  indexHref,
  courses,
  start,
  maxWeek,
  // 作息表：面板要显示「08:30」这种时刻，而课程数据里只有节次。
  // 与 src/semester.py 的 DEFAULT_PERIOD_TIMES 保持一致，config/timetable.json 可覆盖。
  periodTimes: {
    1: '08:30', 2: '09:25', 3: '10:30', 4: '11:25',
    5: '14:30', 6: '15:25', 7: '16:30', 8: '17:25',
    9: '19:00', 10: '19:55', 11: '21:00', 12: '21:55',
  },
};
// 作息表从 config/timetable.json 读，没有就用默认
try {
  Object.assign(payload.periodTimes,
    JSON.parse(await readFile(join(here, '..', 'config', 'timetable.json'), 'utf8')));
} catch { /* 用前端兜底 */ }

/* Blender 出的档案板：内嵌成 base64 塞进 DATA。
   file:// 下没法 fetch，单文件发布也不能多带一个 .glb。 */
let glbB64 = '';
try {
  const glb = await readFile(join(here, '..', 'art', 'archive-board-v2.glb'));
  glbB64 = glb.toString('base64');
} catch { /* 没有 GLB 就退回程序化的盒子 */ }
payload.glb = glbB64;
/* body 已经在 Blender 里拆成"侧面 / 脊面"两个材质槽，
   接进 three 时用 [side, face] 两个材质，脊面那排 NO.xx 保得住。 */
payload.useGlb = true;

const shell = await readFile(join(here, 'shell.html'), 'utf8');
const html = shell
  .replace('/*__DATA__*/null', () => JSON.stringify(payload))
  .replace('/*__BUNDLE__*/', () => code);

/* --check：只重构建一次并与现有产物逐字比对，不写文件。
   单测用它锁住「改了 scene.js / shell.html / config 忘了重建」。 */
if (process.argv.includes('--check')) {
  let current = '';
  try { current = await readFile(OUT, 'utf8'); } catch { /* 产物还不存在 */ }
  if (current !== html) {
    console.error(`STALE: ${OUT} 与源码/配置不一致，请运行 npm run build`);
    process.exit(1);
  }
  console.log(`OK: ${OUT} 与源码一致`);
} else {
  await mkdir(dirname(OUT), { recursive: true });
  await writeFile(OUT, html, 'utf8');
  console.log(`已生成 ${OUT}  ${(Buffer.byteLength(html) / 1024).toFixed(0)} KB`
    + `  · ${courses.length} 个时段 · 起点 ${start} · ${maxWeek} 周`);
}
