/* 课程档案架：一列列立着的薄片，一本 = 一周。
   选中那本抬高一截，旁边拉一条细引线标注周次与日期。 */
import * as THREE from 'three';

const DATA = window.DATA || { courses: [], maxWeek: 17, start: '2026-08-31' };
const COLS = 1;                 // 真脊只有一排，横向铺满
/* 参考图里看着有几十根脊，但它的索引写的是 ARCHIVE INDEX (7) / 01 / 08 ——
   真档案只有个位数，密度来自前后几排**装饰脊**。所以这里也一样：
   17 本真脊横排，前后各 2 排装饰，靠它们把"档案库"的密度撑起来。 */
const W = 0.20, H = 1.66, T = 0.50;
const GAP_X = 0.246, GAP_Z = 0.56;
const DECOR_ROWS = 2;           // 前后各 2 排
const LIFT = 0.62, PULL = 0.13;

const canvas = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-4, 4, 2.6, -2.6, 0.1, 100);
camera.position.set(5.8, 7.2, 7.6);
camera.lookAt(-0.22, 0.84, -0.24);

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
  new THREE.ShadowMaterial({ opacity: 0.07 })
);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

const group = new THREE.Group();
group.rotation.y = -0.26;
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
function rangeOf(w) {
  const a = isoOf(w, 1), b = isoOf(w, 7);
  const f = d => String(d.getMonth() + 1).padStart(2, '0') + '/' + String(d.getDate()).padStart(2, '0');
  return f(a) + ' – ' + f(b);
}

const bodyGeo = new THREE.BoxGeometry(W, H, T);
const capGeo = new THREE.BoxGeometry(W * 0.82, 0.022, T * 0.82);

const slots = [];
const pickables = [];

/* 装饰脊：没有交互、不可拾取，只是把画面填满。
   高度按周次的伪随机数错开，让脊顶参差——整齐齐像柜子，参差才像被人翻过的档案架。
   颜色不能贴近背景 #e8e5e1，否则远处那排看着像半透明；实测它们 op=1 完全不透明，
   纯粹是明度太接近才产生的错觉。 */
const decorMat = new THREE.MeshStandardMaterial({
  color: 0xb9b2a4, roughness: 0.94, metalness: 0
});
function pseudo(n) {
  const x = Math.sin(n * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}
/* 只放在真脊**后方**（远离相机一侧）。放前面会挡住真脊，喧宾夺主。 */
for (let r = 1; r <= DECOR_ROWS; r++) {
  const n = maxWeek - 4;                     // 比真脊少几列，退进画面里不溢出
  for (let c = 0; c < n; c++) {
    const seed = r * 100 + c * 7;
    const h = H * (0.46 + pseudo(seed) * 0.22);   // 明显矮于真脊
    const m = new THREE.Mesh(bodyGeo, decorMat);
    m.scale.set(1, h / H, 1);
    const cx = (c - (n - 1) / 2) * GAP_X;
    m.position.set(cx, h / 2, -r * GAP_Z);   // 相机在 +z，后方即 -z
    m.castShadow = false;          // 装饰脊几十根，全投影会糊掉画面右下角
    m.receiveShadow = true;
    group.add(m);
  }
}

for (let w = 1; w <= maxWeek; w++) {
  const col = w - 1;
  const row = 0;
  const cx = (col - (maxWeek - 1) / 2) * GAP_X;
  const cz = 0;

  const list = weekCourses(w);
  const busy = list.length > 0;
  const hRatio = busy ? 1 : 0.62;
  const baseOpacity = busy ? 1 : 0.82;

  const side = new THREE.MeshStandardMaterial({
    color: 0xded9d0, roughness: 0.88, metalness: 0, transparent: true, opacity: baseOpacity
  });
  const face = new THREE.MeshStandardMaterial({
    color: 0xf4f1ea, roughness: 0.9, metalness: 0, transparent: true, opacity: baseOpacity
  });
  const top = new THREE.MeshStandardMaterial({
    color: 0xf7f4ee, roughness: 0.9, metalness: 0, transparent: true, opacity: baseOpacity
  });

  const body = new THREE.Mesh(bodyGeo, [side, side, top, side, face, side]);
  body.castShadow = true;
  body.receiveShadow = true;
  body.scale.y = hRatio;

  const holder = new THREE.Group();
  holder.position.set(cx, (H * hRatio) / 2, cz);
  holder.add(body);

  /* 脊顶色标：课程越多越深，饱和度压到 20% 左右 */
  const hue = [212, 350, 127, 264, 42, 180, 317, 95][w % 8];
  const light = busy ? Math.max(34, 62 - list.length * 4) : 70;
  const capMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color(`hsl(${hue} 20% ${light}%)`),
    roughness: 0.8, metalness: 0, transparent: true, opacity: busy ? 1 : 0.35
  });
  const cap = new THREE.Mesh(capGeo, capMat);
  cap.position.set(0, H / 2 + 0.012, 0);
  cap.castShadow = true;
  body.add(cap);

  group.add(holder);
  const slot = {
    week: w, col, row, holder, body, baseY: (H * hRatio) / 2, baseX: cx, baseZ: cz,
    mats: [side, face, top, capMat], busy, baseOpacity, lift: 0,
    spring: { value: 0, velocity: 0 }
  };
  slots.push(slot);
  pickables.push(body);
  body.userData.slot = slot;
}

