/* 课程档案架：一列列立着的薄片，一本 = 一周。
   选中那本从架上抽出来、转正、停到画面左侧，右侧浮出这一周的课表。 */
import * as THREE from 'three';

const DATA = window.DATA || { courses: [], maxWeek: 17, start: '2026-08-31' };
/* 参考图里的脊不是"书"，是**极长的长条板**：脊背很窄（W）、高度中等（H）、
   深度方向延伸出去很远（T）。一排平行铺开，靠透视形成"一片"的观感。
   之前 T=0.32 做成的是"书"，怎么调角度都不像。 */
const W = 0.17, H = 1.30, T = 8.0;
const GAP_X = 0.245;
const LIFT = 1.15;

/* 抽出后的状态：往前拉、转正、缩小、停在左侧 */
const EX = {
  pull: 5.0,        // 沿 +z 拉到排面之前，转的时候才不会扫到邻居
  y: 1.62,          // 抽出后的中心高度（大致对准画面中线）
  scale: 0.46,
  tilt: 0.26,       // 转过 90° 后再偏一点，露出厚度，不然像一张纯平面
};

if (/[?&]still=1/.test(location.search)) document.body.classList.add('still');

const canvas = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
/* 长焦，不是广角。
   去读 RhineLabUI 的 scene.ts 才发现的：它用 `PerspectiveCamera(34, …)` 但把
   **fov 压到 6.15**、相机拉到 84 个单位外。长焦把透视压平，一排脊才会看起来
   "平行"，只在远处轻微收敛——那正是参考图的味道。 */
const camera = new THREE.PerspectiveCamera(8.4, 1, 0.1, 200);
camera.position.set(-15.6, 5.4, 27.4);
camera.lookAt(0.35, 0.95, -1.2);

scene.add(new THREE.HemisphereLight(0xffffff, 0xd9d4cb, 2.1));
const key = new THREE.DirectionalLight(0xfffdf8, 2.2);
key.position.set(-5, 9, 7);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.left = -8; key.shadow.camera.right = 8;
key.shadow.camera.top = 8; key.shadow.camera.bottom = -8;
key.shadow.camera.near = 1; key.shadow.camera.far = 32;
key.shadow.bias = -0.0006;
scene.add(key);
const fill = new THREE.DirectionalLight(0xffffff, 0.5);
fill.position.set(6, 4, -8);
scene.add(fill);

/* 地面：只接收阴影，不显形，让脊有落影 */
const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(40, 40),
  new THREE.ShadowMaterial({ opacity: 0.045 })
);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

const group = new THREE.Group();
group.rotation.y = -0.24;
scene.add(group);

const start = new Date(String(DATA.start) + 'T00:00:00');
const maxWeek = DATA.maxWeek || 17;

function weekCourses(w) {
  return (DATA.courses || []).filter(c => (c.weeks || []).indexOf(w) >= 0);
}
function currentWeek() {
  const diff = Math.floor((Date.now() - start.getTime()) / 86400000 / 7) + 1;
  return Math.max(1, Math.min(maxWeek, diff));
}
function isoOf(w, day) {
  return new Date(start.getTime() + ((w - 1) * 7 + day - 1) * 86400000);
}
function pad2(n) { return (n < 10 ? '0' : '') + n; }
function rangeOf(w) {
  const a = isoOf(w, 1), b = isoOf(w, 7);
  const f = d => pad2(d.getMonth() + 1) + '/' + pad2(d.getDate());
  return f(a) + ' – ' + f(b);
}
function cnRange(w) {
  const a = isoOf(w, 1), b = isoOf(w, 7);
  return (a.getMonth() + 1) + '月' + a.getDate() + '日 — ' + (b.getMonth() + 1) + '月' + b.getDate() + '日';
}
/* 星期与配色要早于建模：档案表面的印刷内容在构建时就要用到。 */
const DAY_NAMES = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const DAY_SHORT = ['', '一', '二', '三', '四', '五', '六', '日'];

/* 课程配色：按课程名首次出现顺序发号，同一门课整学期同色。 */
const PALETTE = [212, 350, 127, 264, 42, 180, 317, 95];
const HUE_OF = (() => {
  const m = {};
  let n = 0;
  for (const c of (DATA.courses || [])) {
    if (c.name && !(c.name in m)) m[c.name] = n++;
  }
  return m;
})();
function colorOf(name) {
  const h = PALETTE[(HUE_OF[name] || 0) % PALETTE.length];
  return 'hsl(' + h + ' 38% 52%)';
}

const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* 脊面编号：Canvas 现画竖排小字 NO.09，不用任何外部字体。
   参考图里每根脊的窄面都印着编号，字很小很淡——那是"档案"这个概念的锚点。 */
