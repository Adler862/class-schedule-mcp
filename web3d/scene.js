/* 课程档案架：一列列立着的薄片，一本 = 一周。
   选中那本从架上抽出来、转正、停到画面左侧，右侧浮出这一周的课表。 */
import * as THREE from 'three';

const DATA = window.DATA || { courses: [], maxWeek: 17, start: '2026-08-31' };
/* 参考图里的脊不是"书"，是**极长的长条板**：脊背很窄（W）、高度中等（H）、
   深度方向延伸出去很远（T）。一排平行铺开，靠透视形成"一片"的观感。
   之前 T=0.32 做成的是"书"，怎么调角度都不像。 */
/* 一块档案 = 一张课表：长边与高按 8 列 × 7 行的比例（8:7），
   不再用 8 : 1.3 的细长条。细长条无论怎么转，抽出来都只是一根横杠。 */
const W = 0.17, H = 1.30, T = H * 8 / 7;
/* 板从 8 米缩到 1.5 米之后，0.245 的间距就贴成一堵墙了。
   放到 0.33，板与板之间留出一条缝，才看得出是一格一格。 */
const GAP_X = 0.33;
const LIFT = 1.15;

/* 抽出后的状态：往前拉、转正、缩小、停在左侧 */
const EX = {
  rise: 1.9,        // 从上方拔出：先抬到邻居脊顶之上
  y: 1.55,          // 落定后的中心高度
  scale: 1,         // 不缩放——尺寸靠镜头距离调，缩模型比例就假了
  /* 朝镜头方向带出来一段。不脱离那一排的话，主体和邻居在同一深度上，
     雾没法只吃掉背景，近处那几根会直接盖在主体前面。 */
  out: 10,
  tilt: -0.02,      // 几乎正对；之前 0.18 让板子明显朝左歪
};

if (/[?&]still=1/.test(location.search)) document.body.classList.add('still');

const canvas = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
/* 雾色＝纸色。详情态把 near/far 收到相机跟前，背后整片档案架直接溶进纸里，
   不是"调低不透明度"——那样还会看见轮廓。这是 RhineLabUI scene.ts 的做法：
   fog.near = renderedDistance + lerp(5, -1, detail)，far 同步收到 12。 */
scene.fog = new THREE.Fog(0xe8e5e1, 1000, 2000);
/* 长焦，不是广角。
   去读 RhineLabUI 的 scene.ts 才发现的：它用 `PerspectiveCamera(34, …)` 但把
   **fov 压到 6.15**、相机拉到 84 个单位外。长焦把透视压平，一排脊才会看起来
   "平行"，只在远处轻微收敛——那正是参考图的味道。 */
const camera = new THREE.PerspectiveCamera(8.4, 1, 0.1, 200);
camera.position.set(-15.6, 5.4, 27.4);
camera.lookAt(0.35, 0.95, -1.2);

/* 镜头绕行：档案抽出来之后**不转身**，是我们绕着它走到侧面去看。
   直接 lerp 相机会从直线穿过整排档案，所以用球坐标插值走弧线。
   圆心放在抽出的档案身上，半径/仰角/方位角各走一条。 */
