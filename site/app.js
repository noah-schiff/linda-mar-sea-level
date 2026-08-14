/* Linda Mar Sea Level Explorer
 *
 * Terrain is the present-day USGS 3DEP DEM and never changes. The water-level
 * slider drives a shader uniform that tints submerged ground (so flood extent
 * reads from any camera angle, not just where the water plane is edge-on), and
 * the year slider swaps which satellite-derived shorelines are drawn.
 *
 * All geometry is in metres, with the origin at the DEM's south-west corner:
 * x = east, z = north, y = elevation. Vertical exaggeration is a scale on the
 * parent group, so the shader still compares true elevations in metres.
 */

import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const MHHW = 1.798;
const SHORELINE_LIFT = 1.0;      // metres above ground, so lines don't z-fight
const RIBBON_WIDTH = 14;         // metres; WebGL ignores line width, so use quads

const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement)
  .getPropertyValue(name).trim();

/* ------------------------------------------------------------------ load */

async function loadAll(onProgress) {
  const j = async (p) => (await fetch(p)).json();
  const b = async (p) => (await fetch(p)).arrayBuffer();

  onProgress('Loading terrain…');
  const terrainMeta = await j('./data/terrain.json');
  const terrainBuf = await b('./data/terrain.bin');

  onProgress('Loading shorelines…');
  const shoreMeta = await j('./data/shorelines.json');
  const shoreBuf = await b('./data/shorelines.bin');

  onProgress('Loading records…');
  const sealevel = await j('./data/sealevel.json');
  const summary = await j('./data/summary.json');

  return { terrainMeta, heights: new Int16Array(terrainBuf), shoreMeta,
           shoreXY: new Int16Array(shoreBuf), sealevel, summary };
}

/* --------------------------------------------------------------- terrain */

// Muted earth ramp. Terrain is context; the blue water is the data.
function terrainColor(elev, out) {
  const stops = [
    [-20, 0.29, 0.38, 0.46], [MHHW - 0.01, 0.55, 0.64, 0.71],
    [MHHW, 0.94, 0.91, 0.84], [12, 0.83, 0.80, 0.68],
    [45, 0.70, 0.71, 0.57], [110, 0.55, 0.57, 0.46],
    [280, 0.44, 0.44, 0.39],
  ];
  let i = 0;
  while (i < stops.length - 2 && elev > stops[i + 1][0]) i++;
  const a = stops[i], c = stops[i + 1];
  const t = Math.min(1, Math.max(0, (elev - a[0]) / (c[0] - a[0])));
  out[0] = a[1] + (c[1] - a[1]) * t;
  out[1] = a[2] + (c[2] - a[2]) * t;
  out[2] = a[3] + (c[3] - a[3]) * t;
}

