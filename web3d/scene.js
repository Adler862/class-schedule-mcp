/* 课程档案 · 3D 课表 */
import * as THREE from 'three';

const data = window.DATA || { meta: {}, courses: [], periodTimes: {} };
const courses = Array.isArray(data.courses) ? data.courses : [];
const periodTimes = data.periodTimes || {};
const defaultPeriodTimes = { 1: '08:30', 3: '10:30', 5: '14:00', 7: '16:00', 9: '19:00', 11: '21:00' };
const periodTime = (period, fallback = '') => periodTimes[period] || defaultPeriodTimes[period] || fallback;
const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const EMPTY_HEIGHT_RATIO = 0.18;
const EMPTY_OPACITY = 0.35;

const canvas = document.getElementById('stage');
const hoverMain = document.getElementById('hover-main');
const hoverSub = document.getElementById('hover-sub');
const closeButton = document.getElementById('close-file');
const dayLabels = Array.from(document.querySelectorAll('.day-label'));
const periodLabels = Array.from(document.querySelectorAll('.period-label'));
const semesterText = String(data.meta.semester || '');
const className = semesterText.match(/班级[：:]\s*([^\s]+)/)?.[1] || '课程档案';
const term = semesterText.match(/学年学期[：:]\s*([^\s]+)/)?.[1] || '';
const courseCount = new Set(courses.map(course => course.name).filter(Boolean)).size;

document.getElementById('semester').textContent = term;
document.getElementById('student').textContent = className;
document.querySelector('.footer .index').textContent = `${weekdays.length} 天 × ${periodLabels.length} 大节 · 共 ${courseCount} 门课`;
canvas.tabIndex = 0;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight, false);
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.08;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-6, 6, 4.5, -4.5, 0.1, 100);
camera.position.set(9.5, 11, 16);
camera.lookAt(0, 1.05, 0);

scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d3ca, 2.0));
const key = new THREE.DirectionalLight(0xffffff, 2.35);
key.position.set(-4, 11, 8);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.left = -10;
key.shadow.camera.right = 10;
key.shadow.camera.top = 10;
key.shadow.camera.bottom = -10;
key.shadow.camera.near = 0.5;
key.shadow.camera.far = 35;
key.shadow.bias = -0.0004;
key.shadow.normalBias = 0.025;
scene.add(key);

const fill = new THREE.DirectionalLight(0xffffff, 0.45);
fill.position.set(8, 5, -6);
scene.add(fill);

const group = new THREE.Group();
group.rotation.y = -0.16;
scene.add(group);

const shadow = new THREE.Mesh(
  new THREE.PlaneGeometry(28, 28),
  new THREE.ShadowMaterial({ color: 0x625d54, opacity: 0.105, transparent: true })
);
shadow.rotation.x = -Math.PI / 2;
shadow.position.y = -0.012;
shadow.receiveShadow = true;
scene.add(shadow);

/* 档案脊用几何体。
   Blender 那边确实导出了一根带倒角的 spine.glb（web3d/models/，8.4KB），
   但接进来实测两个问题：一是 glTF 的 Y-up 转换挂在节点旋转上，只取 geometry 会丢朝向，
   薄片会躺平；二是这个尺度下倒角只有几个像素，视觉上和 Box 没区别，却要多 92KB。
   所以 3D 页保持几何体，模型文件留在仓库里作为建模管线的产物。 */
const bodyGeometry = new THREE.BoxGeometry(0.46, 2.05, 1.08);

const markerGeometry = new THREE.BoxGeometry(0.34, 0.045, 0.22);
const courseBySlot = new Map();
for (let i = 0; i < courses.length; i++) {
  const course = courses[i];
  const day = Number(course.day);
  const row = Math.floor((Number(course.startPeriod) - 1) / 2);
  if (day >= 1 && day <= 7 && row >= 0 && row < 6) {
    const key = `${row}:${day - 1}`;
    if (!courseBySlot.has(key)) courseBySlot.set(key, course);
  }
}