const CAM_PIVOT = new THREE.Vector3(-1.55, 1.35, 0);
const CAM_FROM = new THREE.Spherical(31.06, 1.440, -0.474);   // 初始机位反算
const CAM_TO = new THREE.Spherical(11.8, 1.5708, -1.5708);    // 正对镜头：phi/theta 都摆到轴线上
const camLookAt = new THREE.Vector3();

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
  /* 脊面是架子上唯一露出来的窄面，周次印在这里。
     原来是 7.5px 竖排 NO.xx、只占顶部 1/8，等于看不见。 */
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  /* 脊面只有 0.17 宽，架子上也就几十像素，字号必须顶到边。
     而且整幅铺满——之前只画在上方 40%，UV 一偏就整条全白。 */
  g.fillStyle = '#a8a294';
  g.font = '600 20px "Helvetica Neue", Arial, sans-serif';
  let y = 46;
  for (const c of 'WEEK') {
    g.fillText(c, cw / 2, y);
    y += 46;
  }
  y += 16;
  g.fillStyle = '#151713';
  g.font = '300 40px "Helvetica Neue", Arial, sans-serif';
  for (const c of String(n).padStart(2, '0')) {
    g.fillText(c, cw / 2, y);
    y += 72;
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/* ---------- 极简 GLB 解析 ----------
   Blender 导出的档案板只有几何：3 个 node，每个一个 primitive。
   为了不把 GLTFLoader（约 60KB）拉进单文件，这里只读 POSITION / NORMAL /
   TEXCOORD_0 / indices —— 够用了。 */
function parseGLB(b64) {
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  const dv = new DataView(buf.buffer);
  if (dv.getUint32(0, true) !== 0x46546c67) return null;   // 'glTF'

  let off = 12;
  let json = null;
  let binChunk = null;
  while (off < dv.byteLength) {
    const len = dv.getUint32(off, true);
    const type = dv.getUint32(off + 4, true);
    const start = off + 8;
    if (type === 0x4e4f534a) {
      json = JSON.parse(new TextDecoder().decode(buf.subarray(start, start + len)));
    } else if (type === 0x004e4942) {
      binChunk = buf.subarray(start, start + len);
    }
    off = start + len + ((4 - (len % 4)) % 4);
  }
  if (!json || !binChunk) return null;

  const readAcc = (idx) => {
    const acc = json.accessors[idx];
    const bv = json.bufferViews[acc.bufferView];
    const comp = { 5120: Int8Array, 5121: Uint8Array, 5122: Int16Array,
                   5123: Uint16Array, 5125: Uint32Array, 5126: Float32Array }[acc.componentType];
    const n = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 }[acc.type];
    const base = (bv.byteOffset || 0) + (acc.byteOffset || 0);
    const out = new comp(acc.count * n);
    // 直接按字节拷贝，避免对齐问题
    const src = new Uint8Array(binChunk.buffer, binChunk.byteOffset + base, acc.count * n * comp.BYTES_PER_ELEMENT);
    new Uint8Array(out.buffer).set(src);
    return out;
  };

  /* 先收一遍节点变换：glTF 允许把位移/旋转放在 node 上而不是烘进顶点 */
  const nodeXf = {};
  for (const n of json.nodes || []) {
    if (n.mesh === undefined || !json.meshes[n.mesh]) continue;
    const m = new THREE.Matrix4();
    if (n.matrix) {
      m.fromArray(n.matrix);
    } else {
      m.compose(
        new THREE.Vector3().fromArray(n.translation || [0, 0, 0]),
        new THREE.Quaternion().fromArray(n.rotation || [0, 0, 0, 1]),
        new THREE.Vector3().fromArray(n.scale || [1, 1, 1])
      );
    }
    nodeXf[json.meshes[n.mesh].name] = m;
  }

  const geos = {};
  for (const mesh of json.meshes || []) {
    /* 一个 mesh 可能有多个 primitive（每个对应一个材质槽）。
       拼成一个 geometry，用 groups 记住每段属于哪个材质槽。 */
    const pos = [], nor = [], uvs = [], idx = [];
    const groups = [];
    let vBase = 0, iBase = 0;
    mesh.primitives.forEach((pr, pi) => {
      const P = readAcc(pr.attributes.POSITION);
      const N = pr.attributes.NORMAL !== undefined ? readAcc(pr.attributes.NORMAL) : null;
      const U = pr.attributes.TEXCOORD_0 !== undefined ? readAcc(pr.attributes.TEXCOORD_0) : null;
      const I = pr.indices !== undefined ? readAcc(pr.indices) : null;
      const vCount = P.length / 3;
      for (let i = 0; i < P.length; i++) pos.push(P[i]);
      if (N) for (let i = 0; i < N.length; i++) nor.push(N[i]);
      if (U) for (let i = 0; i < U.length; i++) uvs.push(U[i]);
      if (I) for (let i = 0; i < I.length; i++) idx.push(I[i] + vBase);
      const iCount = I ? I.length : vCount;
      groups.push({ start: iBase, count: iCount, materialIndex: pi });
      vBase += vCount;
      iBase += iCount;
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    if (nor.length) g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
    if (uvs.length && mesh.name === 'archive_body') {
      /* body 有两个材质槽（侧面 / 脊面），各自是一块独立的 UV。
         两个都要分别铺满 0-1，否则脊面上那排 NO.xx 会被拉伸成一片糊。 */
      const idxArr = idx.length ? idx : null;
      for (const gr of groups) {
        const verts = new Set();
        for (let k = gr.start; k < gr.start + gr.count; k++) {
          verts.add(idxArr ? idxArr[k] : k);
        }
        let mnU = 1e9, mxU = -1e9, mnV = 1e9, mxV = -1e9;
        for (const v of verts) {
          const u = uvs[v * 2], vv = uvs[v * 2 + 1];
          if (u < mnU) mnU = u;
          if (u > mxU) mxU = u;
          if (vv < mnV) mnV = vv;
          if (vv > mxV) mxV = vv;
        }
        const du = (mxU - mnU) || 1, dv = (mxV - mnV) || 1;
        for (const v of verts) {
          uvs[v * 2] = (uvs[v * 2] - mnU) / du;
          uvs[v * 2 + 1] = (uvs[v * 2 + 1] - mnV) / dv;
        }
      }
    }
    if (uvs.length) {
      /* cube_project 给的 UV 是按立方体尺寸走的，范围不是 0–1，
         课表只盖住板的一角。这里按包围盒拉回 0–1 正好铺满。
         只对那层纸做——body 有两个材质槽，全局归一化会把编号挤扁。 */
      if (mesh.name !== 'archive_body') {
        /* 只按"朝 -x 的那些顶点"求包围盒——立方体六个面在 UV 空间里是分开的，
           用全局包围盒会把正面挤到一小块里去。 */
        let minU = 1e9, maxU = -1e9, minV = 1e9, maxV = -1e9;
        for (let i = 0, v = 0; i < uvs.length; i += 2, v++) {
          if (nor.length && nor[v * 3] > -0.9) continue;
          if (uvs[i] < minU) minU = uvs[i];
          if (uvs[i] > maxU) maxU = uvs[i];
          if (uvs[i + 1] < minV) minV = uvs[i + 1];
          if (uvs[i + 1] > maxV) maxV = uvs[i + 1];
        }
        if (minU > maxU) { minU = 0; maxU = 1; minV = 0; maxV = 1; }
        const du = (maxU - minU) || 1;
        const dv = (maxV - minV) || 1;
        for (let i = 0; i < uvs.length; i += 2) {
          uvs[i] = (uvs[i] - minU) / du;
          uvs[i + 1] = (uvs[i + 1] - minV) / dv;
        }
      }
      g.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
    }
    if (idx.length) g.setIndex(idx);
    /* 节点上的位移/旋转要自己套上去：face 是靠 node.translation 挪到板前面的，
       只读顶点的话它会正好叠在本体中间。 */
    const nx = nodeXf[mesh.name];
    if (nx) g.applyMatrix4(nx);
    for (const gr of groups) g.addGroup(gr.start, gr.count, gr.materialIndex);
    g.computeBoundingSphere();
    geos[mesh.name] = g;
  }
  return geos;
}

const PARTS = (DATA.glb && DATA.useGlb) ? parseGLB(DATA.glb) : null;

const bodyGeo = new THREE.BoxGeometry(W, H, T);
const capGeo = new THREE.BoxGeometry(W * 0.82, 0.022, T * 0.82);
const labelGeo = new THREE.PlaneGeometry(T, H);

/* 长侧面的标签：档案正对观者时才看得见。
   没有它，抽出来的就是一块空白板——脊上那点 NO.xx 是印在窄端的，
   一转身就背过去了。 */
function makeLabelTexture(w) {
  /* 这块面上印的就是**这一周的课表本身**：8 列（节次 + 七天）、7 行（表头 + 六节），
     和模型 8:7 的长宽比一一对应，所以格子是方的，不会被拉扁。
     远看是一块印满字的面，抽到眼前才读得清。 */
  const cw = 1024, ch = 896;
  const HEAD = 96;
  const colW = cw / 8;
  const BAND = 62;                  // 底部周次带的高度
  const rowH = (ch - HEAD - BAND) / 6;
  const cv = document.createElement('canvas');
  cv.width = cw; cv.height = ch;
  const g = cv.getContext('2d');
  const SANS = '"Helvetica Neue", Arial, sans-serif';

  g.fillStyle = '#f8f6f1';
  g.fillRect(0, 0, cw, ch);

  /* 网格 */
  g.strokeStyle = '#d8d2c5';
  g.lineWidth = 2;
  for (let c = 0; c <= 8; c++) {
    g.beginPath(); g.moveTo(c * colW, 0); g.lineTo(c * colW, ch); g.stroke();
  }
  for (let r = 0; r <= 6; r++) {
    const y = HEAD + r * rowH;
    g.beginPath(); g.moveTo(0, y); g.lineTo(cw, y); g.stroke();
  }

  /* 四角 L 形角标 + 极细外框：让人一眼看出这是"一张有版心的档案"，
     而不是一块随手贴上去的图。参考图里也是这个做法。 */
  g.strokeStyle = '#c9c3b6';
  g.lineWidth = 2;
  g.strokeRect(1, 1, cw - 2, ch - 2);
  g.strokeStyle = '#151713';
  g.lineWidth = 4;
  const corner = 46;
  [[0, 0, 1, 1], [cw, 0, -1, 1], [0, ch, 1, -1], [cw, ch, -1, -1]]
    .forEach(([x, y, dx, dy]) => {
      g.beginPath();
      g.moveTo(x + dx * corner, y);
      g.lineTo(x, y);
      g.lineTo(x, y + dy * corner);
      g.stroke();
    });

  /* 底部周次带：整张纸上唯一"一眼可读"的周次，
     详情态和架子上都看得到。 */
  g.fillStyle = '#151713';
  g.fillRect(0, ch - BAND, cw, BAND);
  g.fillStyle = '#f7f5f0';
  g.textBaseline = 'middle';
  g.font = '600 26px "Helvetica Neue", Arial, sans-serif';
  g.fillText('WEEK ' + pad2(w), 18, ch - BAND / 2);
  g.font = '400 18px "Helvetica Neue", Arial, sans-serif';
  g.fillStyle = '#b8b2a4';
  g.textAlign = 'right';
  const bw0 = isoOf(w, 1), bw1 = isoOf(w, 7);
  g.fillText(pad2(bw0.getMonth() + 1) + '/' + pad2(bw0.getDate())
    + ' – ' + pad2(bw1.getMonth() + 1) + '/' + pad2(bw1.getDate()),
    cw - 18, ch - BAND / 2);
  g.textAlign = 'left';

  /* 表头左上：档案号 */
  g.fillStyle = '#151713';
  g.font = '600 34px ' + SANS;
  g.fillText('NO.' + pad2(w), 16, 40);
  g.fillStyle = '#a8a294';
  g.font = '500 15px ' + SANS;
  g.fillText('WEEK ' + pad2(w), 16, 70);

  /* 表头：七天 */
  for (let d = 1; d <= 7; d++) {
    const x = d * colW;
    const dt = isoOf(w, d);
    g.fillStyle = '#151713';
    g.font = '500 24px ' + SANS;
    g.fillText(DAY_NAMES[d], x + 12, 40);
    g.fillStyle = '#8b8578';
    g.font = '400 16px ' + SANS;
    g.fillText(pad2(dt.getMonth() + 1) + '/' + pad2(dt.getDate()), x + 12, 72);
  }

  /* 节次列 */
  for (let r = 0; r < 6; r++) {
    const y = HEAD + r * rowH;
    const sp = r * 2 + 1;
    g.fillStyle = '#151713';
    g.font = '500 20px ' + SANS;
    g.fillText(sp + '-' + (sp + 1), 12, y + 34);
    const t0 = (DATA.periodTimes && DATA.periodTimes[sp]) || '';
    g.fillStyle = '#a8a294';
    g.font = '400 15px ' + SANS;
    g.fillText(t0, 12, y + 62);
  }

  /* 课程块 */
  const list = weekCourses(w);
  for (const c of list) {
    const r1 = Math.ceil(c.startPeriod / 2);
    const r2 = Math.ceil(c.endPeriod / 2);
    if (r1 < 1 || r1 > 6) continue;
    const span = Math.max(1, Math.min(r2 - r1 + 1, 7 - r1));
    const x = c.day * colW;
    const y = HEAD + (r1 - 1) * rowH;
    const hh = span * rowH;

    g.fillStyle = '#ffffff';
    g.fillRect(x + 3, y + 3, colW - 6, hh - 6);
    g.fillStyle = colorOf(c.name);
    g.fillRect(x + 3, y + 3, 6, hh - 6);

    /* 三行：课名（深、重）/ 地点（灰）/ 老师（更淡），和参考图一致 */
    const name = c.name.length > 7 ? c.name.slice(0, 7) : c.name;
    g.fillStyle = '#1a1b16';
    /* 格宽 128、左边距 14，可用 114；按字数挑字号，宁小不裁 */
    const fs = name.length >= 7 ? 15 : (name.length >= 6 ? 16.5
      : (name.length >= 5 ? 18 : (name.length >= 4 ? 20 : 22)));
    g.font = '600 ' + fs + 'px ' + SANS;
    g.fillText(name, x + 12, y + 28);

    /* 只去掉"东校区"这种前缀，楼名和房间号要留着——
       只显示"208"的话，一眼看不出在哪栋楼 */
    const room = (c.room || c.location || '').replace(/^[东南西北]校区/, '');
    g.fillStyle = '#8b8578';
    g.font = '400 15px ' + SANS;
    g.fillText(room.length > 9 ? room.slice(0, 9) : room, x + 12, y + 54);

    if (c.teacher) {
      g.fillStyle = '#a8a294';
      g.font = '400 14px ' + SANS;
      g.fillText(c.teacher, x + 12, y + 76);
    }
  }

  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

const labelTex = new Map();
function labelTexture(w) {
  if (!labelTex.has(w)) {
    const t = makeLabelTexture(w);
    /* Blender 的 cube_project 给 -x 面的 UV 是转 180° 再镜像的，
       在纹理侧一次性翻正，比在 geometry 上改 UV 省事。 */
    t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
    t.repeat.set(-1, -1);
    t.offset.set(1, 1);
    labelTex.set(w, t);
  }
  return labelTex.get(w);
}
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
const ROWS = 6;                       // 脊变短了，多铺几排才填得满纵深
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
    color: 0xded8cb, roughness: 0.94, metalness: 0,
    transparent: tflag, depthWrite: dflag, opacity: op
  });
  /* 脊顶色标：课程越多越深，饱和度压到 20% 左右 */
  const hue = [212, 350, 127, 264, 42, 180, 317, 95][w % 8];
  const light = busy ? Math.max(34, 62 - list.length * 4) : 70;
  const cap = new THREE.MeshStandardMaterial({
    color: new THREE.Color(`hsl(${hue} 20% ${light}%)`),
    roughness: 0.8, metalness: 0, transparent: true, opacity: busy ? 1 : 0.35
  });
  /* 印刷面：课表直接贴在 GLB 那层纸的 UV 上，不再额外叠一片 plane */
  const print = new THREE.MeshBasicMaterial({ map: labelTexture(w) });
  const set = { side, face, top, cap, print, busy, hRatio: busy ? 1 : 0.62 };
  weekMats.set(w, set);
  return set;
}