function buildTerrain(meta, heights) {
  const { rows, cols, spacing_m: sp, height_scale: hs } = meta;
  const n = rows * cols;
  const pos = new Float32Array(n * 3);
  const col = new Float32Array(n * 3);
  const rgb = [0, 0, 0];

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const i = r * cols + c;
      const y = heights[i] * hs;
      pos[i * 3] = c * sp;
      pos[i * 3 + 1] = y;
      pos[i * 3 + 2] = r * sp;
      terrainColor(y, rgb);
      col[i * 3] = rgb[0]; col[i * 3 + 1] = rgb[1]; col[i * 3 + 2] = rgb[2];
    }
  }

  // 547k vertices, so indices must be 32-bit.
  const idx = new Uint32Array((rows - 1) * (cols - 1) * 6);
  let k = 0;
  for (let r = 0; r < rows - 1; r++) {
    for (let c = 0; c < cols - 1; c++) {
      const a = r * cols + c, b = a + 1, d = a + cols, e = d + 1;
      idx[k++] = a; idx[k++] = d; idx[k++] = b;
      idx[k++] = b; idx[k++] = d; idx[k++] = e;
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  geo.setIndex(new THREE.BufferAttribute(idx, 1));
  geo.computeVertexNormals();

  const mat = new THREE.MeshStandardMaterial({
    vertexColors: true, roughness: 0.96, metalness: 0.0,
  });

  // Tint submerged ground. vElev is OBJECT-space y -- true metres, unaffected
  // by the exaggeration scale on the parent group -- so the comparison against
  // uWaterLevel stays correct at any exaggeration.
  const uniforms = {
    uWaterLevel: { value: MHHW },
    uWaterColor: { value: new THREE.Color(0x11406f) },
  };
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uWaterLevel = uniforms.uWaterLevel;
    shader.uniforms.uWaterColor = uniforms.uWaterColor;
    shader.vertexShader = 'varying float vElev;\n' + shader.vertexShader.replace(
      '#include <begin_vertex>',
      '#include <begin_vertex>\n  vElev = position.y;'
    );
    shader.fragmentShader =
      'uniform float uWaterLevel;\nuniform vec3 uWaterColor;\nvarying float vElev;\n' +
      shader.fragmentShader.replace(
        '#include <dithering_fragment>',
        `#include <dithering_fragment>
         float depth = uWaterLevel - vElev;
         if (depth > 0.0) {
           float t = clamp(0.30 + depth / 6.0, 0.30, 0.86);
           gl_FragColor.rgb = mix(gl_FragColor.rgb, uWaterColor, t);
         }`
      );
  };
  mat.customProgramCacheKey = () => 'terrain-flood-v1';

  const mesh = new THREE.Mesh(geo, mat);
  mesh.userData.uniforms = uniforms;
  return mesh;
}

/* Vertical walls dropped from the DEM's four edges down to a base plane, so
 * the tile reads as a solid block of ground rather than a floating shell. */
function buildSkirt(meta, heights, baseY) {
  const { rows, cols, spacing_m: sp, height_scale: hs } = meta;
  const edges = [];
  for (let c = 0; c < cols; c++) edges.push([c * sp, 0, heights[c]]);
  for (let r = 0; r < rows; r++) edges.push([(cols - 1) * sp, r * sp, heights[r * cols + cols - 1]]);
  for (let c = cols - 1; c >= 0; c--) edges.push([c * sp, (rows - 1) * sp, heights[(rows - 1) * cols + c]]);
  for (let r = rows - 1; r >= 0; r--) edges.push([0, r * sp, heights[r * cols]]);

  const pos = new Float32Array(edges.length * 2 * 3);
  for (let i = 0; i < edges.length; i++) {
    const [x, z, h] = edges[i];
    pos[i * 6] = x; pos[i * 6 + 1] = h * hs; pos[i * 6 + 2] = z;
    pos[i * 6 + 3] = x; pos[i * 6 + 4] = baseY; pos[i * 6 + 5] = z;
  }
  const idx = new Uint32Array((edges.length - 1) * 6);
  let k = 0;
  for (let i = 0; i < edges.length - 1; i++) {
    const a = i * 2, b = a + 1, c = a + 2, d = a + 3;
    idx[k++] = a; idx[k++] = b; idx[k++] = c;
    idx[k++] = c; idx[k++] = b; idx[k++] = d;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setIndex(new THREE.BufferAttribute(idx, 1));
  geo.computeVertexNormals();
  return new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
    color: 0x8d887c, roughness: 1.0, metalness: 0.0, side: THREE.DoubleSide,
  }));
}

/* Bilinear terrain sampler, clamped at the edges. Some shoreline points sit
 * ~49 m west of the DEM, out over open water -- clamping returns the seaward
 * edge height rather than NaN, which would poison the vertex buffer. */
function makeSampler(meta, heights) {
  const { rows, cols, spacing_m: sp, height_scale: hs } = meta;
  return (wx, wz) => {
    let fc = wx / sp, fr = wz / sp;
    fc = Math.min(cols - 1.001, Math.max(0, fc));
    fr = Math.min(rows - 1.001, Math.max(0, fr));
    const c0 = Math.floor(fc), r0 = Math.floor(fr);
    const tc = fc - c0, tr = fr - r0;
    const h00 = heights[r0 * cols + c0], h10 = heights[r0 * cols + c0 + 1];
    const h01 = heights[(r0 + 1) * cols + c0], h11 = heights[(r0 + 1) * cols + c0 + 1];
    return (h00 * (1 - tc) * (1 - tr) + h10 * tc * (1 - tr) +
            h01 * (1 - tc) * tr + h11 * tc * tr) * hs;
  };
}