/* ---------- 动效 ----------
   借自 RhineLabUI 的 motion.ts（MIT）。核心不是"更顺滑的缓动"，而是：
   选中一根时，**相邻的也跟着动一下再平息**。只有选中那根在动，整排看上去就是静态图。 */
const smooth = t => {
  t = Math.max(0, Math.min(1, t));
  return t * t * t * (10 + t * (-15 + 6 * t));
};
const bell = (x, width) => Math.exp(-0.5 * (x / width) ** 2);

/* 带速度的二阶阻尼。注意它**不会过冲**（实测 rate 4~12 峰值都是 1.0000），
   它比一阶强的地方是启动/收尾带惯性，不会像指数逼近那样一上来就"刹车"。
   想要回弹得改成欠阻尼形式，但参考实现的波形本来也是显式包络，不靠过冲。 */
function springDamp(s, target, rate, dt) {
  const delta = s.value - target;
  const impulse = s.velocity + rate * delta;
  const decay = Math.exp(-rate * dt);
  s.value = target + (delta + impulse * dt) * decay;
  s.velocity = (s.velocity - rate * impulse * dt) * decay;
}

/* 邻脊被"带起来"的幅度：按距离延迟 + 衰减振荡，像手指扫过一排档案。
   距离越远起得越晚、幅度越小，所以是依次起伏，不是齐动。
   系数 0.28 是量出来的：d=1 峰值约为主抬升的 13%（屏幕上十几像素），
   原来取 0.085 只有 4%、约 2px，等于没做。 */
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

let selectedAt = 0;                 // 上次选中的时刻，用来算波纹年龄
let selected = Math.max(0, Math.min(slots.length - 1, currentWeek() - 1));
/* 面板状态要在这里声明：select() 会读它，而 select 定义在上面。
   放在 select 之后会形成 TDZ，任何在模块执行期调用 select 的改动都会直接抛错。 */
let sheetOpen = false;
let lastSheetWeek = 0;
let hovered = -1;

/* ---------- 交互 ---------- */
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
let pointerIn = false;

function pick(ev) {
  const r = canvas.getBoundingClientRect();
  ndc.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
  ndc.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
  ray.setFromCamera(ndc, camera);
  const hit = ray.intersectObjects(pickables, false)[0];
  return hit ? hit.object.userData.slot : null;
}