for (let c = 0; c < RAIL_N; c++) {
  const w = (c % PERIOD) + 1;
  const base = matSet(w);
  /* 每列克隆一套材质（map 纹理共享），否则 51 列共用同一份，
     "只把其余档案压成背景"就无从下手。 */
  const m = {
    side: base.side.clone(), face: base.face.clone(),
    top: base.top.clone(), cap: base.cap.clone(), print: base.print.clone(),
    busy: base.busy, hRatio: base.hRatio,
  };
  /* 同一周在轨道上会出现三次，高度给一点确定性微差，
     否则 17 列一个循环的重复感一眼就能看出来。 */
  const jit = 0.982 + pseudo(c * 7 + 3) * 0.036;
  const rail = {
    col: c, week: w, x: 0, busy: m.busy,
    baseY: (H * m.hRatio * jit) / 2,
    holders: [], body: null, cap: null,
    hRatio: m.hRatio,
    mats: [m.side, m.face, m.top, m.cap],
    printMat: m.print,
    baseOpacity: m.busy ? 1 : 0.82,
    capOpacity: m.busy ? 1 : 0.35,
    _op: -1,
    lift: 0, ex: 0, spring: { value: 0, velocity: 0 },
  };
  for (let r = 0; r < ROWS; r++) {
    /* 前排用 Blender 出的真模型（倒角 + 一层纸 + 顶部夹），
       后排还是程序化盒子——后排永远只露个边，没必要上精模。 */
    let body;
    if (r === 0 && PARTS && PARTS.archive_body) {
      body = new THREE.Mesh(PARTS.archive_body, [m.side, m.side]);
      if (PARTS.archive_face) {
        const sheet = new THREE.Mesh(PARTS.archive_face, m.print);
        body.add(sheet);
      }
      if (PARTS.archive_clip) {
        const clip = new THREE.Mesh(PARTS.archive_clip, m.top);
        body.add(clip);
      }
    } else {
      body = new THREE.Mesh(bodyGeo, [m.side, m.side, m.top, m.side, m.face, m.side]);
    }
    body.castShadow = r === 0;
    body.receiveShadow = true;
    body.scale.y = m.hRatio * jit;

    const holder = new THREE.Group();
    holder.position.set(0, rail.baseY, -r * T);
    holder.add(body);

    /* 脊顶色标只有最前排看得见，后排建了也是被挡住，白占 250 多个 draw */
    if (r === 0) {
      const cap = new THREE.Mesh(capGeo, m.cap);
      cap.position.set(0, H / 2 + 0.012, 0);
      cap.castShadow = true;
      body.add(cap);
    }

    group.add(holder);
    rail.holders.push(holder);
    if (r === 0) {
      /* 长侧面标签贴在 +x 面上：架子上看是极薄的一条边（等于看不见），
         抽出来转正之后才整个露出来。 */
      const labelMat = labelMaterial(w);
      const front = new THREE.Mesh(labelGeo, labelMat);
      front.visible = false;   // 课表改贴 GLB 的纸面，这层留着只作回退
      body.add(front);
      rail.label = front;
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

/* 邻脊被"带起来"的幅度：按距离延迟 + 衰减振荡，像手指扫过一排档案。
   衰减系数从 0.55 收到 0.26、尾巴从 2.4s 放到 3.2s——照 motion.ts 的包络，
   原来只有紧挨着的一两根动，远一点完全静止，整片看起来还是死的。 */
function neighborWave(distance, age) {
  const t = age - Math.abs(distance) * 0.045;
  if (t <= 0 || t > 3.2) return 0;
  const env = smooth(t / 0.12) * Math.exp(-t * 1.45);
  return (env * Math.cos(t * 7.2)) / (1 + Math.abs(distance) * 0.26);
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

/* 第二维：抽出来的这一周里，当前聚焦的是星期几（1–7）。
   ← → 换周，↑ ↓ 在这一周的七天里翻——和 RhineLabUI 的 lane × row 是同一个意思。 */
let selectedDay = 1;

/* 鼠标停在哪一根上。重构循环阵列时把这个丢了，
   结果光标还在变，脊却一动不动——看着像"悬停效果没了"。 */
let hoverRail = null;
/* 点击脉冲：点下去的那一根立刻弹一下再平息。
   只靠"滚过去再抬起"的话，点到远处的档案会有半秒的"点了没反应"。 */
let pressRail = null;
let pressAt = -99;

let selectedAt = 0;                 // 上次选中的时刻，用来算波纹年龄
let selected = Math.max(0, Math.min(PERIOD - 1, currentWeek() - 1));
/* 面板状态要在这里声明：select() 会读它，而 select 定义在上面。 */
let sheetOpen = false;
let lastSheetWeek = 0;
let focusRail = null;

/* 轨道位置（列单位，带小数）——缓动到 selected，所以柱子是连续滑过去的 */
let railScroll = 0;
/* 焦点横坐标：关着时居中，打开时左移，整条轨道跟着让位。 */
const FOCUS_CLOSED = 0.30, FOCUS_OPEN = 0.78;   // 详情态把模型摆到画面中间偏右
let focusX = FOCUS_CLOSED;
let camK = 0;                       // 镜头绕行进度 0→1

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
  const r = pick(ev);
  hoverRail = r;
  canvas.style.cursor = r ? 'pointer' : 'default';
});
canvas.addEventListener('pointerleave', () => {
  hoverRail = null;
  canvas.style.cursor = 'default';
});
canvas.addEventListener('click', (ev) => {
  const r = pick(ev);
  if (!r) return;
  pressRail = r;
  pressAt = performance.now() / 1000;
  const i = r.week - 1;
  /* 三段式：
     点别的档案 → 只把它提到最高位（预览），不急着开；
     再点同一根   → 才打开课表；
     面板已经开着时点同一根 → 收起。 */
  if (sheetOpen && i === selected) { closeWeekSheet(); return; }
  if (i === selected) { openWeekSheet(r.week); return; }
  select(i);
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

function stepDay(dir) {
  selectedDay += dir;
  if (selectedDay > 7) { selectedDay = 1; select(selected + 1); }
  else if (selectedDay < 1) { selectedDay = 7; select(selected - 1); }
  else { paintOverlay(); if (sheetOpen) syncDay(); }
  syncDayMark();
  if (sheetOpen) syncDay();
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

/* ---------- 第二维：周内聚焦的那一天 ---------- */
function syncDayMark() {
  if (!focusRail || !focusRail.mark) return;
  /* 纹理是 8 列（节次 + 七天），第 d 天占 u ∈ [d/8, (d+1)/8]，
     plane 的 u=0 对应局部 x = -T/2 */
  focusRail.mark.position.z = -T / 2 + ((selectedDay - 0.5) / 8) * T;
}

/* 右侧面板跟着走：标题换成"周三 · 10/28"，清单里那一列标出来 */
function syncDay() {
  const week = selected + 1;
  const dt = isoOf(week, selectedDay);
  setText('wsCat', DAY_NAMES[selectedDay] + ' · '
    + pad2(dt.getMonth() + 1) + '/' + pad2(dt.getDate()));
  document.querySelectorAll('#wsList li').forEach(li => {
    li.classList.toggle('on', +li.dataset.day === selectedDay);
  });
}

/* ---------- 滚动编号 ----------
   周次不是"换一个数字"，而是滚过去。每格是一条 0–9 的竖带（两份首尾相接，
   越过边界时先无动画平移一份，再接上），换周时整条平移。 */
const ROLL_STEP = 1.15;      // 和 CSS 里 .rn 的格高一致

function mountRoll(id, digits) {
  const el = E(id);
  if (!el) return;
  let html = '';
  for (let i = 0; i < digits; i++) {
    html += '<i>';
    for (let copy = 0; copy < 2; copy++) {
      for (let d = 0; d < 10; d++) html += '<b>' + d + '</b>';
    }
    html += '</i>';
  }
  el.innerHTML = html;
  el.__roll = {
    reels: [...el.children],
    pos: new Array(digits).fill(10),
    set: new Array(digits).fill(-1),
  };
}

function rollTo(id, value) {
  const el = E(id);
  const st = el && el.__roll;
  if (!st) return;
  const str = String(Math.max(0, value)).padStart(st.reels.length, '0');
  st.reels.forEach((r, i) => {
    const d = +str[i];
    if (st.set[i] === d) return;
    st.set[i] = d;
    const cur = st.pos[i];
    const curD = ((cur % 10) + 10) % 10;
    let step = d - curD;
    if (step > 5) step -= 10;
    if (step < -5) step += 10;
    let next = cur + step;
    /* 快到头了就先无动画平移一整份（同余，看不出来），再接下一段 */
    if (next > 18 || next < 2) {
      const shift = next > 18 ? -10 : 10;
      const base = cur + shift;
      r.style.transition = 'none';
      r.style.transform = 'translateY(' + (-base * ROLL_STEP) + 'em)';
      void r.offsetWidth;
      r.style.transition = '';
      next = base + step;
    }
    st.pos[i] = next;
    r.style.transform = 'translateY(' + (-next * ROLL_STEP) + 'em)';
  });
}

function paintOverlay() {
  const week = selected + 1;
  const list = weekCourses(week);
  setText('idx', '(' + maxWeek + ')');
  rollTo('bigNum', week);
  setText('totalNum', '/ ' + pad2(maxWeek));
  rollTo('colNum', week);
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
    return '<li data-day="' + c.day + '"><i class="bar" style="--c:' + colorOf(c.name) + '"></i>'
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
  rollTo('wsNum', week);
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
  syncDayMark();
  syncDay();
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
  if (!box) return;
  /* 面板打开时必须把内联 opacity 清掉——它优先级高于 CSS 的
     body.sheet-open #callout{opacity:0}，不清就会留着上一次的 1。 */
  if (!focusRail || sheetOpen) { box.style.opacity = '0'; return; }

  v.set(0, H / 2, 0).applyMatrix4(focusRail.body.matrixWorld);
  v.project(camera);
  const px = (v.x * 0.5 + 0.5) * innerWidth;
  const py = (-v.y * 0.5 + 0.5) * innerHeight;

  /* 标注位置是**设计死的**，不跟着脊跑（照 RhineLabUI 的 .archive-callout 定坐标）。 */
  const wide = innerWidth >= 760;
  /* 模型现在占满画面中间，标注放 40% / 20% 正好压在板上。
     挪到右侧那条空白带，只留一个小圆点贴在脊顶。 */
  const bx = wide ? Math.round(innerWidth * 0.775) : 24;
  const by = wide ? Math.round(innerHeight * 0.40) : 96;
  box.style.setProperty('--bx', bx + 'px');
  box.style.setProperty('--by', by + 'px');
  box.style.setProperty('--dx2', px.toFixed(1) + 'px');

  /* 引线是**水平**的：方块在脊顶，线从方块向远处拉，文字浮在线的上方。 */
  const line = box.querySelector('.line');
  if (line) {
    const ly = Math.max(py, by + 110);          // 别穿过文字块
    const lw = Math.max(180, innerWidth * 0.42);
    line.style.width = '0px';
    box.style.setProperty('--dy2', ly.toFixed(1) + 'px');
    box.style.setProperty('--actTop', '108px');   // 动作条固定在方块下面，别跑去模型顶上
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

/* 板子不转身——朝向靠镜头绕过去解决；这里只留一个占位变量 */
let ckNow = 0;

function tick(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  const time = now / 1000;
  const age = time - selectedAt;

  /* 焦点横坐标跟着面板开合，整条轨道因此整体让位到左半边 */
  /* 镜头绕行的进度先算：柱阵列要按它压暗背景，得在相机段之前就有值 */
  /* 抽出和绕镜头同时进行，但整体压到 0.4 秒左右做完。
     试过"先抽出、再绕过去"，结果中间那 0.3 秒更难看：镜头已经绕到侧面、
     档案还没离架，画面上是一排别人的侧脸。与其细调过程，不如让它快到看不清。 */
  camK += ((sheetOpen ? 1 : 0) - camK) * Math.min(1, dt * (reduce ? 40 : 6.0));
  const ck = smooth(camK);
  ckNow = ck;

  group.updateMatrixWorld();
  /* y 用板中心而不是 1.35：正对时视点高一点低一点，板就整体上移/下移 */
  CAM_PIVOT.set(FOCUS_OPEN - EX.out * ck, 1.35 + (EX.y - 1.35) * ck, 0);
  group.localToWorld(CAM_PIVOT);

  const fxTarget = sheetOpen ? FOCUS_OPEN : FOCUS_CLOSED;
  focusX += (fxTarget - focusX) * Math.min(1, dt * (reduce ? 40 : 4.2));

  /* 轨道缓动：按环形最短路径逼近，所以 17 → 1 是往前滑一格，不是倒着走 16 格 */
  const fx = focusX / GAP_X;
  let delta = (selected - fx - railScroll) % PERIOD;
  if (delta > PERIOD / 2) delta -= PERIOD;
  if (delta < -PERIOD / 2) delta += PERIOD;
  railScroll += reduce ? delta : delta * Math.min(1, dt * 7.5);
  /* 取模周期必须是 RAIL_N*PERIOD，不能是 PERIOD。
     柱子位置函数的周期是 RAIL_N(51)，只有"周次"的周期是 PERIOD(17)。
     按 17 归一化时，railScroll 每越过 17，center 会瞬间掉 17 列，
     而 17 不是 51 的倍数 —— 整排柱子就会"啪"地跳一下，这就是到头那一下顿感。 */
  railScroll %= RAIL_N * PERIOD;

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
    /* 悬停抬起：比选中弱，但足够看得出"这一根是活的" */
    if (r === hoverRail && !isFocus) target = Math.max(target, 0.2);
    if (r === pressRail) {
      const pt = time - pressAt;
      if (pt >= 0 && pt < 1.2) target = Math.max(target, 0.6 * Math.exp(-pt * 5));
    }
    if (!reduce && !isFocus) {
      target += neighborWave(r.col - focusRail.col, age) * 0.22;
    }
    if (!reduce) target += idleBreath(r.col, time);
    if (reduce) { r.spring.value = target; r.spring.velocity = 0; }
    else springDamp(r.spring, target, 9, dt);
    r.lift = r.spring.value;

    /* 抽出进度由"离焦点的远近"直接算，不再用「是不是焦点列」这个布尔量。
       那个布尔量在缓动过程中会在相邻两列之间来回翻，ex 目标跟着 0/1 跳，
       模型就一抽一缩地抖。改成位置的连续函数，滑过去就是平滑交接。 */
    const exTarget = sheetOpen ? smooth(clamp01((w - 0.5) / 0.5)) : 0;
    r.ex += (exTarget - r.ex) * Math.min(1, dt * (reduce ? 40 : 5.2));

    const e = clamp01(r.ex);
    const e1 = smooth(clamp01(e / 0.5));                  // 先从上方拔出
    const e2 = smooth(clamp01((e - 0.34) / 0.66));        // 再转身 + 缩小 + 落位
    /* 拔起然后再落回来：拔的那一段完全退掉，不叠加到最终高度上 */
    const py = r.baseY + LIFT * r.lift * (1 - e2)
      + EX.rise * e1 * (1 - e2) + (EX.y - r.baseY) * e2;
    const sc = 1 + (EX.scale - 1) * e2;

    /* 详情态把其余档案压到几乎看不见。雾做不到：同一排的邻居和主体
       距离只差一两个单位，雾会把它们和主体一起糊掉。 */
    const dim = isFocus ? 1 : 1 - 0.94 * ck;
    for (let mi = 0; mi < 4; mi++) {
      const mt = r.mats[mi];
      const baseOp = mi === 3 ? r.capOpacity : r.baseOpacity;
      const op2 = baseOp * dim;
      if (Math.abs((mt.opacity || 0) - op2) > 0.004) {
        mt.opacity = op2;
        mt.transparent = op2 < 0.999;
        mt.depthWrite = op2 > 0.96;
      }
    }
    if (r.printMat && Math.abs(r.printMat.opacity - dim) > 0.004) {
      r.printMat.transparent = dim < 0.999;
      r.printMat.opacity = dim;
    }

    /* 只有第 0 排会抬、会拔；**不转身**——转的是镜头，不是档案。
       后排是背景，跟着横向滑动就够。 */
    /* 架子上空周矮一截是"这一周没课"的记号；
       抽出来看的时候不该还矮着——那是内容为空，不是档案尺寸不同。 */
    r.body.scale.y = r.hRatio + (1 - r.hRatio) * e2;

    const front = r.holders[0];
    /* 朝镜头方向（-x）带出来，脱离那一排 */
    front.position.set(r.x - EX.out * e2, py, 0);
    front.rotation.y = 0;
    front.scale.setScalar(sc);
    /* 标签跟着拔出进度淡入，塞回去时一起消失 */
    if (r.mark) r.mark.visible = e2 > 0.4;
    /* 周次标签只在架子上有用；详情态板上已经印着 NO.xx / WEEK xx，
       而且它不吃 dim，会变成几块飘在画面里的白牌子。 */
    if (r.tag) r.tag.visible = ck < 0.35;
    r.labelMat.opacity = e2;
    for (let row = 1; row < ROWS; row++) {
      const h = r.holders[row];
      h.position.set(r.x, r.baseY, -row * T);
      /* 焦点那一根的"纵深副本"是假的：抽出来之后如果还留着，
         它们在侧视里会并排成一堵墙，把主体自己埋掉。 */
      h.visible = !(isFocus && ck > 0.15);
    }
  }

  /* 镜头绕过去看：位置走球面弧线，注视点在圆心上再往右挪一点，
     这样档案落在画面左半边，右边留给课表。 */
  /* 按画面比例算"刚好装得下板宽"的距离。
     fov 定的是竖直视野，横向可见宽度 = 2·R·tan(fov/2)·aspect，
     竖屏 aspect 只有 0.46，1.55 倍远远不够（视野宽才 1.24，板宽 1.486）。
     这里直接解出 R，横屏时算出来比 11.8 小，取 max 后桌面行为不变。 */
  const aspect = Math.max(0.28, innerWidth / innerHeight);
  const tanHalf = Math.tan((camera.fov * Math.PI / 180) / 2);
  const fitR = 1.66 / (2 * tanHalf * aspect);        // 1.486 的板 + 一点留白
  const toR = Math.min(26, Math.max(CAM_TO.radius, fitR));

  const sph = new THREE.Spherical(
    CAM_FROM.radius + (toR - CAM_FROM.radius) * ck,
    CAM_FROM.phi + (CAM_TO.phi - CAM_FROM.phi) * ck,
    CAM_FROM.theta + (CAM_TO.theta - CAM_FROM.theta) * ck
  );
  camera.position.setFromSpherical(sph).add(CAM_PIVOT);

  /* 雾跟着相机距离走：关着时推到无穷远（等于没有），
     打开时收到主角前后十来个单位，背景那一排就消失了。 */
  /* 雾要跑在镜头前面：镜头绕行的中途会从斜上方掠过整排档案，
     那一瞬间画面上全是顶面的条纹。前段拉快，过半时背景已经吃干净。 */
  const fogK = Math.pow(ck, 0.4);
  const camDist = camera.position.distanceTo(CAM_PIVOT);
  scene.fog.near = camDist + (1 - fogK) * 900 - fogK * 1.0;
  scene.fog.far = camDist + (1 - fogK) * 1800 + fogK * 8;

  const vd = CAM_PIVOT.clone().sub(camera.position).setY(0).normalize();
  camLookAt.copy(CAM_PIVOT)
    .addScaledVector(new THREE.Vector3(-vd.z, 0, vd.x), 0 * ck);
  camera.lookAt(camLookAt);

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
mountRoll('bigNum', 2);
mountRoll('colNum', 2);
mountRoll('wsNum', 2);
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