function courseColor(name) {
  let hash = 0;
  const text = String(name || 'FILE');
  for (let i = 0; i < text.length; i++) hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  return new THREE.Color().setHSL((hash % 360) / 360, 0.18, 0.55);
}

function fileCode(course) {
  const firstWeek = Array.isArray(course.weeks) && course.weeks.length ? course.weeks[0] : 1;
  return `W${String(firstWeek).padStart(2, '0')}·D${String(course.day).padStart(2, '0')}·P${String(course.startPeriod).padStart(2, '0')}`;
}

function wrapText(ctx, text, maxWidth, maxLines) {
  const lines = [];
  let line = '';
  const chars = Array.from(String(text || '未命名课程'));
  for (let i = 0; i < chars.length; i++) {
    const test = line + chars[i];
    if (line && ctx.measureText(test).width > maxWidth) {
      lines.push(line);
      line = chars[i];
      if (lines.length === maxLines) break;
    } else {
      line = test;
    }
  }
  if (lines.length < maxLines && line) lines.push(line);
  if (lines.length === maxLines && chars.join('').length > lines.join('').length) {
    let last = lines[maxLines - 1];
    while (last && ctx.measureText(`${last}…`).width > maxWidth) last = last.slice(0, -1);
    lines[maxLines - 1] = `${last}…`;
  }
  return lines;
}

function makeCardTexture(course, accent) {
  const card = document.createElement('canvas');
  card.width = 640;
  card.height = 1180;
  const ctx = card.getContext('2d');
  ctx.fillStyle = '#f2efe9';
  ctx.fillRect(0, 0, card.width, card.height);
  ctx.fillStyle = '#151713';
  ctx.font = '500 22px -apple-system, "MiSans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif';
  ctx.fillText('COURSE ARCHIVE / 课程档案', 56, 72);
  ctx.fillStyle = `#${accent.getHexString()}`;
  ctx.fillRect(56, 108, 528, 5);
  ctx.fillStyle = '#a67d48';
  ctx.fillRect(56, 108, 116, 5);

  let titleSize = 60;
  let titleLines;
  do {
    ctx.font = `600 ${titleSize}px -apple-system, "MiSans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif`;
    titleLines = wrapText(ctx, course.name, 528, 2);
    if (titleLines.length < 2) break;
    titleSize -= 4;
  } while (titleSize > 40);
  ctx.fillStyle = '#151713';
  titleLines.forEach((line, i) => ctx.fillText(line, 56, 220 + i * (titleSize + 22)));

  const detailTop = titleLines.length > 1 ? 390 : 320;
  ctx.fillStyle = '#6f6c64';
  ctx.font = '500 20px -apple-system, "MiSans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif';
  ctx.fillText('授课教师 / INSTRUCTOR', 56, detailTop);
  ctx.fillText('上课地点 / LOCATION', 56, detailTop + 142);
  ctx.fillText('时间安排 / SCHEDULE', 56, detailTop + 310);

  ctx.fillStyle = '#151713';
  ctx.font = '500 34px -apple-system, "MiSans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif';
  ctx.fillText(course.teacher || '待定', 56, detailTop + 54);
  const room = course.room || course.location || '待定';
  ctx.font = '600 46px -apple-system, "MiSans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif';
  ctx.fillText(String(room), 56, detailTop + 212);
  if (course.location && course.location !== course.room) {
    ctx.fillStyle = '#6f6c64';
    ctx.font = '400 23px -apple-system, "MiSans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif';
    const locationLines = wrapText(ctx, course.location, 528, 2);
    locationLines.forEach((line, i) => ctx.fillText(line, 56, detailTop + 254 + i * 30));
  }

  const day = weekdays[course.day - 1] || '待定';
  const start = Number(course.startPeriod) || 1;
  const end = Number(course.endPeriod) || start;
  const time = periodTime(start) || '';
  ctx.fillStyle = '#151713';
  ctx.font = '500 32px -apple-system, "MiSans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif';
  ctx.fillText(`${day}  第 ${start}–${end} 节${time ? `  ·  ${time}` : ''}`, 56, detailTop + 370);

  ctx.strokeStyle = '#c9c4ba';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(56, 1018);
  ctx.lineTo(584, 1018);
  ctx.stroke();
  ctx.fillStyle = '#6f6c64';
  ctx.font = '500 19px -apple-system, "MiSans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif';
  ctx.fillText('档案 / FILE', 56, 1070);
  ctx.fillStyle = '#a67d48';
  ctx.font = '500 25px ui-monospace, SFMono-Regular, Consolas, monospace';
  ctx.textAlign = 'right';
  ctx.fillText(fileCode(course), 584, 1110);
  ctx.textAlign = 'left';

  const texture = new THREE.CanvasTexture(card);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  return texture;
}