canvas.addEventListener('pointermove', (ev) => {
  if (ev.pointerType === 'touch') return;
  const s = pick(ev);
  hovered = s ? slots.indexOf(s) : -1;
  canvas.style.cursor = s ? 'pointer' : 'default';
});
canvas.addEventListener('pointerleave', () => { hovered = -1; canvas.style.cursor = 'default'; });
canvas.addEventListener('click', (ev) => {
  const s = pick(ev);
  if (!s) return;
  const i = slots.indexOf(s);
  /* 左键点脊就直接打开课表，不用再去找引线里那个按钮。
     点的是当前已经打开的那一根 → 收起。 */
  if (sheetOpen && i === selected) { closeWeekSheet(); return; }
  select(i);
  if (!sheetOpen) openWeekSheet(slots[i].week);
});

function select(i) {
  const next = Math.max(0, Math.min(slots.length - 1, i));
  if (next !== selected) selectedAt = performance.now() / 1000;
  selected = next;
  paintOverlay();
  /* 面板开着时切周，内容必须跟着换——否则引线指向第 10 周、面板还是第 9 周。
     注意 next 是数组下标（0 基），lastSheetWeek 是周次（1 基），必须 +1 再比，
     否则永远差 1，面板会慢一拍。 */
  const nextWeek = next + 1;
  if (sheetOpen && nextWeek !== lastSheetWeek) openWeekSheet(nextWeek);
}