function makeNoTexture(n) {
  const cw = 48, ch = 400;
  const cv = document.createElement('canvas');
  cv.width = cw;
  cv.height = ch;
  const g = cv.getContext('2d');
  g.fillStyle = '#f7f5f0';
  g.fillRect(0, 0, cw, ch);
  const text = 'NO.' + String(n).padStart(2, '0');
  const chars = text.split('');
  /* 编号只占脊面上方一小段（参考图里约 1/8 脊高），不是铺满整根。 */
  const step = 8;
  const top = 40;
  g.font = '500 7.5px "Helvetica Neue", Arial, sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillStyle = '#8f8a80';
  chars.forEach((c, i) => g.fillText(c, cw / 2, top + step * i));
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

const bodyGeo = new THREE.BoxGeometry(W, H, T);
const capGeo = new THREE.BoxGeometry(W * 0.82, 0.022, T * 0.82);
const labelGeo = new THREE.PlaneGeometry(T, H);

/* 长侧面的标签：档案正对观者时才看得见。
   没有它，抽出来的就是一块空白板——脊上那点 NO.xx 是印在窄端的，
   一转身就背过去了。 */
function makeLabelTexture(w) {
  /* 直接印在档案surface上的周课表：左栏是档案号，右侧 7 列就是这一周。
     它不是给"读"的（那么小的字本来也读不动），是让抽出来的东西
     真的像一份写着内容的档案，而不是一块空白板。 */
  const cw = 2048, ch = 336;
  const cv = document.createElement('canvas');
  cv.width = cw; cv.height = ch;
  const g = cv.getContext('2d');
  const SANS = '"Helvetica Neue", Arial, sans-serif';
  g.fillStyle = '#f8f6f1';
  g.fillRect(0, 0, cw, ch);

  g.strokeStyle = '#d8d2c5';
  g.lineWidth = 2;
  const hline = (y) => { g.beginPath(); g.moveTo(0, y); g.lineTo(cw, y); g.stroke(); };
  const vline = (x, a, b) => { g.beginPath(); g.moveTo(x, a); g.lineTo(x, b); g.stroke(); };
  hline(30); hline(ch - 31); vline(320, 30, ch - 31);

  g.textBaseline = 'middle';
  g.textAlign = 'left';
  g.fillStyle = '#9a9487';
  g.font = '500 22px ' + SANS;
  g.fillText('COURSE ARCHIVE', 40, 84);
  g.fillText('TIMETABLE / WEEK', 40, 116);
  g.fillStyle = '#151713';
  g.font = '600 46px ' + SANS;
  g.fillText('NO.' + pad2(w), 40, 178);
  g.fillStyle = '#8b8578';
  g.font = '500 19px ' + SANS;
  const list = weekCourses(w);
  const secs = list.reduce((n, c) => n + (c.endPeriod - c.startPeriod + 1), 0);
  g.fillText('WEEK ' + pad2(w) + ' · ' + new Set(list.map(c => c.name)).size
    + ' 门课 · ' + secs + ' 节', 40, 240);
  g.fillText(cnRange(w), 40, 272);

  /* 7 列星期 */
  const x0 = 320, colW = (cw - x0) / 7;
  const top = 30, bot = ch - 31;
  for (let d = 1; d <= 7; d++) {
    const x = x0 + (d - 1) * colW;
    if (d > 1) vline(x, top, bot);
    const dt = isoOf(w, d);
    g.textAlign = 'left';
    g.fillStyle = '#151713';
    g.font = '500 27px ' + SANS;
    g.fillText(DAY_NAMES[d], x + 20, 82);
    g.fillStyle = '#a8a294';
    g.font = '400 19px ' + SANS;
    g.fillText(pad2(dt.getMonth() + 1) + '/' + pad2(dt.getDate()), x + 20, 112);
    hline0(g, x + 20, x + colW - 20, 134);

    const ofDay = list.filter(c => c.day === d).sort((a, b) => a.startPeriod - b.startPeriod);
    ofDay.slice(0, 4).forEach((c, i) => {
      const y = 168 + i * 42;
      g.fillStyle = colorOf(c.name);
      g.fillRect(x + 20, y - 13, 5, 28);
      const t0 = (DATA.periodTimes && DATA.periodTimes[c.startPeriod]) || '';
      g.fillStyle = '#a8a294';
      g.font = '400 16px ' + SANS;
      g.fillText(t0, x + 38, y - 9);
      g.fillStyle = '#2b2c25';
      g.font = '400 23px ' + SANS;
      g.fillText(c.name.length > 7 ? c.name.slice(0, 7) : c.name, x + 38, y + 14);
    });
    if (ofDay.length > 4) {
      g.fillStyle = '#a8a294';
      g.font = '400 16px ' + SANS;
      g.fillText('+' + (ofDay.length - 4), x + 20, 168 + 4 * 42 - 8);
    }
  }

  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}
function hline0(g, a, b, y) {
  g.strokeStyle = '#e2ded7';
  g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(a, y); g.lineTo(b, y); g.stroke();
  g.strokeStyle = '#d8d2c5';
  g.lineWidth = 2;
}

const labelTex = new Map();
function labelMaterial(w) {
  if (!labelTex.has(w)) labelTex.set(w, makeLabelTexture(w));
  return new THREE.MeshStandardMaterial({
    map: labelTex.get(w), roughness: 0.94, metalness: 0,
    transparent: true, opacity: 0,
  });
}

/* ================= 循环阵列 =================
   以前是"17 根真柱 + 一堆装饰柱 + 几排复制品"，只有前排那 17 根能点、能动。
   现在整条是一个**循环轨道**：PERIOD 周为一圈，拼 COPIES 份铺满画面，
   回卷点落在视口之外，所以看不出接缝。
   每一列都参与拾取、都跟着选择连续滑动；周次走到头自动绕回第 1 周。 */
const PERIOD = Math.max(1, maxWeek);
const COPIES = 3;
const RAIL_N = PERIOD * COPIES;
const ROWS = 4;                       // 纵深 4 排，负责把画面下半/上半填满
const RAIL_MID = (RAIL_N - 1) / 2;

const rails = [];
const pickables = [];
const weekMats = new Map();

/* 确定性伪随机：同一个下标永远同一个值，不引入 Math.random，
   否则每次刷新高度都会变，调好的构图就白调了。 */
function pseudo(n) {
  const x = Math.sin(n * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

function matSet(w) {
  if (weekMats.has(w)) return weekMats.get(w);
  const list = weekCourses(w);
  const busy = list.length > 0;
  const op = busy ? 1 : 0.82;
  /* 完全不透明时必须关掉 transparent。否则它仍走透明渲染队列，
     按距离排序而不是深度测试，前面这几根就会"透"出后面的脊，像塑料壳。
     材质是按周共享的，所以这三个开关在创建时定死就行。 */
  const tflag = op < 0.999;
  const dflag = op > 0.96;
  const side = new THREE.MeshStandardMaterial({
    color: 0xe9e5dc, roughness: 0.88, metalness: 0,
    transparent: tflag, depthWrite: dflag, opacity: op
  });
  const face = new THREE.MeshStandardMaterial({
    color: 0xffffff, roughness: 0.9, metalness: 0,
    transparent: tflag, depthWrite: dflag, opacity: op,
    map: makeNoTexture(w),
  });
  const top = new THREE.MeshStandardMaterial({
    color: 0xfbf9f4, roughness: 0.9, metalness: 0,
    transparent: tflag, depthWrite: dflag, opacity: op
  });
  /* 脊顶色标：课程越多越深，饱和度压到 20% 左右 */
  const hue = [212, 350, 127, 264, 42, 180, 317, 95][w % 8];
  const light = busy ? Math.max(34, 62 - list.length * 4) : 70;
  const cap = new THREE.MeshStandardMaterial({
    color: new THREE.Color(`hsl(${hue} 20% ${light}%)`),
    roughness: 0.8, metalness: 0, transparent: true, opacity: busy ? 1 : 0.35
  });
  const set = { side, face, top, cap, busy, hRatio: busy ? 1 : 0.62 };
  weekMats.set(w, set);
  return set;
}

for (let c = 0; c < RAIL_N; c++) {
  const w = (c % PERIOD) + 1;
  const m = matSet(w);
  /* 同一周在轨道上会出现三次，高度给一点确定性微差，
     否则 17 列一个循环的重复感一眼就能看出来。 */
  const jit = 0.982 + pseudo(c * 7 + 3) * 0.036;
  const rail = {
    col: c, week: w, x: 0, busy: m.busy,
    baseY: (H * m.hRatio * jit) / 2,
    holders: [], body: null, cap: null,
    lift: 0, ex: 0, spring: { value: 0, velocity: 0 },
  };
  for (let r = 0; r < ROWS; r++) {
    const body = new THREE.Mesh(bodyGeo, [m.side, m.side, m.top, m.side, m.face, m.side]);
    body.castShadow = r === 0;
    body.receiveShadow = true;
    body.scale.y = m.hRatio * jit;

    const holder = new THREE.Group();
    holder.position.set(0, rail.baseY, -r * T);
    holder.add(body);

    const cap = new THREE.Mesh(capGeo, m.cap);
    cap.position.set(0, H / 2 + 0.012, 0);
    cap.castShadow = r === 0;
    body.add(cap);

    group.add(holder);
    rail.holders.push(holder);
    if (r === 0) {
      /* 长侧面标签贴在 +x 面上：架子上看是极薄的一条边（等于看不见），
         抽出来转正之后才整个露出来。 */
      const labelMat = labelMaterial(w);
      const label = new THREE.Mesh(labelGeo, labelMat);
      label.position.set(W / 2 + 0.002, 0, 0);
      label.rotation.y = Math.PI / 2;
      label.visible = false;
      body.add(label);
      rail.label = label;
      rail.labelMat = labelMat;
      rail.body = body;
      pickables.push(body);
      body.userData.rail = rail;
    }
  }
  rails.push(rail);
}

/* ---------- 动效 ----------
   借自 RhineLabUI 的 motion.ts（MIT）。核心不是"更顺滑的缓动"，而是：
   选中一根时，**相邻的也跟着动一下再平息**。只有选中那根在动，整排看上去就是静态图。 */
const smooth = t => {
  t = Math.max(0, Math.min(1, t));
  return t * t * t * (10 + t * (-15 + 6 * t));
};
const bell = (x, width) => Math.exp(-0.5 * (x / width) ** 2);
const clamp01 = t => t < 0 ? 0 : (t > 1 ? 1 : t);

/* 带速度的二阶阻尼。注意它**不会过冲**，它比一阶强的地方是启动/收尾带惯性。 */
function springDamp(s, target, rate, dt) {
  const delta = s.value - target;
  const impulse = s.velocity + rate * delta;
  const decay = Math.exp(-rate * dt);
  s.value = target + (delta + impulse * dt) * decay;
  s.velocity = (s.velocity - rate * impulse * dt) * decay;
}

/* 邻脊被"带起来"的幅度：按距离延迟 + 衰减振荡，像手指扫过一排档案。 */
function neighborWave(distance, age) {
  const t = age - Math.abs(distance) * 0.05;
  if (t <= 0 || t > 2.4) return 0;
  const env = smooth(t / 0.12) * Math.exp(-t * 1.9);
  return (env * Math.cos(t * 7.4)) / (1 + Math.abs(distance) * 0.55);
}

/* 空闲呼吸：两个不同周期的正弦叠加，相邻脊错相，肉眼看不出但整架是活的 */
function idleBreath(i, time) {
  return 0.0055 * Math.sin(time * 0.85 + i * 0.42)
       + 0.0026 * Math.sin(time * 0.61 - i * 0.29);
}

/* 无界序列里挑离 center 最近的那一次出现（RhineLabUI archive-loop.ts，MIT） */
function nearestOccurrence(value, center, period) {
  return value + Math.floor((center - value + period / 2) / period) * period;
}

let selectedAt = 0;                 // 上次选中的时刻，用来算波纹年龄
let selected = Math.max(0, Math.min(PERIOD - 1, currentWeek() - 1));
/* 面板状态要在这里声明：select() 会读它，而 select 定义在上面。 */
let sheetOpen = false;
let lastSheetWeek = 0;
let focusRail = null;

/* 轨道位置（列单位，带小数）——缓动到 selected，所以柱子是连续滑过去的 */
let railScroll = 0;
/* 焦点横坐标：关着时居中，打开时左移，整条轨道跟着让位。 */
const FOCUS_CLOSED = 0.30, FOCUS_OPEN = -2.28;
let focusX = FOCUS_CLOSED;

/* ---------- 交互 ---------- */
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();

function pick(ev) {
  const r = canvas.getBoundingClientRect();
  ndc.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
  ndc.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
  ray.setFromCamera(ndc, camera);
  const hit = ray.intersectObjects(pickables, false)[0];
  return hit ? hit.object.userData.rail : null;
}

canvas.addEventListener('pointermove', (ev) => {
  if (ev.pointerType === 'touch') return;
  canvas.style.cursor = pick(ev) ? 'pointer' : 'default';
});
canvas.addEventListener('pointerleave', () => { canvas.style.cursor = 'default'; });
canvas.addEventListener('click', (ev) => {
  const r = pick(ev);
  if (!r) return;
  const i = r.week - 1;
  /* 左键点脊就直接打开课表。点的是当前已经打开的那一根 → 收起。 */
  if (sheetOpen && i === selected) { closeWeekSheet(); return; }
  select(i);
  if (!sheetOpen) openWeekSheet(r.week);
});

/* 首尾循环：17 周点 → 回到第 1 周，1 周点 ← 回到第 17 周。
   轨道本身是环形的，所以这里不需要任何特殊处理，绕回去就是接着滑一格。 */
function select(i) {
  const next = ((i % PERIOD) + PERIOD) % PERIOD;
  if (next !== selected) selectedAt = performance.now() / 1000;
  selected = next;
  paintOverlay();
  /* 面板开着时切周，内容必须跟着换——否则引线指向第 10 周、面板还是第 9 周。 */
  const nextWeek = next + 1;
  if (sheetOpen && nextWeek !== lastSheetWeek) openWeekSheet(nextWeek);
}

addEventListener('keydown', (ev) => {
  const k = ev.key;
  if (k === 'ArrowRight') { select(selected + 1); ev.preventDefault(); }
  else if (k === 'ArrowLeft') { select(selected - 1); ev.preventDefault(); }
  else if (k === 'ArrowDown') { select(selected + 4); ev.preventDefault(); }
  else if (k === 'ArrowUp') { select(selected - 4); ev.preventDefault(); }
  else if (k === 'Home') { select(currentWeek() - 1); ev.preventDefault(); }
});

/* ---------- 覆盖层 ----------
   每次用的时候现取元素：脚本可能在覆盖层解析完成前就跑到这里，
   缓存下来的引用会一直是 null。 */
const E = (id) => document.getElementById(id);

function setText(id, txt) {
  const n = E(id);
  if (n) n.textContent = txt;
}

function paintOverlay() {
  const week = selected + 1;
  const list = weekCourses(week);
  setText('idx', '(' + maxWeek + ')');
  setText('bigNum', pad2(week));
  setText('totalNum', '/ ' + pad2(maxWeek));
  setText('colNum', pad2(week));
  setText('colTotal', '/ ' + pad2(maxWeek));
  setText('slotName', '第 ' + week + ' 周 · ' + rangeOf(week));
  setText('callWeek', 'WEEK ' + pad2(week));
  const names = new Set(list.map(c => c.name));
  setText('callRange', rangeOf(week) + ' · ' + names.size + ' 门课 / ' + list.length + ' 节');
}

/* ---------- 周档案页签 ---------- */
/* 「学年学期：2026-2027-1    班级：…    专业：…」按两个以上空格切成键值 */
function semesterInfo() {
  const s = String((DATA.meta && DATA.meta.semester) || '');
  const out = {};
  s.split(/\s{2,}/).forEach(part => {
    const i = part.indexOf('：');
    if (i > 0) out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  });
  return out;
}

let activeTab = 'grid';
let paneAnims = [];

function revealPane(swap) {
  if (reduce) return;
  const pin = E('wsPin');
  if (!pin) return;
  paneAnims.forEach(a => { try { a.cancel(); } catch (e) { /* 已结束 */ } });
  paneAnims = [];
  const rows = pin.querySelectorAll(
    ':scope > .kicker, :scope > h2, :scope > .cnline, :scope > .rule,'
    + ' :scope > .meta > div, :scope > .tabs, :scope > .acts, :scope > .fnote,'
    + ' .tbody .cc, .tbody .clist > li, .tbody .stat > div'
  );
  const step = swap ? 9 : 26;
  const dur = swap ? 300 : 520;
  rows.forEach((el, i) => {
    const delay = Math.min(i * step, 420);
    const frames = el.classList.contains('rule')
      ? [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }]
      : [{ opacity: 0, transform: 'translateY(13px)' }, { opacity: 1, transform: 'none' }];
    paneAnims.push(el.animate(frames, {
      duration: dur, delay: swap ? delay : delay + 40, easing: 'cubic-bezier(.22,1,.36,1)',
      fill: 'both',
    }));
  });
}

function setTab(name) {
  activeTab = name;
  const tabs = E('wsTabs');
  if (!tabs) return;
  const btns = tabs.querySelectorAll('[data-tab]');
  let activeBtn = null;
  btns.forEach(b => {
    const on = b.dataset.tab === name;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', String(on));
    if (on) activeBtn = b;
  });
  const ind = tabs.querySelector('.ind');
  if (ind && activeBtn) {
    ind.style.transform = 'translateX(' + activeBtn.offsetLeft + 'px) scaleX('
      + Math.max(1, activeBtn.offsetWidth) + ')';
  }
  document.querySelectorAll('.tabp').forEach(p => p.classList.toggle('on', p.dataset.p === name));
}

function renderGrid(week, list) {
  const host = E('wsGrid');
  const todayIso = (() => {
    const d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  })();
  let h = '<div class="tgrid">';
  /* 所有格子都显式指定行列。课程块是显式定位的，自动流会跳过被占住的格子。 */
  h += '<div class="th blank" style="grid-column:1;grid-row:1"></div>';
  for (let d = 1; d <= 7; d++) {
    const dt = isoOf(week, d);
    const iso = dt.getFullYear() + '-' + pad2(dt.getMonth() + 1) + '-' + pad2(dt.getDate());
    h += '<div class="th' + (iso === todayIso ? ' today' : '') + '" style="grid-column:' + (d + 1)
      + ';grid-row:1">' + DAY_NAMES[d]
      + '<em>' + pad2(dt.getMonth() + 1) + '/' + pad2(dt.getDate()) + '</em></div>';
  }
  for (let r = 1; r <= 6; r++) {
    const sp = (r - 1) * 2 + 1;
    const t = (DATA.periodTimes && DATA.periodTimes[sp]) || '';
    h += '<div class="gt" style="grid-column:1;grid-row:' + (r + 1) + '">'
      + '<b>' + sp + '-' + (sp + 1) + '</b><span>' + t + '</span></div>';
    for (let d = 1; d <= 7; d++) {
      const dt = isoOf(week, d);
      const iso = dt.getFullYear() + '-' + pad2(dt.getMonth() + 1) + '-' + pad2(dt.getDate());
      h += '<div class="cell' + (iso === todayIso ? ' today' : '') + '" style="grid-column:'
        + (d + 1) + ';grid-row:' + (r + 1) + '"></div>';
    }
  }
  let idx = 0;
  for (const c of list) {
    const r1 = Math.ceil(c.startPeriod / 2);
    const r2 = Math.ceil(c.endPeriod / 2);
    if (r1 < 1 || r1 > 6) continue;
    const span = Math.max(1, Math.min(r2 - r1 + 1, 7 - r1));
    const where = c.room || c.location || '';
    const t0 = (DATA.periodTimes && DATA.periodTimes[c.startPeriod]) || '';
    const t1 = (DATA.periodTimes && DATA.periodTimes[c.endPeriod + 1]) || '';
    h += '<div class="cc" style="grid-column:' + (c.day + 1)
      + ';grid-row:' + (r1 + 1) + ' / span ' + span
      + ';--c:' + colorOf(c.name) + ';--i:' + (idx++) + '">'
      + '<b>' + esc(c.name) + '</b>'
      + '<i>' + esc(where) + '</i>'
      + (t0 ? '<u>' + t0 + (t1 ? '–' + t1 : '') + '</u>' : '')
      + '</div>';
  }
  h += '</div>';
  /* 空周也照常画表格：空着的七列六行本身就是信息——"这一周确实没有课"，
     比一句提示更接近课表的样子。 */
  host.innerHTML = (list.length ? '' : '<div class="tempty">本周无排课 · 空档案</div>') + h;
}

function renderList(list) {
  const host = E('wsList');
  if (!list.length) { host.innerHTML = '<li><div class="t">—</div><div class="n"><b>这一周没有排课</b></div></li>'; return; }
  host.innerHTML = list.map(c => {
    const t0 = (DATA.periodTimes && DATA.periodTimes[c.startPeriod]) || '';
    const t1 = (DATA.periodTimes && DATA.periodTimes[c.endPeriod + 1]) || '';
    return '<li><i class="bar" style="--c:' + colorOf(c.name) + '"></i>'
      + '<div class="t">' + (c.startPeriod) + '-' + (c.endPeriod)
      + (t0 ? '<br>' + t0 : '') + '</div>'
      + '<div class="n"><b>' + esc(c.name) + '</b><span>' + esc(c.room || c.location || '')
      + (t1 ? ' · 至 ' + t1 : '') + '</span></div>'
      + '<div class="d">周' + DAY_SHORT[c.day] + '</div></li>';
  }).join('');
}

function renderStat(week, list) {
  const host = E('wsStat');
  if (!list.length) {
    host.innerHTML = '<div class="statp">这一周没有排课，档案架上这一格是空的。</div>';
    return;
  }
  const per = [0, 0, 0, 0, 0, 0, 0];
  let secs = 0;
  for (const c of list) {
    const n = c.endPeriod - c.startPeriod + 1;
    per[c.day - 1] += n;
    secs += n;
  }
  const names = new Set(list.map(c => c.name));
  const days = per.filter(n => n > 0).length;
  const max = Math.max(1, ...per);
  let busiest = 1;
  per.forEach((n, i) => { if (n > per[busiest - 1]) busiest = i + 1; });

  const bars = per.map((n, i) =>
    '<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end">'
    + '<i style="flex:none;height:' + Math.round(n / max * 40) + 'px;'
    + 'background:' + (n ? '#8b8f75' : '#e2ded7') + '"></i>'
    + '<em style="margin-top:5px">' + DAY_SHORT[i + 1] + '</em></div>'
  ).join('');

  host.innerHTML =
    '<div class="stat">'
    + '<div><span>COURSES / 门课</span><b>' + names.size + '</b></div>'
    + '<div><span>SECTIONS / 节数</span><b>' + secs + '</b></div>'
    + '<div><span>ACTIVE DAYS / 有用课天</span><b>' + days + '<s>/ 7</s></b></div>'
    + '<div><span>BUSIEST / 最满</span><b>周' + DAY_SHORT[busiest] + '<s>' + per[busiest - 1] + ' 节</s></b></div>'
    + '</div>'
    + '<div class="swd">' + bars + '</div>'
    + '<p class="statp">本周共 ' + list.length + ' 个时段、' + secs + ' 节课，'
    + '集中在 ' + days + ' 天里。最重的一天是周' + DAY_SHORT[busiest] + '（' + per[busiest - 1] + ' 节），'
    + '其余时间留白。点右侧 EXPORT 可以把这一周导成 CSV。</p>';
}

function exportWeek(week, list) {
  const head = ['星期', '节次', '开始', '结束', '课程', '教师', '地点'];
  const lines = [head.join(',')];
  for (const c of list) {
    const t0 = (DATA.periodTimes && DATA.periodTimes[c.startPeriod]) || '';
    const t1 = (DATA.periodTimes && DATA.periodTimes[c.endPeriod + 1]) || '';
    const row = [DAY_NAMES[c.day], c.startPeriod + '-' + c.endPeriod, t0, t1,
      c.name, c.teacher || '', c.room || c.location || ''];
    lines.push(row.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(','));
  }
  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '第' + pad2(week) + '周课表.csv';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}

function openWeekSheet(week) {
  const list = weekCourses(week).slice().sort((a, b) => a.day - b.day || a.startPeriod - b.startPeriod);
  const names = new Set(list.map(c => c.name));
  const secs = list.reduce((n, c) => n + (c.endPeriod - c.startPeriod + 1), 0);
  const info = semesterInfo();
  const swap = sheetOpen;

  setText('wsFile', 'FILE W-' + pad2(week));
  setText('wsArea', list.length ? 'TIMETABLE AREA' : 'EMPTY WEEK');
  setText('wsTitle', '第 ' + pad2(week) + ' 周');
  setText('wsRange', cnRange(week));
  setText('wsCat', list.length ? '常规教学周' : '本周无排课');
  setText('capNum', 'NO.' + pad2(week));
  setText('capMeta', 'WEEK ' + pad2(week) + ' · ' + secs + ' SECTIONS');
  setText('wsCount', pad2(week) + ' / ' + pad2(maxWeek));

  const meta = E('wsMeta');
  if (meta) {
    const cells = [
      ['SEMESTER / 学期', esc(info['学年学期'] || '—')],
      ['COLLECTION / 本周', names.size + ' 门课 · ' + secs + ' 节'],
      ['PROGRAM / 专业', esc(info['专业'] || '—')],
      ['STATUS / 状态', '<i></i>已归档 · 可读取'],
    ];
    meta.innerHTML = cells.map(([k, v]) =>
      '<div><dt>' + k + '</dt><dd>' + (v.charAt(0) === '<' ? v : '<b>' + v + '</b>') + '</dd></div>'
    ).join('');
  }

  const full = E('wsFull');
  if (full) full.href = 'index.html?w=' + week;

  renderGrid(week, list);
  renderList(list);
  renderStat(week, list);
  setTab(activeTab);
  revealPane(swap);

  document.body.classList.add('sheet-open');
  setText('callLink', '收起 ↑');
  sheetOpen = true;
  lastSheetWeek = week;
  const body = E('wsBody');
  if (body) body.scrollTop = 0;
}

function closeWeekSheet() {
  if (!sheetOpen) return;
  document.body.classList.remove('sheet-open');
  setText('callLink', '打开课表 →');
  sheetOpen = false;
  lastSheetWeek = 0;
}

E('callLink').addEventListener('click', ev => {
  ev.stopPropagation();
  if (sheetOpen) { closeWeekSheet(); return; }
  openWeekSheet(selected + 1);
});
const backBtn = E('wsBack');
if (backBtn) backBtn.addEventListener('click', closeWeekSheet);
const tabsEl = E('wsTabs');
if (tabsEl) {
  tabsEl.addEventListener('click', ev => {
    const b = ev.target.closest('[data-tab]');
    if (!b) return;
    setTab(b.dataset.tab);
    revealPane(true);
  });
}
const exportBtn = E('wsExport');
if (exportBtn) {
  exportBtn.addEventListener('click', () => {
    if (!sheetOpen) return;
    exportWeek(selected + 1,
      weekCourses(selected + 1).slice().sort((a, b) => a.day - b.day || a.startPeriod - b.startPeriod));
  });
}

document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape' && sheetOpen) { closeWeekSheet(); ev.stopPropagation(); }
});