const slots = [];
const pickTargets = [];
for (let r = 0; r < 6; r++) {
  for (let c = 0; c < 7; c++) {
    const course = courseBySlot.get(`${r}:${c}`) || null;
    const baseOpacity = course ? 1 : EMPTY_OPACITY;
    const side = new THREE.MeshStandardMaterial({
      color: 0xdedbd5, roughness: 0.85, metalness: 0, transparent: true, opacity: baseOpacity
    });
    const top = new THREE.MeshStandardMaterial({
      color: 0xf2efe9, roughness: 0.85, metalness: 0, transparent: true, opacity: baseOpacity
    });
    const front = new THREE.MeshStandardMaterial({
      color: 0xf2efe9, roughness: 0.85, metalness: 0, transparent: true, opacity: baseOpacity,
      emissive: 0xf2efe9, emissiveIntensity: 0
    });
    const body = new THREE.Mesh(bodyGeometry, [side, side, top, side, front, side]);
    body.castShadow = !!course;
    body.receiveShadow = true;

    const holder = new THREE.Group();
    const baseX = (c - 3) * 0.66;
    const baseZ = (r - 2.5) * 1.26;
    const baseY = course ? 1.025 : 1.025 * EMPTY_HEIGHT_RATIO;
    holder.position.set(baseX, baseY, baseZ);
    if (!course) body.scale.y = EMPTY_HEIGHT_RATIO;
    holder.add(body);
    group.add(holder);

    const materials = [side, top, front];
    let marker = null;
    let accent = null;
    if (course) {
      accent = courseColor(course.name);
      const markerMaterial = new THREE.MeshStandardMaterial({
        color: accent, roughness: 0.85, metalness: 0, transparent: true, opacity: 1
      });
      marker = new THREE.Mesh(markerGeometry, markerMaterial);
      marker.position.set(0, 1.047, 0.31);
      marker.castShadow = true;
      body.add(marker);
      materials.push(markerMaterial);
    }

    const slot = {
      row: r, col: c, course, holder, body, front, materials, marker, accent,
      baseX, baseY, baseZ, baseOpacity, hoverLift: 0, texture: null
    };
    body.userData.slot = slot;
    slots.push(slot);
    pickTargets.push(body);
  }
}

for (let i = 0; i < periodLabels.length; i++) {
  const start = i * 2 + 1;
  periodLabels[i].innerHTML = `<span>${start}-${start + 1}</span><small>${periodTime(start) || '—'}</small>`;
}

scene.updateMatrixWorld(true);
const cameraLocal = group.worldToLocal(camera.position.clone()).normalize();
const selectedRotationY = Math.atan2(camera.position.x, camera.position.z) - group.rotation.y;
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const projection = new THREE.Vector3();
const axisPoints = [];
for (let c = 0; c < 7; c++) {
  axisPoints.push(group.localToWorld(new THREE.Vector3((c - 3) * 0.66, 0.06, -4.08)));
}
for (let r = 0; r < 6; r++) {
  axisPoints.push(group.localToWorld(new THREE.Vector3(-2.72, 0.08, (r - 2.5) * 1.26)));
}