/* ------------------------------------------------------------ shorelines */

function makeDequantiser(shoreMeta, terrainMeta) {
  const q = shoreMeta.quantisation;
  return (qx, qy) => [
    q.x_min + ((qx - q.int16_offset) / q.int16_range) * q.span_x - terrainMeta.x0_utm,
    q.y_min + ((qy - q.int16_offset) / q.int16_range) * q.span_y - terrainMeta.y0_utm,
  ];
}

/* Every pass as one LineSegments; parts are already grouped by year in the
 * binary, so switching years is a setDrawRange call, not a rebuild. */
function buildPasses(shoreMeta, shoreXY, deq, sample) {
  const parts = shoreMeta.parts;
  let segs = 0;
  for (const [, count] of parts) segs += count - 1;

  const pos = new Float32Array(segs * 2 * 3);
  const segStart = new Int32Array(parts.length + 1);
  let v = 0;

  for (let p = 0; p < parts.length; p++) {
    segStart[p] = v / 3 / 2;
    const [off, count] = parts[p];
    let [px, pz] = deq(shoreXY[off * 2], shoreXY[off * 2 + 1]);
    let py = Math.max(sample(px, pz), MHHW) + SHORELINE_LIFT;
    for (let i = 1; i < count; i++) {
      const o = (off + i) * 2;
      const [cx, cz] = deq(shoreXY[o], shoreXY[o + 1]);
      const cy = Math.max(sample(cx, cz), MHHW) + SHORELINE_LIFT;
      pos[v++] = px; pos[v++] = py; pos[v++] = pz;
      pos[v++] = cx; pos[v++] = cy; pos[v++] = cz;
      px = cx; py = cy; pz = cz;
    }
  }
  segStart[parts.length] = v / 3 / 2;

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.LineBasicMaterial({
    color: new THREE.Color(css('--raw') || '#c3c2b7'),
    transparent: true, opacity: 0.5, depthWrite: false,
  });
  const obj = new THREE.LineSegments(geo, mat);
  obj.userData.segStart = segStart;
  return obj;
}

/* A flat ribbon along a polyline. WebGL ignores LineBasicMaterial.linewidth on
 * essentially every platform, so a real quad strip is the only way to get a
 * shoreline that reads as a line rather than a hairline. */
function ribbonGeometry(pts, sample, width) {
  if (pts.length < 2) return null;
  const half = width / 2;
  const pos = new Float32Array(pts.length * 2 * 3);
  for (let i = 0; i < pts.length; i++) {
    const prev = pts[Math.max(0, i - 1)], next = pts[Math.min(pts.length - 1, i + 1)];
    let dx = next[0] - prev[0], dz = next[1] - prev[1];
    const len = Math.hypot(dx, dz) || 1;
    // Perpendicular in the ground plane.
    const nx = -dz / len * half, nz = dx / len * half;
    const [x, z] = pts[i];
    const y = Math.max(sample(x, z), MHHW) + SHORELINE_LIFT + 0.4;
    pos[i * 6] = x - nx; pos[i * 6 + 1] = y; pos[i * 6 + 2] = z - nz;
    pos[i * 6 + 3] = x + nx; pos[i * 6 + 4] = y; pos[i * 6 + 5] = z + nz;
  }
  const idx = new Uint32Array((pts.length - 1) * 6);
  let k = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const a = i * 2, b = a + 1, c = a + 2, d = a + 3;
    idx[k++] = a; idx[k++] = c; idx[k++] = b;
    idx[k++] = b; idx[k++] = c; idx[k++] = d;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setIndex(new THREE.BufferAttribute(idx, 1));
  return geo;
}

/* ----------------------------------------------------------- chart panel */