/* ---------- 把焦点脊顶投到屏幕，摆引线 ---------- */
const v = new THREE.Vector3();
function placeCallout() {
  const box = E('callout');
  if (!focusRail || !box || sheetOpen) return;

  v.set(0, H / 2, 0).applyMatrix4(focusRail.body.matrixWorld);
  v.project(camera);
  const px = (v.x * 0.5 + 0.5) * innerWidth;
  const py = (-v.y * 0.5 + 0.5) * innerHeight;

  /* 标注位置是**设计死的**，不跟着脊跑（照 RhineLabUI 的 .archive-callout 定坐标）。 */
  const wide = innerWidth >= 760;
  const bx = wide ? Math.round(innerWidth * 0.40) : 24;
  const by = wide ? Math.round(innerHeight * 0.20) : 96;
  box.style.setProperty('--bx', bx + 'px');
  box.style.setProperty('--by', by + 'px');
  box.style.setProperty('--dx2', px.toFixed(1) + 'px');

  /* 引线是**水平**的：方块在脊顶，线从方块向远处拉，文字浮在线的上方。 */
  const line = box.querySelector('.line');
  if (line) {
    const ly = Math.max(py, by + 110);          // 别穿过文字块
    const lw = Math.max(180, innerWidth * 0.42);
    line.style.left = px.toFixed(1) + 'px';
    line.style.top = ly.toFixed(1) + 'px';
    line.style.width = lw.toFixed(0) + 'px';
    line.style.transform = 'none';
    box.style.setProperty('--dy2', ly.toFixed(1) + 'px');
    box.style.setProperty('--actTop', (ly - by + 13).toFixed(0) + 'px');
  }
  box.style.opacity = '1';
}