function updateAxes() {
  for (let i = 0; i < axisPoints.length; i++) {
    projection.copy(axisPoints[i]).project(camera);
    const element = i < 7 ? dayLabels[i] : periodLabels[i - 7];
    element.style.left = `${(projection.x * 0.5 + 0.5) * innerWidth}px`;
    element.style.top = `${(-projection.y * 0.5 + 0.5) * innerHeight}px`;
  }
}

function resize() {
  const aspect = innerWidth / innerHeight;
  // 阵列投影约 8.3 宽 × 5.5 高，收紧到 5.6 高刚好铺满，留一点边
  const viewHeight = Math.max(5.6, 5.4 / aspect);
  camera.left = -viewHeight * aspect / 2;
  camera.right = viewHeight * aspect / 2;
  camera.top = viewHeight / 2;
  camera.bottom = -viewHeight / 2;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight, false);
  updateAxes();
}
addEventListener('resize', resize);
resize();

let hovered = null;
let active = null;
let motion = null;
let pointerDirty = false;
let pointerClientX = 0;
let pointerClientY = 0;
let pointerDownX = 0;
let pointerDownY = 0;

function setHover(slot) {
  if (hovered === slot) return;
  if (hovered && hovered !== active) {
    hovered.front.color.setHex(0xf2efe9);
    hovered.front.emissiveIntensity = 0;
  }
  hovered = slot;
  canvas.style.cursor = slot ? 'pointer' : 'default';
  if (!slot) {
    hoverMain.textContent = '选择一根档案脊';
    hoverSub.textContent = '点击展开课程档案';
    return;
  }
  const start = slot.row * 2 + 1;
  const time = periodTime(start) || '时间待定';
  hoverMain.textContent = `${weekdays[slot.col]} 第 ${start}-${start + 1} 节 · ${time}`;
  hoverSub.textContent = slot.course ? slot.course.name : '空档 / NO FILE';
  if (slot !== active) {
    slot.front.color.setHex(0xffffff);
    slot.front.emissiveIntensity = 0.07;
  }
}

function hitTest(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  pointer.set(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(pickTargets, false);
  return hits.length ? hits[0].object.userData.slot : null;
}

canvas.addEventListener('pointermove', (event) => {
  pointerClientX = event.clientX;
  pointerClientY = event.clientY;
  pointerDirty = true;
});
canvas.addEventListener('pointerleave', () => {
  pointerDirty = false;
  setHover(null);
});
canvas.addEventListener('pointerdown', (event) => {
  pointerDownX = event.clientX;
  pointerDownY = event.clientY;
});
canvas.addEventListener('pointerup', (event) => {
  if (Math.hypot(event.clientX - pointerDownX, event.clientY - pointerDownY) > 7) return;
  const slot = hitTest(event.clientX, event.clientY);
  if (slot && slot.course && !active) openFile(slot);
});

function openFile(slot) {
  setHover(null);
  active = slot;
  if (!slot.texture) slot.texture = makeCardTexture(slot.course, slot.accent);
  slot.front.map = slot.texture;
  slot.front.color.setHex(0xffffff);
  slot.front.emissiveIntensity = 0;
  slot.front.needsUpdate = true;
  document.body.classList.add('is-open');
  closeButton.tabIndex = 0;
  closeButton.setAttribute('aria-hidden', 'false');
  hoverMain.textContent = slot.course.name;
  hoverSub.textContent = `${fileCode(slot.course)} · 档案已展开`;
  motion = reducedMotion ? null : { from: 0, to: 1, start: performance.now(), opening: true };
  if (reducedMotion) updateScene(1, 0);
}

function closeFile() {
  if (!active || (motion && !motion.opening)) return;
  motion = reducedMotion ? null : { from: 1, to: 0, start: performance.now(), opening: false };
  document.body.classList.remove('is-open');
  closeButton.tabIndex = -1;
  closeButton.setAttribute('aria-hidden', 'true');
  if (reducedMotion) {
    const closing = active;
    updateScene(0, 0);
    active = null;
    resetCard(closing);
    setHover(null);
  }
  canvas.focus({ preventScroll: true });
}

function resetCard(slot) {
  slot.front.map = null;
  slot.front.color.setHex(0xf2efe9);
  slot.front.needsUpdate = true;
  slot.body.scale.set(1, 1, 1);
  slot.holder.rotation.set(0, 0, 0);
}

closeButton.addEventListener('click', closeFile);
addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeFile();
});