function drawChart(sealevel) {
  const W = 400, H = 132, L = 34, R = 6, T = 8, B = 18;
  const years = sealevel.year;
  const vals = sealevel.monthly_mm.filter((v) => v !== null);
  const yMin = Math.min(...vals), yMax = Math.max(...vals);
  const xMin = years[0], xMax = years[years.length - 1];

  const sx = (x) => L + ((x - xMin) / (xMax - xMin)) * (W - L - R);
  const sy = (y) => T + (1 - (y - yMin) / (yMax - yMin)) * (H - T - B);

  // Split on nulls so gaps in the record aren't bridged by a straight line.
  const path = (series) => {
    const out = [];
    let open = false;
    for (let i = 0; i < series.length; i++) {
      const v = series[i];
      if (v === null) { open = false; continue; }
      out.push(`${open ? 'L' : 'M'}${sx(years[i]).toFixed(1)} ${sy(v).toFixed(1)}`);
      open = true;
    }
    return out.join('');
  };

  const yTicks = [-200, -100, 0, 100, 200].filter((t) => t > yMin && t < yMax);
  const xTicks = [1875, 1925, 1975, 2025].filter((t) => t > xMin && t < xMax);

  const svg = `
<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="San Francisco monthly mean sea level, 1854 to present, rising about 1.98 millimetres per year">
  ${yTicks.map((t) => `<line x1="${L}" x2="${W - R}" y1="${sy(t).toFixed(1)}" y2="${sy(t).toFixed(1)}" stroke="var(--grid)" stroke-width="1"/>`).join('')}
  ${yTicks.map((t) => `<text x="${L - 5}" y="${(sy(t) + 3).toFixed(1)}" text-anchor="end" font-size="8.5" fill="var(--muted)">${t}</text>`).join('')}
  ${xTicks.map((t) => `<text x="${sx(t).toFixed(1)}" y="${H - 5}" text-anchor="middle" font-size="8.5" fill="var(--muted)">${t}</text>`).join('')}
  <path d="${path(sealevel.monthly_mm)}" fill="none" stroke="var(--raw)" stroke-width="0.7"/>
  <path d="${path(sealevel.rolling_mm)}" fill="none" stroke="var(--water)" stroke-width="1.5"/>
  <line x1="${sx(sealevel.trend.x[0]).toFixed(1)}" y1="${sy(sealevel.trend.y[0]).toFixed(1)}"
        x2="${sx(sealevel.trend.x[1]).toFixed(1)}" y2="${sy(sealevel.trend.y[1]).toFixed(1)}"
        stroke="var(--trend)" stroke-width="2" stroke-linecap="round"/>
  <text x="${L - 5}" y="${T + 4}" text-anchor="end" font-size="8" fill="var(--muted)">mm</text>
</svg>`;
  $('chart').innerHTML = svg;
  $('trend-label').textContent = `Trend ${sealevel.trend.slope_mm_per_yr.toFixed(2)} mm/yr`;
}

/* A soft vertical gradient standing in for sky, drawn once into a 2x64 canvas.
 * Reads its two stops from the CSS tokens so it follows the light/dark theme. */
function skyTexture() {
  const c = document.createElement('canvas');
  c.width = 2; c.height = 64;
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, 0, 64);
  g.addColorStop(0, css('--scene-top') || '#dfe6ec');
  g.addColorStop(1, css('--scene-bottom') || '#f3f1ea');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 2, 64);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/* ------------------------------------------------------------------ main */