/* ---------- 底部滚动周次条 ---------- */
const STRIP_W = 30;
const stripBox = E('strip');
const stripIn = E('stripIn');
let stripItems = [];
let stripOn = -1;
if (stripIn) {
  let h = '';
  for (let c = 0; c < RAIL_N; c++) h += '<i>' + pad2((c % PERIOD) + 1) + '</i>';
  stripIn.innerHTML = h;
  stripItems = [...stripIn.children];
}

/* ---------- 尺寸 ---------- */
function resize() {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight, false);
}
addEventListener('resize', resize);
resize();

/* ---------- 循环 ---------- */
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
let last = performance.now();

/* 抽出后板子要正对观者：绕 y 转到 +x 面朝相机，再偏 tilt 露出厚度。 */
const FACE_ROT = Math.atan2(
  camera.position.x - FOCUS_OPEN, camera.position.z
) - Math.PI / 2 + EX.tilt - group.rotation.y;

function tick(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  const time = now / 1000;
  const age = time - selectedAt;

  /* 焦点横坐标跟着面板开合，整条轨道因此整体让位到左半边 */
  const fxTarget = sheetOpen ? FOCUS_OPEN : FOCUS_CLOSED;
  focusX += (fxTarget - focusX) * Math.min(1, dt * (reduce ? 40 : 4.2));

  /* 轨道缓动：按环形最短路径逼近，所以 17 → 1 是往前滑一格，不是倒着走 16 格 */
  const fx = focusX / GAP_X;
  let delta = (selected - fx - railScroll) % PERIOD;
  if (delta > PERIOD / 2) delta -= PERIOD;
  if (delta < -PERIOD / 2) delta += PERIOD;
  railScroll += reduce ? delta : delta * Math.min(1, dt * 7.5);
  railScroll = ((railScroll % PERIOD) + PERIOD) % PERIOD;

  /* 先算位置，才知道谁在焦点上。
     取 RhineLabUI archive-loop.ts 的 nearestOccurrence：不去给每个柱子算余数，
     而是问"离当前中心最近的那一次出现是哪一次"。柱子编号可以无限延伸，
     到边界的回卷就自然落在视口外，不会看到接缝。 */
  /* 基准取 PERIOD 的整数倍：这样 (center + fx) 落在第几周只由 railScroll 决定，
     不会因为中间多出半个周期而整体错半格。 */
  const center = PERIOD + railScroll;
  let best = null, bestD = Infinity;
  for (const r of rails) {
    r.x = (nearestOccurrence(r.col, center, RAIL_N) - center) * GAP_X;
    const dist = Math.abs(r.x - focusX);
    if (dist < bestD) { bestD = dist; best = r; }
  }
  focusRail = best;

  for (const r of rails) {
    const isFocus = r === focusRail;
    const w = Math.max(0, 1 - Math.abs(r.x - focusX) / GAP_X);

    let target = w;
    if (!reduce && !isFocus) {
      target += neighborWave(r.col - focusRail.col, age) * 0.28;
    }
    if (!reduce) target += idleBreath(r.col, time);
    if (reduce) { r.spring.value = target; r.spring.velocity = 0; }
    else springDamp(r.spring, target, 9, dt);
    r.lift = r.spring.value;

    /* 抽出进度：只有焦点那一根抽，切周时旧的自己缩回去 */
    const exTarget = (sheetOpen && isFocus) ? 1 : 0;
    r.ex += (exTarget - r.ex) * Math.min(1, dt * (reduce ? 40 : 5.2));

    const e = clamp01(r.ex);
    const e1 = smooth(clamp01(e / 0.55));                 // 先往前拉
    const e2 = smooth(clamp01((e - 0.28) / 0.72));        // 再转正 + 缩小
    const py = r.baseY + LIFT * r.lift * (1 - e2) + (EX.y - r.baseY) * e2;
    const sc = 1 + (EX.scale - 1) * e2;

    /* 只有第 0 排会抬、会抽、会转；后排是背景，跟着横向滑动就够 */
    const front = r.holders[0];
    front.position.set(r.x, py, EX.pull * e1);
    front.rotation.y = FACE_ROT * e2;
    front.scale.setScalar(sc);
    /* 标签跟着抽出进度淡入，收回去时一起消失 */
    r.label.visible = e2 > 0.02;
    r.labelMat.opacity = e2;
    for (let row = 1; row < ROWS; row++) {
      r.holders[row].position.set(r.x, r.baseY, -row * T);
    }
  }

  /* 面板打开时略收窄视野（长焦再拉一点），不再动 position：
     透视相机下改 position.z 会同时改变距离和视线方向，阵列会整体跑偏。 */
  const fovTarget = sheetOpen ? 7.8 : 8.4;
  if (Math.abs(camera.fov - fovTarget) > 0.005) {
    camera.fov += (fovTarget - camera.fov) * Math.min(1, dt * 8);
    camera.updateProjectionMatrix();
  }

  /* 底部滚动周次条：跟着轨道位置一起平移，
     让"这是第几周、前后是什么"在没打开面板时也一眼可读。 */
  if (stripIn) {
    const w = STRIP_W;
    const P = PERIOD * w;
    const sw = stripBox.clientWidth || innerWidth;
    let tx = (sw / 2 - w / 2 - (center + fx) * w) % P;
    tx = ((tx % P) - P) % P;
    stripIn.style.transform = 'translate3d(' + tx.toFixed(2) + 'px,0,0)';
    const idx = Math.round(center + fx);
    if (idx !== stripOn) {
      if (stripItems[stripOn]) stripItems[stripOn].classList.remove('on');
      if (stripItems[idx]) stripItems[idx].classList.add('on');
      stripOn = idx;
    }
  }

  camera.updateMatrixWorld();
  group.updateMatrixWorld(true);
  placeCallout();
  renderer.render(scene, camera);
}

addEventListener('error', function (e) { document.title = 'ERR ' + e.message; });
paintOverlay();

/* ?w=9 直接停在某一周并展开——深链接，也是截图调试用的入口 */
const qw = parseInt(new URLSearchParams(location.search).get('w') || '', 10);
if (qw >= 1 && qw <= PERIOD) {
  selected = qw - 1;
  paintOverlay();
  openWeekSheet(qw);
}

try { tick(performance.now()); } catch (e) { document.title = 'TICK ' + e.message; }
renderer.setAnimationLoop(tick);