function easeCubic(t) {
  let x = t;
  for (let i = 0; i < 7; i++) {
    const u = 1 - x;
    const bx = 3 * u * u * x * 0.2 + 3 * u * x * x * 0.25 + x * x * x;
    const dx = 3 * u * u * 0.2 + 6 * u * x * (0.25 - 0.2) + 3 * x * x * (1 - 0.25);
    if (Math.abs(dx) < 0.00001) break;
    x -= (bx - t) / dx;
    x = Math.max(0, Math.min(1, x));
  }
  const u = 1 - x;
  return 3 * u * u * x * 0.85 + 3 * u * x * x + x * x * x;
}

function updateScene(progress, dt) {
  for (let i = 0; i < slots.length; i++) {
    const slot = slots[i];
    const isActive = slot === active;
    const hoverTarget = slot === hovered && !active ? 1 : 0;
    slot.hoverLift = reducedMotion ? hoverTarget * 0.06 : THREE.MathUtils.damp(slot.hoverLift, hoverTarget * 0.06, 14, dt);
    const travel = isActive ? 2.2 * progress : -0.6 * progress;
    const extraLift = isActive ? 0.32 * progress : 0;
    slot.holder.position.set(
      slot.baseX + cameraLocal.x * travel,
      slot.baseY + cameraLocal.y * travel + extraLift + slot.hoverLift,
      slot.baseZ + cameraLocal.z * travel
    );
    if (isActive) {
      slot.holder.rotation.x = -0.32 * progress;
      slot.holder.rotation.y = selectedRotationY * progress;
      slot.holder.scale.setScalar(1 + 0.42 * progress);
      slot.body.scale.x = 1 + 1.05 * progress;
      slot.body.scale.z = 1 - 0.88 * progress;
    } else if (slot.course) {
      slot.body.scale.x = 1;
      slot.body.scale.z = 1;
    }
    const opacity = isActive ? slot.baseOpacity : slot.baseOpacity * (1 - 0.45 * progress);
    for (let m = 0; m < slot.materials.length; m++) {
      const material = slot.materials[m];
      material.opacity = opacity;
      material.depthWrite = opacity > 0.96;
    }
  }

  /* 卡片展开时把相机往后撤一点：取景框是固定的（正交），不后撤就一定被裁。 */
  const targetZoom = 1 - 0.3 * progress;
  if (Math.abs(camera.zoom - targetZoom) > 0.0005){
    camera.zoom += (targetZoom - camera.zoom) * Math.min(1, dt * 9);
    camera.updateProjectionMatrix();
  }
}

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.05);
  if (pointerDirty) {
    pointerDirty = false;
    setHover(active ? null : hitTest(pointerClientX, pointerClientY));
  }

  let progress = active ? 1 : 0;
  let finishedClosing = false;
  if (motion) {
    const raw = Math.min(1, (performance.now() - motion.start) / 420);
    progress = motion.from + (motion.to - motion.from) * easeCubic(raw);
    if (raw >= 1) {
      progress = motion.to;
      finishedClosing = !motion.opening;
      motion = null;
    }
  }
  updateScene(progress, dt);
  if (finishedClosing) {
    const closing = active;
    active = null;
    resetCard(closing);
    setHover(null);
  }
  renderer.render(scene, camera);
});