addEventListener('keydown', (ev) => {
  const k = ev.key;
  if (k === 'ArrowRight') { select(selected + 1); ev.preventDefault(); }
  else if (k === 'ArrowLeft') { select(selected - 1); ev.preventDefault(); }
  else if (k === 'ArrowDown') { select(selected + COLS); ev.preventDefault(); }
  else if (k === 'ArrowUp') { select(selected - COLS); ev.preventDefault(); }
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
  const s = slots[selected];
  if (!s) return;
  const list = weekCourses(s.week);
  const pad = n => String(n).padStart(2, '0');
  setText('idx', '(' + maxWeek + ')');
  setText('bigNum', pad(s.week));
  setText('totalNum', '/ ' + pad(maxWeek));
  setText('colNum', pad(s.week));
  setText('colTotal', '/ ' + pad(maxWeek));
  setText('slotName', '第 ' + s.week + ' 周 · ' + rangeOf(s.week));
  setText('callWeek', 'WEEK ' + pad(s.week));
  const names = new Set(list.map(c => c.name));
  setText('callRange', rangeOf(s.week) + ' · ' + names.size + ' 门课 / ' + list.length + ' 节');
  setText('callCount', list.length ? list.length + ' SECTIONS' : 'NO CLASS');
  /* 面板内容由 openWeekSheet(week) 现取，这里不需要预写链接 */
}

/* ---------- 周档案面板 ----------
   点「打开课表」原地展开，不再整页跳到 index.html 重载。
   之前是 <a href>，点一下整个 WebGL 场景重新初始化，所以那一瞬间必然是白的。 */
const DAY_NAMES = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日'];

function pad2(n) { return (n < 10 ? '0' : '') + n; }

/* 课程配色：按课程名首次出现顺序发号，同一门课整学期同色。
   和主站 index.html 用的是同一组色相、同一套规则。 */
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

/* 面板内容：7 列星期 × 6 大节的正经课表网格。
   不是按天罗列的清单——用户要的是"正常课表"的样子。 */
function openWeekSheet(week) {
  const host = E('wsGrid');
  const list = weekCourses(week).slice();
  const todayIso = (() => {
    const d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  })();

  E('wsNum').innerHTML = pad2(week) + '<s id="wsAll">/ ' + pad2(maxWeek) + '</s>';
  const names = new Set(list.map(c => c.name));
  E('wsRange').textContent = rangeOf(week) + ' · ' + names.size + ' 门课 / ' + list.length + ' 节';
  if (E('wsFull')) E('wsFull').href = 'index.html?w=' + week;

  if (!list.length) {
    host.innerHTML = '<div class="tempty">这一周没有排课</div>';
  } else {
    let h = '<div class="tgrid">';

    /* 所有格子都显式指定行列。
       不能让它们走自动流：课程块是显式 grid-row/column 定位的，自动流会跳过
       被课程块占住的格子，节次列就会被挤到某一天的列里去（第一版就是这样错的）。 */
    h += '<div class="th blank" style="grid-column:1;grid-row:1"></div>';
    for (let d = 1; d <= 7; d++) {
      const dt = isoOf(week, d);
      h += '<div class="th" style="grid-column:' + (d + 1) + ';grid-row:1;--i:' + (d - 1) + '">'
         + DAY_NAMES[d]
         + '<em>' + pad2(dt.getMonth() + 1) + '/' + pad2(dt.getDate()) + '</em></div>';
    }

    /* 六个大节：左侧节次列（1-2 / 08:30）+ 7 个空格子当底板 */
    for (let r = 1; r <= 6; r++) {
      const sp = (r - 1) * 2 + 1;
      const t = (DATA.periodTimes && DATA.periodTimes[sp]) || '';
      h += '<div class="gt" style="grid-column:1;grid-row:' + (r + 1) + ';--i:' + r + '">'
         + '<b>' + sp + '-' + (sp + 1) + '</b><span>' + t + '</span></div>';
      for (let d = 1; d <= 7; d++) {
        const dt = isoOf(week, d);
        const iso = dt.getFullYear() + '-' + pad2(dt.getMonth() + 1) + '-' + pad2(dt.getDate());
        h += '<div class="cell' + (iso === todayIso ? ' today' : '') + '" style="grid-column:'
           + (d + 1) + ';grid-row:' + (r + 1) + '"></div>';
      }
    }

    /* 课程块：显式指定行列，跨大节的课用 span 占多行 */
    let idx = 0;
    for (const c of list) {
      const r1 = Math.ceil(c.startPeriod / 2);
      const r2 = Math.ceil(c.endPeriod / 2);
      const span = Math.max(1, r2 - r1 + 1);
      if (r1 < 1 || r1 > 6) continue;
      const where = c.room || c.location || '';
      h += '<div class="cc" style="grid-column:' + (c.day + 1)
         + ';grid-row:' + (r1 + 1) + ' / span ' + Math.min(span, 7 - r1)
         + ';--c:' + colorOf(c.name) + ';--i:' + (idx++) + '">'
         + '<b>' + c.name + '</b>'
         + '<i>' + where + '</i>'
         + '</div>';
    }

    h += '</div>';
    host.innerHTML = h;
  }

  E('wsScrim').classList.add('show');
  E('wsheet').classList.add('show');
  document.body.classList.add('sheet-open');
  E('callLink').textContent = '收起 ↑';
  sheetOpen = true;
  lastSheetWeek = week;
  const body = E('wsBody');
  if (body) { body.scrollTop = 0; body.scrollLeft = 0; }
}

function closeWeekSheet() {
  if (!sheetOpen) return;
  E('wsScrim').classList.remove('show');
  E('wsheet').classList.remove('show');
  document.body.classList.remove('sheet-open');
  E('callLink').textContent = '打开课表 →';
  sheetOpen = false;
  lastSheetWeek = 0;
}

E('callLink').addEventListener('click', ev => {
  ev.stopPropagation();
  if (sheetOpen) { closeWeekSheet(); return; }
  openWeekSheet(slots[selected].week);
});
E('wsClose').addEventListener('click', closeWeekSheet);
E('wsScrim').addEventListener('click', closeWeekSheet);

document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape' && sheetOpen) { closeWeekSheet(); ev.stopPropagation(); }
});

