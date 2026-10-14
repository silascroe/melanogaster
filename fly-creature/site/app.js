// Page wiring for the live demo: loads the obstacle brain copy, advances the
// Creature (creature.js) in step with the clock, and draws the neurons, the
// cartoon arena and the MDN trace. When the device cannot keep up, the whole
// world runs in slow motion and the header says so; it never skips brain time.

import { Creature, SETTINGS } from "./creature.js";
import { seededRandom } from "./brain.js";

const COMPUTE_BUDGET_MS = 12;    // per animation frame
const METER_MAX_HZ = 30;
const S = SETTINGS;

const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

async function load() {
  const get = (path, as) => fetch(path).then((r) => {
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r[as]();
  });
  const [meta, buffer] = await Promise.all([
    get("data/obstacle_brain_v4.json", "json"),
    get("data/obstacle_brain_v4.bin", "arrayBuffer"),
  ]);
  return { meta, buffer };
}

function main({ meta, buffer }) {
  const params = new URLSearchParams(location.search);
  const seed = Number(params.get("seed")) || Math.floor(Math.random() * 2 ** 32);
  const world = new Creature(meta, buffer, { seed });
  const { n, kind, xy, fly } = world;
  let paused = false;

  // ---- drawing ----------------------------------------------------------
  const colors = {};
  for (const k of ["paper-bright", "paper-deep", "line-strong", "muted", "text",
    "teal", "blue", "amber", "magenta"]) colors[k] = css(`--${k}`);
  const sans = css("--sans");
  const serif = css("--serif");
  const spaced = (text) => text.toUpperCase().split("").join(" ");
  // Text with a paper-coloured halo, readable on top of the neuron dots.
  const label = (g, text, x, y) => {
    g.save();
    g.lineWidth = 3.5;
    g.lineJoin = "round";
    g.strokeStyle = colors["paper-bright"];
    g.strokeText(text, x, y);
    g.restore();
    g.fillText(text, x, y);
  };

  function sizeCanvas(canvas) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    return { dpr, w: rect.width, h: rect.height };
  }

  const brainCanvas = $("brain");
  const bctx = brainCanvas.getContext("2d");
  const base = document.createElement("canvas");
  const layout = { scale: 1, ox: 0, oy: 0, dpr: 1, w: 0, h: 0 };
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (let i = 0; i < n; i++) {
    minX = Math.min(minX, xy[2 * i]); maxX = Math.max(maxX, xy[2 * i]);
    minY = Math.min(minY, xy[2 * i + 1]); maxY = Math.max(maxY, xy[2 * i + 1]);
  }
  const px = (i) => layout.ox + (xy[2 * i] - minX) * layout.scale;
  const py = (i) => layout.oy + (xy[2 * i + 1] - minY) * layout.scale;
  const centroid = (cells) => {
    let sx = 0, sy = 0;
    for (const i of cells) { sx += px(i); sy += py(i); }
    return [sx / cells.length, sy / cells.length];
  };

  function layoutBrain() {
    const { dpr, w, h } = sizeCanvas(brainCanvas);
    Object.assign(layout, { dpr, w, h });
    const padX = 64, padY = 20;
    layout.scale = Math.min((w - 2 * padX) / (maxX - minX), (h - 2 * padY) / (maxY - minY));
    layout.ox = (w - (maxX - minX) * layout.scale) / 2;
    layout.oy = (h - (maxY - minY) * layout.scale) / 2;
    base.width = brainCanvas.width;
    base.height = brainCanvas.height;
    const g = base.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.fillStyle = colors["paper-bright"];
    g.fillRect(0, 0, w, h);
    g.fillStyle = colors["line-strong"];
    g.globalAlpha = 0.5;
    for (let i = 0; i < n; i++) g.fillRect(px(i) - 0.8, py(i) - 0.8, 1.6, 1.6);
    g.globalAlpha = 1;
    // Cell bodies sort into the brain (top) and the ventral nerve cord (below).
    g.font = `600 10px ${sans}`;
    g.fillStyle = colors.muted;
    for (const [text, frac] of [["brain", 0.15], ["nerve cord", 0.7]]) {
      g.save();
      g.translate(14, layout.oy + frac * (maxY - minY) * layout.scale);
      g.rotate(-Math.PI / 2);
      g.textAlign = "center";
      g.fillText(spaced(text), 0, 0);
      g.restore();
    }
  }

  const palette = () => [colors.teal, colors.amber, colors.blue, colors.magenta];
  function drawBrain() {
    const { dpr, w } = layout;
    bctx.setTransform(1, 0, 0, 1, 0, 0);
    bctx.drawImage(base, 0, 0);
    bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const heat = world.heat;
    const colorsByKind = palette();
    for (let k = 0; k < 4; k++) {
      bctx.fillStyle = colorsByKind[k];
      for (let i = 0; i < n; i++) {
        if (kind[i] !== k) continue;
        const h = heat[i];
        if (h < 0.04) continue;
        const r = k >= 2 ? 1.6 + 2.2 * h : 1.1 + 1.8 * h;
        bctx.globalAlpha = Math.min(1, 0.25 + h);
        bctx.fillRect(px(i) - r, py(i) - r, 2 * r, 2 * r);
      }
    }
    bctx.globalAlpha = 1;

    // MDN: four cells by the midline, ringed whether or not they fire.
    const [mx, my] = centroid(world.mdnCells);
    const cut = world.condition === "disconnected";
    bctx.strokeStyle = colors.magenta;
    bctx.lineWidth = 1.5;
    bctx.setLineDash(cut ? [3, 3] : []);
    bctx.beginPath();
    bctx.arc(mx, my, 11 + 6 * Math.min(1, world.mdnHz / 20), 0, Math.PI * 2);
    bctx.stroke();
    bctx.setLineDash([]);
    bctx.font = `600 11px ${sans}`;
    bctx.fillStyle = colors.magenta;
    bctx.textAlign = "left";
    label(bctx, cut ? "MDN ×4 · inputs cut" : "MDN ×4", mx + 22, my + 4);

    // Foreleg label to the right of the whole cluster, not on top of it.
    const [, fy] = centroid(world.foreleg);
    let right = 0;
    for (const i of world.foreleg) right = Math.max(right, px(i));
    const lx = Math.min(right + 12, w - 112);
    bctx.fillStyle = colors.blue;
    label(bctx, "foreleg touch", lx, fy - 4);
    bctx.font = `italic 10.5px ${serif}`;
    bctx.fillStyle = colors.muted;
    label(bctx, "position approximate", lx, fy + 9);
  }

  const arena = $("arena");
  const actx = arena.getContext("2d");
  let arenaLayout = { dpr: 1, w: 0, h: 0, scale: 1 };

  // A few fixed sugar grains so the cube reads as sugar, not a box.
  const grains = Array.from({ length: 26 }, (_, k) => {
    const r = seededRandom(1000 + k);
    return [(r() - 0.5) * 0.8, (r() - 0.5) * 0.8, 0.012 + r() * 0.018];
  });

  function drawFly(g) {
    const touching = world.input;
    g.save();
    g.translate(fly.x, fly.y);
    g.rotate(fly.heading);
    g.lineCap = "round";
    g.lineWidth = 0.035;
    // Legs: three per side; the forelegs reach the contact point.
    const legs = [[0.06, S.reachM, 0.13], [-0.02, 0.05, 0.3], [-0.08, -0.32, 0.27]];
    legs.forEach(([root, tipX, tipY], k) => {
      for (const side of [-1, 1]) {
        g.strokeStyle = k === 0 && touching ? colors.blue : "#5a3a22";
        g.beginPath();
        g.moveTo(root, side * 0.06);
        g.quadraticCurveTo((root + tipX) / 2 + 0.03, side * tipY * 0.95, tipX, side * tipY);
        g.stroke();
      }
    });
    if (touching) {
      g.fillStyle = colors.blue;
      for (const side of [-1, 1]) {
        g.globalAlpha = 0.25;
        g.beginPath(); g.arc(S.reachM, side * 0.13, 0.07, 0, Math.PI * 2); g.fill();
        g.globalAlpha = 1;
        g.beginPath(); g.arc(S.reachM, side * 0.13, 0.025, 0, Math.PI * 2); g.fill();
      }
    }
    // Wings folded back over the abdomen.
    g.fillStyle = "rgba(150, 170, 178, 0.42)";
    g.strokeStyle = "rgba(90, 100, 105, 0.5)";
    g.lineWidth = 0.008;
    for (const side of [-1, 1]) {
      g.save();
      g.translate(-0.02, side * 0.04);
      g.rotate(Math.PI + side * 0.18);
      g.beginPath(); g.ellipse(0.22, 0, 0.24, 0.075, 0, 0, Math.PI * 2); g.fill(); g.stroke();
      g.restore();
    }
    // Abdomen with bands, thorax, head, red eyes.
    g.fillStyle = "#6e4426";
    g.beginPath(); g.ellipse(-0.2, 0, 0.17, 0.11, 0, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "rgba(30, 18, 10, 0.55)";
    g.lineWidth = 0.02;
    for (const bx of [-0.15, -0.23, -0.3]) {
      g.beginPath(); g.moveTo(bx, -0.095); g.quadraticCurveTo(bx - 0.03, 0, bx, 0.095); g.stroke();
    }
    g.fillStyle = "#a0692f";
    g.beginPath(); g.ellipse(0.03, 0, 0.11, 0.095, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#8b5a2b";
    g.beginPath(); g.ellipse(0.17, 0, 0.055, 0.075, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#b8392b";
    for (const side of [-1, 1]) {
      g.beginPath(); g.ellipse(0.175, side * 0.06, 0.045, 0.035, 0, 0, Math.PI * 2); g.fill();
    }
    g.restore();
  }

  function drawArena() {
    const { dpr, w, h, scale } = arenaLayout;
    actx.setTransform(dpr, 0, 0, dpr, 0, 0);
    actx.clearRect(0, 0, w, h);
    actx.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * w / 2, dpr * h / 2);
    actx.fillStyle = colors["line-strong"];
    for (let k = 0; k < fly.trail.length; k += 2) {
      actx.globalAlpha = 0.15 + 0.5 * (k / fly.trail.length);
      actx.beginPath(); actx.arc(fly.trail[k], fly.trail[k + 1], 0.018, 0, Math.PI * 2); actx.fill();
    }
    actx.globalAlpha = 1;
    const c = S.cubeHalfM;
    actx.fillStyle = "rgba(60, 50, 40, 0.14)";
    actx.fillRect(-c + 0.07, -c + 0.09, 2 * c, 2 * c);
    actx.fillStyle = "#fffdf8";
    actx.strokeStyle = colors["line-strong"];
    actx.lineWidth = 0.015;
    actx.fillRect(-c, -c, 2 * c, 2 * c);
    actx.strokeRect(-c, -c, 2 * c, 2 * c);
    actx.fillStyle = colors["paper-deep"];
    for (const [gx, gy, r] of grains) actx.fillRect(gx - r, gy - r, 2 * r, 2 * r);
    drawFly(actx);
    actx.setTransform(dpr, 0, 0, dpr, 0, 0);
    actx.font = `600 10.5px ${sans}`;
    actx.textAlign = "left";
    actx.fillStyle = fly.mode === "backing" ? colors.magenta : colors.muted;
    actx.fillText(spaced(fly.mode), 12, 20);
    actx.fillStyle = colors.muted;
    actx.font = `italic 11px ${serif}`;
    actx.textAlign = "center";
    actx.fillText("sugar cube", w / 2, h / 2 + c * scale + 16);
  }

  const trace = $("trace");
  const tctx = trace.getContext("2d");
  let traceLayout = { dpr: 1, w: 0, h: 0 };
  function drawTrace() {
    const { dpr, w, h } = traceLayout;
    const history = world.history;
    tctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    tctx.clearRect(0, 0, w, h);
    let top = 24;
    for (const f of history) top = Math.max(top, f.hz);
    const y = (hz) => h - 2 - (hz / top) * (h - 6);
    const dx = w / S.historyReads;
    const x0 = w - history.length * dx;
    tctx.fillStyle = colors.blue;
    tctx.globalAlpha = 0.13;
    history.forEach((f, k) => { if (f.input) tctx.fillRect(x0 + k * dx, 0, dx + 0.5, h); });
    tctx.globalAlpha = 1;
    tctx.strokeStyle = colors.text;
    tctx.setLineDash([4, 4]);
    tctx.lineWidth = 1;
    tctx.beginPath(); tctx.moveTo(0, y(S.backupHz)); tctx.lineTo(w, y(S.backupHz)); tctx.stroke();
    tctx.setLineDash([]);
    if (history.length > 1) {
      tctx.beginPath();
      tctx.moveTo(x0, h);
      history.forEach((f, k) => tctx.lineTo(x0 + (k + 1) * dx, y(f.hz)));
      tctx.lineTo(w, h);
      tctx.closePath();
      tctx.fillStyle = colors.magenta;
      tctx.globalAlpha = 0.18;
      tctx.fill();
      tctx.globalAlpha = 1;
      tctx.beginPath();
      history.forEach((f, k) => (k ? tctx.lineTo(x0 + (k + 1) * dx, y(f.hz)) : tctx.moveTo(x0 + dx, y(f.hz))));
      tctx.strokeStyle = colors.magenta;
      tctx.lineWidth = 1.6;
      tctx.stroke();
    }
    tctx.fillStyle = colors.muted;
    tctx.font = `10px ${sans}`;
    tctx.textAlign = "left";
    tctx.fillText("8 Hz", 4, y(S.backupHz) - 3);
    tctx.fillText("last 6 s · blue = foreleg input", 4, 11);
  }

  // ---- readouts -----------------------------------------------------------
  const el = {
    status: $("status"), speed: $("speed"), input: $("input"), action: $("action"),
    mdn: $("mdn"), bar: $("mdn-bar"), threshold: $("mdn-threshold"), firing: $("firing"), wiring: $("wiring"),
  };
  el.threshold.style.left = `${(S.backupHz / METER_MAX_HZ) * 100}%`;
  let speedText = "starting…";
  function updateReadouts() {
    el.input.textContent = world.input ? (world.contact ? "touching" : "on (button)") : "off";
    el.action.textContent = fly.mode;
    el.action.className = "v" + (fly.mode === "backing" ? " action-backing" : fly.mode === "pressing" ? " action-pressing" : "");
    el.mdn.textContent = `${world.mdnHz.toFixed(1)} Hz${world.backing ? " · backing" : ""}`;
    el.bar.style.width = `${Math.min(100, (world.mdnHz / METER_MAX_HZ) * 100)}%`;
    el.firing.textContent = world.active ? world.firingLastRead.toLocaleString() : "0 (at rest)";
    el.speed.textContent = paused ? "paused" : speedText;
  }

  const clock = { realMs: 0, simMs: 0 };
  let computeMark = 0, brainMark = 0;
  function updateSpeed() {
    if (clock.realMs < 1000) return;
    const factor = clock.simMs / clock.realMs;
    const brainMs = world.brainSimMs - brainMark;
    const perRead = brainMs ? ((world.computeMs - computeMark) / brainMs) * S.readMs : null;
    speedText = (factor >= 0.97 ? "real time" : `${factor.toFixed(2)}× real time (slow motion)`) +
      (perRead === null ? " · brain at rest" : ` · ${perRead.toFixed(1)} ms of compute per 50 ms of brain`);
    clock.realMs = clock.simMs = 0;
    computeMark = world.computeMs;
    brainMark = world.brainSimMs;
  }

  // ---- controls -------------------------------------------------------------
  const touch = $("touch");
  const setTouch = (on) => {
    world.touchHeld = on;
    touch.classList.toggle("on", on);
    touch.setAttribute("aria-pressed", String(on));
  };
  touch.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    touch.setPointerCapture?.(e.pointerId);
    setTouch(true);
  });
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) touch.addEventListener(type, () => setTouch(false));
  touch.addEventListener("keydown", (e) => {
    if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); setTouch(true); }
  });
  touch.addEventListener("keyup", (e) => { if (e.key === " " || e.key === "Enter") setTouch(false); });
  touch.addEventListener("blur", () => setTouch(false));
  touch.addEventListener("contextmenu", (e) => e.preventDefault());

  const cutButton = $("cut");
  cutButton.addEventListener("click", () => {
    const cut = world.condition === "intact";
    world.setCondition(cut ? "disconnected" : "intact");
    cutButton.classList.toggle("on", cut);
    cutButton.setAttribute("aria-pressed", String(cut));
    cutButton.textContent = cut ? "Restore wiring onto MDN" : "Cut wiring onto MDN";
    el.wiring.textContent = cut ? "cut onto MDN" : "intact";
    setStatus();
  });

  const pauseButton = $("pause");
  pauseButton.addEventListener("click", () => {
    paused = !paused;
    pauseButton.classList.toggle("on", paused);
    pauseButton.setAttribute("aria-pressed", String(paused));
    pauseButton.textContent = paused ? "Resume" : "Pause";
  });

  function setStatus() {
    el.status.classList.remove("loading");
    el.status.textContent = world.condition === "intact"
      ? "Running live · intact wiring" : "Running live · wiring onto MDN cut";
  }

  // ---- loop -----------------------------------------------------------------
  function resize() {
    layoutBrain();
    arenaLayout = sizeCanvas(arena);
    arenaLayout.scale = arenaLayout.w / (2 * S.arenaHalfW);
    traceLayout = sizeCanvas(trace);
  }
  new ResizeObserver(resize).observe(document.querySelector(".demo"));
  resize();
  setStatus();

  let last = performance.now();
  let debt = 0;
  function frame(now) {
    const real = Math.min(now - last, 100);
    last = now;
    if (!paused) {
      debt += real;
      clock.realMs += real;
      const t0 = performance.now();
      let advanced = 0;
      while (debt >= S.chunkMs) {
        if (performance.now() - t0 > COMPUTE_BUDGET_MS) { debt = 0; break; }
        world.chunk();
        debt -= S.chunkMs;
        advanced += S.chunkMs;
      }
      clock.simMs += advanced;
      if (advanced) world.fade(advanced);
      updateSpeed();
    }
    drawBrain();
    drawArena();
    drawTrace();
    updateReadouts();
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

load().then(main).catch((error) => {
  $("status").textContent = "Could not load the wiring";
  console.error(error);
});