async function main() {
  const canvas = $('scene');
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  } catch (err) {
    $('loading').hidden = true;
    $('webgl-error').hidden = false;
    console.error('WebGL unavailable:', err);
    return;
  }

  const data = await loadAll((t) => { $('loading-text').textContent = t; });
  const { terrainMeta: tm, heights, shoreMeta, shoreXY, sealevel, summary } = data;

  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  scene.background = skyTexture();
  scene.fog = new THREE.Fog(new THREE.Color(css('--scene-bottom') || '#f3f1ea'),
                            8000, 26000);
  const camera = new THREE.PerspectiveCamera(
    48, canvas.clientWidth / canvas.clientHeight, 2, 60000);

  const group = new THREE.Group();
  scene.add(group);

  const terrain = buildTerrain(tm, heights);
  group.add(terrain);
  const uniforms = terrain.userData.uniforms;
  const sample = makeSampler(tm, heights);

  const baseY = tm.min_m - 45;
  group.add(buildSkirt(tm, heights, baseY));

  // Water runs far past the DEM so its edge never shows -- the fog dissolves
  // it into the sky instead, which reads as open ocean to the horizon.
  const pad = 30000;
  const waterGeo = new THREE.PlaneGeometry(tm.width_m + pad * 2, tm.depth_m + pad * 2);
  waterGeo.rotateX(-Math.PI / 2);
  const water = new THREE.Mesh(waterGeo, new THREE.MeshStandardMaterial({
    color: new THREE.Color(0x2a78d6), transparent: true, opacity: 0.46,
    roughness: 0.18, metalness: 0.1, depthWrite: false,
  }));
  water.position.set(tm.width_m / 2, MHHW, tm.depth_m / 2);
  water.renderOrder = 1;
  group.add(water);

  // Shorelines
  const deq = makeDequantiser(shoreMeta, tm);
  const passes = buildPasses(shoreMeta, shoreXY, deq, sample);
  passes.renderOrder = 2;
  group.add(passes);

  const medianMat = new THREE.MeshBasicMaterial({
    color: 0xffffff, side: THREE.DoubleSide, transparent: true, opacity: 0.95,
    depthWrite: false,
  });
  const medianMesh = new THREE.Mesh(new THREE.BufferGeometry(), medianMat);
  medianMesh.renderOrder = 4;
  group.add(medianMesh);

  const baselinePts = shoreMeta.baseline.map(([x, y]) => [x - tm.x0_utm, y - tm.y0_utm]);
  const baselineGeo = ribbonGeometry(baselinePts, sample, RIBBON_WIDTH * 0.8);
  const baseline = new THREE.Mesh(baselineGeo, new THREE.MeshBasicMaterial({
    color: new THREE.Color(0xeb6834), side: THREE.DoubleSide,
    transparent: true, opacity: 0.9, depthWrite: false,
  }));
  baseline.renderOrder = 3;
  group.add(baseline);

  // Lighting: one key light from the north-west (the classic relief convention)
  // plus fill, so the landforms read without hard shadows.
  scene.add(new THREE.HemisphereLight(0xdfe8f0, 0x54514a, 1.15));
  const key = new THREE.DirectionalLight(0xfff6e8, 1.5);
  key.position.set(-1, 1.4, 0.7);
  scene.add(key);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.maxPolarAngle = Math.PI * 0.492;   // never go under the terrain
  controls.minDistance = 400;
  controls.maxDistance = 22000;
  controls.target.set(tm.width_m * 0.44, 0, tm.depth_m * 0.48);
  // Three-quarter aerial from the south-west, out over the ocean looking
  // inland, high enough to see down into the valley and the creek floodplain.
  camera.position.set(-2000, 2900, -1100);
  controls.update();

  /* ---------- state ---------- */
  const steps = summary.water_steps;
  const years = Object.keys(shoreMeta.years).map(Number).sort((a, b) => a - b);
  // 276 m of relief across a 3.5 km scene is a 0.08 ratio -- flat-looking at
  // 1x, but a sheer wall past ~4x. 2.5x reads as real hills while still
  // making the 2 m of sea level rise perceptible.
  let exag = 2.5;

  function applyExaggeration(v) {
    exag = v;
    group.scale.y = v;
    $('exag-label').textContent = `${v}×`;
  }

  function setWater(i) {
    const s = steps[i];
    uniforms.uWaterLevel.value = s.level_m;
    water.position.y = s.level_m;
    $('ro-level').textContent = `${s.level_m.toFixed(2)} m / ${s.level_ft.toFixed(1)} ft`;
    $('ro-rise').textContent = s.rise_m === 0 ? '— (today)' : `+${s.rise_m.toFixed(2)} m`;
    $('ro-area').textContent = s.rise_m === 0
      ? '0 ha (baseline)'
      : `${s.newly_flooded_ha.toLocaleString(undefined, { maximumFractionDigits: 1 })} ha`;
  }

  function setYear(i) {
    const year = years[i];
    const [firstPart, nParts] = shoreMeta.years[String(year)];
    const segStart = passes.userData.segStart;
    const start = segStart[firstPart];
    const end = segStart[firstPart + nParts];
    passes.geometry.setDrawRange(start * 2, (end - start) * 2);

    const pts = (shoreMeta.median_by_year[String(year)] || [])
      .map(([x, y]) => [x - tm.x0_utm, y - tm.y0_utm]);
    const geo = ribbonGeometry(pts, sample, RIBBON_WIDTH);
    medianMesh.geometry.dispose();
    medianMesh.geometry = geo || new THREE.BufferGeometry();

    const covered = shoreMeta.coverage_by_year[String(year)];
    const nT = shoreMeta.n_transects;
    $('ro-year').textContent = String(year);
    // Satellite passes, not polyline parts -- one pass usually contributes
    // several disconnected coastline pieces.
    $('ro-passes').textContent = String(shoreMeta.passes_by_year[String(year)]);
    $('ro-coverage').textContent = covered < nT
      ? `Only ${covered} of ${nT} transects had a usable detection this year — the annual line skips the rest.`
      : '';
  }

  /* ---------- UI ---------- */
  $('stats').innerHTML = summary.headline.map((s) => `
    <div>
      <dt>${s.n}. ${s.label}</dt>
      <dd>${s.value}</dd>
      <div class="sub">${s.sub}</div>
    </div>`).join('');

  drawChart(sealevel);

  $('water-ticks').innerHTML =
    `<span>Today</span><span>2100 Int.</span><span>2100 High</span>`;
  $('year-ticks').innerHTML =
    `<span>${years[0]}</span><span>${years[Math.floor(years.length / 2)]}</span><span>${years[years.length - 1]}</span>`;

  const waterSlider = $('water');
  const yearSlider = $('year');
  waterSlider.max = String(steps.length - 1);
  yearSlider.max = String(years.length - 1);
  yearSlider.value = String(years.length - 1);

  waterSlider.addEventListener('input', (e) => setWater(+e.target.value));
  yearSlider.addEventListener('input', (e) => setYear(+e.target.value));
  $('exag').addEventListener('input', (e) => applyExaggeration(+e.target.value));
  $('show-passes').addEventListener('change', (e) => { passes.visible = e.target.checked; });
  $('show-baseline').addEventListener('change', (e) => { baseline.visible = e.target.checked; });

  let playing = null;
  $('play').addEventListener('click', () => {
    const btn = $('play');
    if (playing) {
      clearInterval(playing); playing = null;
      btn.textContent = '▶'; btn.setAttribute('aria-label', 'Play shoreline animation');
      return;
    }
    btn.textContent = '❚❚'; btn.setAttribute('aria-label', 'Pause shoreline animation');
    playing = setInterval(() => {
      const next = (+yearSlider.value + 1) % years.length;
      yearSlider.value = String(next);
      setYear(next);
    }, 420);
  });

  applyExaggeration(exag);
  setWater(0);
  setYear(years.length - 1);

  /* ---------- resize + render ---------- */
  const resize = () => {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  addEventListener('resize', resize);
  resize();

  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
  });

  const loading = $('loading');
  loading.classList.add('done');
  setTimeout(() => { loading.hidden = true; }, 450);

  console.log('[linda-mar] ready:',
    `${tm.rows}x${tm.cols} terrain, ${shoreMeta.parts.length} shoreline parts, ` +
    `${years.length} years, ${steps.length} water levels`);
}

main().catch((err) => {
  console.error('[linda-mar] fatal:', err);
  $('loading-text').textContent = 'Something went wrong loading the scene.';
});
