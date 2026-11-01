/* 课程档案架：一列列立着的薄片，一本 = 一周。
   选中那本抬高一截，旁边拉一条细引线标注周次与日期。 */
import * as THREE from 'three';

const DATA = window.DATA || { courses: [], maxWeek: 17, start: '2026-08-31' };
const COLS = 6;
const W = 0.30, H = 2.20, T = 1.00;
const GAP_X = 0.34, GAP_Z = 1.04;
const LIFT = 0.36, PULL = 0.25;

const canvas = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-4, 4, 2.6, -2.6, 0.1, 100);
camera.position.set(7.4, 8.2, 9.6);
camera.lookAt(0, 1.15, 0);

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
  new THREE.ShadowMaterial({ opacity: 0.10 })
);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

const group = new THREE.Group();
group.rotation.y = -0.34;
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
const slotGeo = new THREE.BoxGeometry(W * 0.86, 0.045, T * 0.9);

const slots = [];
const pickables = [];

for (let w = 1; w <= maxWeek; w++) {
  const col = (w - 1) % COLS;
  const row = Math.floor((w - 1) / COLS);
  const cx = (col - (COLS - 1) / 2) * GAP_X;
  const cz = (row - 1) * GAP_Z;

  const list = weekCourses(w);
  const busy = list.length > 0;
  const hRatio = busy ? 1 : 0.55;
  const baseOpacity = busy ? 1 : 0.4;

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

  /* 脊顶色标：课程越多越深，饱和度压到 18% 左右 */
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
    mats: [side, face, top, capMat], busy, baseOpacity, lift: 0
  };
  slots.push(slot);
  pickables.push(body);
  body.userData.slot = slot;
}

let selected = Math.max(0, Math.min(slots.length - 1, currentWeek() - 1));
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
  if (s) select(slots.indexOf(s));
});

function select(i) {
  selected = Math.max(0, Math.min(slots.length - 1, i));
  paintOverlay();
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
  setText('colNum', pad(s.col + 1));
  setText('colTotal', '/ ' + pad(COLS));
  setText('slotName', '第 ' + s.week + ' 周 · ' + rangeOf(s.week));
  setText('callWeek', 'WEEK ' + pad(s.week));
  setText('callRange', rangeOf(s.week) + ' · ' + list.length + ' 门课');
  setText('callCount', list.length ? list.length + ' SECTIONS' : 'NO CLASS');
  const a = E('callLink');
  if (a) a.href = 'index.html?w=' + s.week;
}

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
  box.style.opacity = '1';
}

/* ---------- 尺寸 ---------- */
function resize() {
  const aspect = innerWidth / innerHeight;
  const viewH = Math.max(4.3, 3.5 / aspect);
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

  for (let i = 0; i < slots.length; i++) {
    const s = slots[i];
    const want = i === selected ? 1 : (i === hovered ? 0.16 : 0);
    s.lift = reduce ? want : THREE.MathUtils.damp(s.lift, want, 12, dt);

    const px = s.baseX;
    const pz = s.baseZ - PULL * s.lift;
    const py = s.baseY + LIFT * s.lift + (s.busy ? 0 : 0);
    s.holder.position.set(px, py, pz);

    const op = s.baseOpacity * (i === selected ? 1 : (hovered === i ? 1 : (selected >= 0 ? 0.92 : 1)));
    for (let m = 0; m < s.mats.length; m++) {
      const mt = s.mats[m];
      const target = (m === 3) ? (s.busy ? 1 : 0.35) : op;
      mt.opacity = target;
      mt.depthWrite = target > 0.96;
    }
  }

  camera.updateMatrixWorld();
  placeCallout();
  renderer.render(scene, camera);
}

addEventListener('error', function(e){ document.title = 'ERR ' + e.message; });
paintOverlay();
try { tick(performance.now()); } catch (e) { document.title = 'TICK ' + e.message; }
renderer.setAnimationLoop(tick);