/* ---------- 把选中脊顶投到屏幕，摆引线 ---------- */
const v = new THREE.Vector3();
function placeCallout() {
  const s = slots[selected];
  const box = E('callout');
  if (!s || !box) return;
  s.holder.getWorldPosition(v);
  v.y += (H * (s.busy ? 1 : 0.55)) / 2 + 0.06;
  v.project(camera);
  const x = (v.x * 0.5 + 0.5) * innerWidth;
  const y = (-v.y * 0.5 + 0.5) * innerHeight;
  box.style.transform = 'translate(' + Math.round(x) + 'px,' + Math.round(y) + 'px)';

  /* 文字块永远摆到空白处，不压在脊上：
     脊在中线右侧 → 文字整体翻到左边（左边那一片正好是空的），反之往右。
     只翻转不挪位置的话，文字免不了要盖住某几根脊。 */
  const toLeft = x > innerWidth * 0.46;
  box.style.setProperty('--ox', toLeft ? '-352px' : '22px');
  box.style.setProperty('--lx', toLeft ? '-300px' : '0px');
  /* 垂直方向也别撞上左上角那三行标题：块顶至少落在 y=186 以下 */
  box.style.setProperty('--fy', Math.max(0, 186 - y) + 'px');
  box.style.opacity = '1';
}

/* ---------- 尺寸 ---------- */
function resize() {
  const aspect = innerWidth / innerHeight;
  const viewH = Math.max(4.2, 3.5 / aspect);
  camera.left = -viewH * aspect / 2;
  camera.right = viewH * aspect / 2;
  camera.top = viewH / 2;
  camera.bottom = -viewH / 2;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight, false);
}
addEventListener('resize', resize);
resize();

/* ---------- 循环 ---------- */
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
let last = performance.now();

function tick(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;

  const time = now / 1000;
  const age = time - selectedAt;

  for (let i = 0; i < slots.length; i++) {
    const s = slots[i];
    const base = i === selected ? 1 : (i === hovered ? 0.16 : 0);

    /* 选中一根时，邻脊按距离依次被带起再平息；静止时整体极轻微呼吸。
       两条加起来幅度都很小（邻脊约主位移的 1/12），但整排因此不再像静态图。 */
    let wobble = 0;
    if (!reduce) {
      const d = i - selected;
      if (d !== 0) wobble = neighborWave(d, age) * 0.28;
      wobble += idleBreath(i, time);
    }

    if (reduce) {
      s.spring.value = base;
      s.spring.velocity = 0;
    } else {
      springDamp(s.spring, base + wobble, 9, dt);
    }
    s.lift = s.spring.value;

    const px = s.baseX;
    /* 朝观者抽出（相机在 +z），不是往后推——往后推会被后排的装饰脊挡住，
       "抽出"这个动作也就看不出来了。 */
    const pz = s.baseZ + PULL * s.lift;
    const py = s.baseY + LIFT * s.lift + (s.busy ? 0 : 0);
    s.holder.position.set(px, py, pz);

    /* 不要为了"突出选中"把其余脊降到 0.92：那会让 depthWrite 变 false，
       后面的脊直接透出来，看着像塑料壳。区分靠抬升就够了。 */
    for (let m = 0; m < s.mats.length; m++) {
      const mt = s.mats[m];
      const target = (m === 3) ? (s.busy ? 1 : 0.35) : s.baseOpacity;
      mt.opacity = target;
      /* 关键：完全不透明时必须关掉 transparent。否则它仍走透明渲染队列，
         按距离排序而不是深度测试，前面这几根就会"透"出后面的脊，像塑料壳。 */
      mt.transparent = target < 0.999;
      mt.depthWrite = target > 0.96;
    }
  }

  /* 面板打开时场景略退，给底部面板让出层次感 */
  const zoomTarget = sheetOpen ? 0.93 : 1;
  if (Math.abs(camera.zoom - zoomTarget) > 0.001) {
    camera.zoom += (zoomTarget - camera.zoom) * Math.min(1, dt * 8);
    camera.updateProjectionMatrix();
  }

  camera.updateMatrixWorld();
  placeCallout();
  renderer.render(scene, camera);
}

addEventListener('error', function(e){ document.title = 'ERR ' + e.message; });
paintOverlay();
try { tick(performance.now()); } catch (e) { document.title = 'TICK ' + e.message; }
renderer.setAnimationLoop(tick);
