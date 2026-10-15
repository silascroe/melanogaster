// Home page: replays recorded runs of the game's brain copies on the 3D map.
// Data comes from tools/export_web_replays.py. Every number shown is read from
// the recording; the stories only say which neurons were driven and read, and
// which rules are ours.

import { MapView } from "./map3d.js";

const SENSE_RGB = {
  taste: [0.878, 0.651, 0.227], loom: [0.890, 0.416, 0.310], target: [0.310, 0.639, 0.878],
  touch: [0.435, 0.812, 0.557], obstacle: [0.843, 0.478, 0.690],
};
const HEAT_TAU_MS = 45;      // brain-time fade of a neuron's glow after it fires
const LOOP_PAUSE_MS = 900;   // real time to hold the last frame before looping

// Display names for the package groups the replays drive and read.
const GROUP_NAMES = {
  loom: "LC4 + LPLC2", sugar: "sugar LB3", bitter: "bitter LB1", lc10a_R: "right LC10a",
  jo_ce: "Johnston’s organ C/E", foreleg: "foreleg bristles", gf: "giant fibre", mn9: "MN9",
  dna02_R: "DNa02 right", dna02_L: "DNa02 left", pip10: "pIP10", adn: "aDN", mdn: "MDN",
};

const fmt = (x) => Math.round(x).toLocaleString("en-US");
const hz = (x) => `${x >= 10 ? Math.round(x) : x.toFixed(1)} Hz`;

// One entry per recorded reaction. Rules marked "ours" are the game's engineering.
const SCENARIOS = [
  {
    name: "jump", label: "Jump", sub: "something looms", sense: "loom",
    readout: "Giant fibre", series: [{ key: "gf", label: "giant fibre (DNp01), per 25 ms", raw: true }],
    rule: "Ours: the game jumps on the first giant-fibre spike.",
    story: (s) => `
      <p><b>Driven:</b> ${s.inputCells} LC4 and LPLC2 neurons, visual cells that respond to something
        growing fast in view, at 150 Hz for 0.3 s.</p>
      <p><b>Read:</b> the two giant-fibre neurons (DNp01), the fly’s escape command.
        ${s.cut ? "With the wiring onto them cut they never fire, so there is no jump, though the rest of the map still lights up."
          : `They fire at about ${hz(s.mean)} from the first 25 ms of input.`}</p>
      <p class="fine">Whole brain: 404 Hz; the best of 20 shuffled brains, 34.5 Hz.</p>`,
  },
  {
    name: "feed", label: "Feed", sub: "sugar on the mouth", sense: "taste",
    readout: "MN9", threshold: 20, series: [{ key: "mn9", label: "MN9, smoothed" }, { key: "mn9", label: "per 25 ms", raw: true }],
    rule: "Ours: the fly feeds while smoothed MN9 is at least 20 Hz.",
    story: (s) => `
      <p><b>Driven:</b> ${s.inputCells} LB3 sugar/water taste neurons on the mouthparts, at 150 Hz for 1 s.</p>
      <p><b>Read:</b> MN9, the two motor neurons that push the proboscis out.
        ${s.cut ? "Cut, they stay silent. Notice also how much less of the map joins in: cutting the action neurons changes the whole copy’s activity here."
          : `About ${hz(s.mean)} while the sugar is there, silent within 25 ms of it going.`}</p>
      <p class="fine">Whole brain: 66–78 Hz; 0 Hz in all 20 shuffled brains.</p>`,
  },
  {
    name: "bitter", label: "Refuse", sub: "sugar laced with bitter", sense: "taste",
    readout: "MN9", threshold: 20, series: [{ key: "mn9", label: "MN9, smoothed" }, { key: "mn9", label: "per 25 ms", raw: true }],
    rule: "Ours: the fly feeds while smoothed MN9 is at least 20 Hz.",
    story: (s) => `
      <p><b>Driven:</b> the same sugar neurons plus ${s.extraCells} LB1 bitter neurons, together, for 1 s.</p>
      <p><b>Read:</b> MN9 again. ${s.cut ? "Cut, it never fires." :
        `During contact it barely fires (${hz(s.mean)}): bitter vetoes sugar. Then a flaw shows: in the half
        second after the drop is gone, leftover activity drives MN9 to about ${hz(s.after)}, enough to count as
        feeding under our rule. We saw this in 6 of 6 runs and have not traced why.`}</p>
      <p class="fine">Whole brain: sugar plus bitter 0–1 Hz. When the bitter cells’ outputs were rewired at
        random, at most a third of the suppression was left.</p>`,
  },
  {
    name: "turn", label: "Turn & sing", sub: "a target to the right", sense: "target",
    readout: "Turn rate", threshold: 30, thresholdKey: "pip10",
    series: [{ key: "asym", label: "DNa02 right − left, smoothed" }, { key: "pip10", label: "pIP10 song, smoothed", alt: true }],
    rule: "Ours: turn rate follows the DNa02 difference; the fly sings while smoothed pIP10 is at least 30 Hz.",
    story: (s) => `
      <p><b>Driven:</b> ${s.inputCells} right-side LC10a neurons, visual cells that track a small moving
        object, at 150 Hz for 1 s.</p>
      <p><b>Read:</b> the left and right DNa02 steering neurons, and pIP10, the courtship-song command.
        ${s.cut ? "Cut, all three stay silent: no turn, no song." :
        `Right DNa02 fires at about ${hz(s.mean)} and left stays silent, so the fly turns right; pIP10
        crosses the song threshold too.`}</p>
      <p class="fine">Whole brain: DNa02 difference 104–168 Hz, pIP10 38–47 Hz; both beat all 20 shuffled brains.</p>`,
  },
  {
    name: "groom", label: "Groom", sub: "dust on the antennae", sense: "touch",
    readout: "aDN", threshold: 30, series: [{ key: "adn", label: "aDN, smoothed" }, { key: "adn", label: "per 25 ms", raw: true }],
    rule: "Ours: the fly grooms while smoothed aDN is at least 30 Hz.",
    story: (s) => `
      <p><b>Driven:</b> ${s.inputCells} Johnston’s organ neurons (zones C and E), which sense the antenna
        being pushed, at 150 Hz for 1 s.</p>
      <p><b>Read:</b> the four aDN descending neurons, linked to antennal grooming in real flies.
        ${s.cut ? "Cut, they stay silent and the fly never grooms." :
        `About ${hz(s.mean)}. Note they keep firing after the dust is gone, until the game resets the copy.`}</p>
      <p class="fine">Whole brain: 199–204 Hz; the best of 20 shuffled brains, 3.25 Hz.</p>`,
  },
  {
    name: "backup", label: "Back up", sub: "forelegs against a wall", sense: "obstacle",
    readout: "MDN", threshold: 8, series: [{ key: "mdn", label: "MDN, smoothed" }, { key: "mdn", label: "per 25 ms", raw: true }],
    rule: "Ours: the fly backs up once smoothed MDN reaches 8 Hz.",
    story: (s) => `
      <p><b>Driven:</b> ${s.inputCells} touch-bristle neurons on both forelegs, at 150 Hz for 1 s.</p>
      <p><b>Read:</b> the four “moonwalker” neurons (MDN) that make a fly walk backwards.
        ${s.cut ? "Cut, they stay dark." :
        `About ${hz(s.mean)}. This copy stays calm: about ${fmt(s.peak)} neurons at most, not ten thousand.`}
        It is small enough to <a href="backing-up/">run live in your browser</a>.</p>
      <p class="fine">Whole brain: 16–17 Hz; beats all 20 shuffled brains.</p>`,
  },
];

const $ = (id) => document.getElementById(id);

async function fetchGz(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  if (typeof DecompressionStream === "undefined") throw new Error("this browser cannot unpack the data (no DecompressionStream)");
  const stream = r.body.pipeThrough(new DecompressionStream("gzip"));
  return new Response(stream).arrayBuffer();
}

async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function typed(buffer, spec) {
  const T = { int16: Int16Array, uint8: Uint8Array, uint16: Uint16Array, uint32: Uint32Array }[spec.dtype];
  return new T(buffer, spec.offset, spec.length);
}

class Atlas {
  constructor(meta, buffer) {
    this.meta = meta;
    const a = meta.arrays;
    const raw = typed(buffer, a.xyz);
    this.n = meta.n;
    this.xyz = new Float32Array(raw.length);
    for (let i = 0; i < raw.length; i++) this.xyz[i] = raw[i] * meta.xyz_scale;
    this.approximate = typed(buffer, a.approximate);
    this.type = typed(buffer, a.type);
    this.superclass = typed(buffer, a.superclass);
    this.bodyId = typed(buffer, a.body_id);
    this.view = new MapView($("map"), this.xyz, this.n);
    this.cache = new Map();
    this.condition = 0;           // 0 intact, 1 cut
    this.speed = 0.25;
    this.playing = true;
    this.t = 0;                   // brain time, ms
    this.lastFrame = -1;
    this.hold = 0;
    this.drag = null;
    this.autoYaw = true;          // gentle sway until the visitor drags
    this.sway = 0;
    this.hover = -1;
    $("approx-count").textContent = fmt(meta.approximate_count);
    // Which side is which, from the recorded side labels (before any turning).
    $("hud-note").textContent = meta.left_x_sign > 0
      ? "brain on top · the fly’s right is on your left"
      : "brain on top · the fly’s right is on your right";
    this.buildButtons();
    this.bindInput();
  }

  buildButtons() {
    const box = $("scenarios");
    for (const sc of SCENARIOS) {
      const b = document.createElement("button");
      b.style.setProperty("--sense", `var(--sense-${sc.sense})`);
      b.innerHTML = `<b>${sc.label}</b><span>${sc.sub}</span>`;
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", () => this.select(sc.name));
      sc.button = b;
      box.append(b);
    }
  }

  bindInput() {
    const setCondition = (c) => {
      this.condition = c;
      $("intact").setAttribute("aria-pressed", String(c === 0));
      $("cut").setAttribute("aria-pressed", String(c === 1));
      this.rebuildHeat();
      this.refreshText();
      this.drawChart();
      this.refreshLive();
    };
    $("intact").addEventListener("click", () => setCondition(0));
    $("cut").addEventListener("click", () => setCondition(1));
    $("play").addEventListener("click", () => this.setPlaying(!this.playing));
    $("restart").addEventListener("click", () => { this.seek(0); this.setPlaying(true); });
    for (const b of document.querySelectorAll(".speed button")) {
      b.addEventListener("click", () => {
        this.speed = Number(b.dataset.speed);
        for (const o of document.querySelectorAll(".speed button")) o.setAttribute("aria-pressed", String(o === b));
      });
    }
    $("scrub").addEventListener("input", (e) => {
      this.setPlaying(false);
      this.seek(Number(e.target.value) / 1000 * this.totalMs());
    });

    const el = $("specimen");
    el.addEventListener("pointerdown", (e) => {
      this.drag = { x: e.clientX, y: e.clientY, yaw: this.view.yaw, pitch: this.view.pitch };
      this.autoYaw = false;
      el.classList.add("dragging");
      el.setPointerCapture(e.pointerId);
    });
    el.addEventListener("pointermove", (e) => {
      const rect = el.getBoundingClientRect();
      if (this.drag) {
        this.view.yaw = this.drag.yaw + (e.clientX - this.drag.x) * 0.008;
        this.view.pitch = Math.max(-0.9, Math.min(0.9, this.drag.pitch + (e.clientY - this.drag.y) * 0.006));
        this.hideTip();
        return;
      }
      if (e.pointerType === "mouse") this.showTip(e.clientX - rect.left, e.clientY - rect.top);
    });
    const end = () => { this.drag = null; el.classList.remove("dragging"); };
    el.addEventListener("pointerup", (e) => {
      const moved = this.drag && Math.hypot(e.clientX - this.drag.x, e.clientY - this.drag.y) > 4;
      end();
      if (!moved && e.pointerType !== "mouse") {
        const rect = el.getBoundingClientRect();
        this.showTip(e.clientX - rect.left, e.clientY - rect.top);
      }
    });
    el.addEventListener("pointercancel", end);
    el.addEventListener("pointerleave", () => { if (!this.drag) this.hideTip(); });
    window.addEventListener("resize", () => this.drawChart());
  }

  setPlaying(on) {
    this.playing = on;
    $("play").textContent = on ? "Pause" : "Play";
    $("play").setAttribute("aria-pressed", String(!on));
  }

  async select(name) {
    const sc = SCENARIOS.find((s) => s.name === name);
    for (const s of SCENARIOS) s.button.setAttribute("aria-pressed", String(s === sc));
    let data = this.cache.get(name);
    if (!data) {
      $("status").className = "status-pill loading";
      $("status").textContent = "Loading the recording…";
      const [meta, bits] = await Promise.all([
        fetchJson(`data/replay_${name}.json`), fetchGz(`data/replay_${name}.bin`)]);
      data = { meta, bits: new Uint8Array(bits) };
      data.kinds = this.kindsFor(sc, meta);
      data.facts = [0, 1].map((c) => this.factsFor(sc, meta, c));
      this.cache.set(name, data);
    }
    this.sc = sc;
    this.data = data;
    this.view.setKinds(data.kinds);
    this.view.setSense(SENSE_RGB[sc.sense]);
    $("specimen").style.setProperty("--sense", `var(--sense-${sc.sense})`);
    $("copy-note").textContent = `${fmt(data.meta.package_neurons)}-neuron copy`;
    $("chart-title").textContent = sc.series.filter((s) => !s.raw).map((s) => s.label.split(",")[0]).join(" and ") || sc.series[0].label;
    $("fact-readout-k").textContent = sc.readout;
    $("status").className = "status-pill";
    $("status").textContent = `Replaying: ${sc.label.toLowerCase()} · recorded, seed ${data.meta.seed}`;
    this.buildTags(data.meta);
    this.seek(0);
    this.setPlaying(true);
    this.refreshText();
    this.drawChart();
  }

  // 0 outside this copy, 1 in it, 2 named input cells, 3 named readout cells.
  kindsFor(sc, meta) {
    const kinds = new Float32Array(this.n);
    const member = Uint8Array.from(atob(this.meta.packages[meta.package]), (ch) => ch.charCodeAt(0));
    for (let i = 0; i < this.n; i++) kinds[i] = (member[i >> 3] >> (i & 7)) & 1;
    for (const cells of Object.values(meta.cells.inputs)) for (const c of cells) kinds[c] = 2;
    for (const cells of Object.values(meta.cells.readouts)) for (const c of cells) kinds[c] = 3;
    return kinds;
  }

  factsFor(sc, meta, c) {
    const cond = meta.conditions[c === 0 ? "intact" : "disconnected"];
    const fr = meta.frame_ms;
    const on = Math.round(meta.rest_ms / fr), off = on + Math.round(meta.stimulus_ms / fr);
    const key = sc.series[0].key === "asym" ? "dna02_R" : sc.series[0].key;
    const mean = (arr, a, b) => arr.slice(a, b).reduce((x, y) => x + y, 0) / Math.max(1, b - a);
    const cellsOf = (g) => (meta.cells.inputs[g] || []).length;
    return {
      cut: c === 1,
      mean: mean(cond.rates_hz[key], on, off),
      after: mean(cond.rates_hz[key], off, off + Math.round(meta.reset_after_ms / fr)),
      peak: Math.max(...cond.neurons_fired),
      inputCells: fmt(cellsOf(meta.inputs[0])),
      extraCells: fmt(cellsOf("bitter")),
    };
  }

  totalMs() { return this.data.meta.frames * this.data.meta.frame_ms; }

  seek(ms) {
    this.t = Math.max(0, Math.min(ms, this.totalMs() - 1e-6));
    this.hold = 0;
    this.rebuildHeat();
    this.refreshLive();
  }

  // Recompute glow from the recent frames (after a seek or a wiring switch).
  rebuildHeat() {
    const heat = this.view.heat;
    heat.fill(0);
    const meta = this.data.meta, fr = meta.frame_ms;
    const frame = Math.floor(this.t / fr);
    const from = Math.max(0, frame - Math.ceil((HEAT_TAU_MS * 6) / fr));
    for (let f = from; f <= frame; f++) {
      const decay = Math.exp(-fr / HEAT_TAU_MS);
      for (let i = 0; i < this.n; i++) heat[i] *= decay;
      this.light(f);
    }
    this.lastFrame = frame;
  }

  light(f) {
    const { meta, bits } = this.data;
    const bpf = meta.bytes_per_frame;
    const base = (this.condition * meta.frames + f) * bpf;
    const heat = this.view.heat;
    let count = 0;
    for (let b = 0; b < bpf; b++) {
      const byte = bits[base + b];
      if (!byte) continue;
      for (let k = 0; k < 8; k++) {
        if (byte & (1 << k)) { heat[b * 8 + k] = 1; count++; }
      }
    }
    return count;
  }

  tick(dtReal) {
    if (!this.data) return;
    dtReal = Math.max(0, dtReal);  // the first frame's timestamp can precede start()
    const meta = this.data.meta, fr = meta.frame_ms, total = this.totalMs();
    if (this.autoYaw && !this.drag) {
      this.sway += Math.min(dtReal, 100);
      this.view.yaw = 0.55 * Math.sin(this.sway * 0.00022);
    }
    if (this.playing) {
      if (this.t >= total - 1e-6) {
        this.hold += dtReal;
        if (this.hold > LOOP_PAUSE_MS) this.seek(0);
      } else {
        const dtBrain = Math.min(dtReal, 100) * this.speed;
        this.t = Math.min(total - 1e-6, this.t + dtBrain);
        const decay = Math.exp(-dtBrain / HEAT_TAU_MS);
        const heat = this.view.heat;
        for (let i = 0; i < this.n; i++) heat[i] *= decay;
        const frame = Math.floor(this.t / fr);
        for (let f = this.lastFrame + 1; f <= frame; f++) this.light(f);
        this.lastFrame = frame;
      }
    }
    this.view.draw();
    this.placeTags();
    this.refreshLive();
  }

  refreshLive() {
    const meta = this.data.meta, fr = meta.frame_ms;
    const f = Math.max(0, Math.min(meta.frames - 1, Math.floor(this.t / fr)));
    const cond = meta.conditions[this.condition === 0 ? "intact" : "disconnected"];
    const stimOn = this.t >= meta.rest_ms && this.t < meta.rest_ms + meta.stimulus_ms;
    const reset = this.t >= meta.rest_ms + meta.stimulus_ms + meta.reset_after_ms;
    $("clock").textContent = `${Math.round(this.t - meta.rest_ms)} ms`;
    const stim = $("stim");
    stim.className = stimOn ? "stim on" : "stim";
    stim.textContent = stimOn ? `input on · ${this.sc.sub}` : reset ? "copy reset (game rule)" : "input off";
    const action = cond.action[f];
    $("action-flag").textContent = action || "—";
    $("action-flag").className = action ? "action-flag on" : "action-flag";
    $("fact-action").textContent = action || "—";
    $("fact-firing").textContent = fmt(cond.neurons_fired[f]);
    $("fact-readout").textContent = this.readoutValue(cond, f);
    if (document.activeElement !== $("scrub")) $("scrub").value = String(Math.round(this.t / this.totalMs() * 1000));
    this.drawCursor();
  }

  readoutValue(cond, f) {
    if (this.sc.name === "turn") {
      const d = cond.smoothed_hz.turn_deg_s[f];
      return `${d > 0 ? "+" : ""}${Math.round(d)}°/s`;
    }
    if (this.sc.name === "jump") return hz(cond.rates_hz.gf[f]);
    return hz(cond.smoothed_hz[this.sc.series[0].key][f]);
  }

  refreshText() {
    const facts = this.data.facts[this.condition];
    $("story").innerHTML = this.sc.story(facts) + `<p class="fine"><b>Rule:</b> ${this.sc.rule}</p>`;
  }

  // --- chart -------------------------------------------------------------
  seriesValues(cond, s) {
    if (s.key === "asym") return cond.smoothed_hz.dna02_R.map((r, i) => r - cond.smoothed_hz.dna02_L[i]);
    return s.raw ? cond.rates_hz[s.key] : cond.smoothed_hz[s.key];
  }

  drawChart() {
    if (!this.data) return;
    const canvas = $("chart");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    const meta = this.data.meta, sc = this.sc, fr = meta.frame_ms, total = this.totalMs();
    const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
    const sense = css(`--sense-${sc.sense}`), ink = css("--text"), muted = css("--muted"), line = css("--line");
    const conds = [meta.conditions.intact, meta.conditions.disconnected];
    let top = sc.threshold || 1;
    for (const c of conds) for (const s of sc.series) top = Math.max(top, ...this.seriesValues(c, s));
    top *= 1.08;
    const padL = 34, padR = 8, padT = 8, padB = 18;
    const X = (ms) => padL + (ms / total) * (w - padL - padR);
    const Y = (v) => padT + (1 - v / top) * (h - padT - padB);
    // stimulus band and reset line
    ctx.fillStyle = sense + "26";
    ctx.fillRect(X(meta.rest_ms), padT, X(meta.rest_ms + meta.stimulus_ms) - X(meta.rest_ms), h - padT - padB);
    const resetAt = meta.rest_ms + meta.stimulus_ms + meta.reset_after_ms;
    ctx.strokeStyle = line;
    ctx.setLineDash([2, 3]);
    ctx.beginPath(); ctx.moveTo(X(resetAt), padT); ctx.lineTo(X(resetAt), h - padB); ctx.stroke();
    ctx.setLineDash([]);
    // axes
    ctx.fillStyle = muted;
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    const step = niceStep(top);
    for (let v = 0; v <= top; v += step) {
      ctx.fillText(String(v), padL - 5, Y(v));
      ctx.strokeStyle = line + "88";
      ctx.beginPath(); ctx.moveTo(padL, Y(v)); ctx.lineTo(w - padR, Y(v)); ctx.stroke();
    }
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    ctx.fillText("input", X(meta.rest_ms) + 3, h - 5);
    ctx.fillText("reset", X(resetAt) + 3, h - 5);
    // threshold
    if (sc.threshold) {
      ctx.strokeStyle = ink;
      ctx.setLineDash([5, 4]);
      ctx.beginPath(); ctx.moveTo(padL, Y(sc.threshold)); ctx.lineTo(w - padR, Y(sc.threshold)); ctx.stroke();
      ctx.setLineDash([]);
    }
    // series: the other condition faint, the selected one strong
    const order = this.condition === 0 ? [1, 0] : [0, 1];
    for (const ci of order) {
      const strong = ci === this.condition;
      for (const s of sc.series) {
        const vals = this.seriesValues(conds[ci], s);
        ctx.strokeStyle = ci === 1 ? muted : s.alt ? css("--magenta") : sense;
        ctx.globalAlpha = strong ? (s.raw ? 0.55 : 1) : 0.22;
        ctx.lineWidth = s.raw ? 1 : 2;
        ctx.beginPath();
        vals.forEach((v, i) => {
          const x = X((i + 0.5) * fr), y = Y(Math.max(0, v));
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
    this.chartGeom = { X, padT, padB, h, w, dpr };
    this.chartImage = ctx.getImageData(0, 0, canvas.width, canvas.height);
    this.drawCursor();
    const legend = sc.series.map((s) => `<span><i class="${s.raw ? "thin" : ""}" style="--c:${s.alt ? css("--magenta") : sense}"></i>${s.label}</span>`);
    if (sc.threshold) legend.push(`<span><i class="dash" style="--c:${ink}"></i>${sc.thresholdKey === "pip10" ? "song" : "action"} threshold, ${sc.threshold} Hz</span>`);
    legend.push(`<span><i style="--c:${muted}"></i>cut wiring (${this.condition === 1 ? "shown" : "faint"})</span>`);
    $("chart-legend").innerHTML = legend.join("");
  }

  drawCursor() {
    if (!this.chartImage) return;
    const ctx = $("chart").getContext("2d");
    const { X, padT, padB, h, dpr } = this.chartGeom;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.putImageData(this.chartImage, 0, 0);
    ctx.scale(dpr, dpr);
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--text").trim();
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(X(this.t), padT); ctx.lineTo(X(this.t), h - padB); ctx.stroke();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }

  // --- labels and hover --------------------------------------------------
  buildTags(meta) {
    const layer = $("tags");
    layer.innerHTML = "";
    const groups = [...Object.entries(meta.cells.inputs).map(([g, cells]) => ["input", g, cells]),
      ...Object.entries(meta.cells.readouts).map(([g, cells]) => ["readout", g, cells])];
    this.tagEls = [];
    for (const [kind, g, cells] of groups) {
      // Cells on both sides of the brain get one tag per side, not one at the midline.
      const left = cells.filter((i) => this.xyz[3 * i] < 0), right = cells.filter((i) => this.xyz[3 * i] >= 0);
      const meanX = (ids) => ids.reduce((t, i) => t + this.xyz[3 * i], 0) / Math.max(1, ids.length);
      const split = Math.min(left.length, right.length) >= 0.2 * cells.length && meanX(right) - meanX(left) > 0.35;
      for (const part of split ? [left, right] : [cells]) {
        const d = document.createElement("div");
        d.className = `t-${kind}`;
        d.textContent = GROUP_NAMES[g] || g;
        const c = [0, 0, 0];
        for (const i of part) for (let k = 0; k < 3; k++) c[k] += this.xyz[3 * i + k] / part.length;
        layer.append(d);
        this.tagEls.push({ el: d, c });
      }
    }
  }

  placeTags() {
    if (!this.tagEls) return;
    for (const t of this.tagEls) {
      const [x, y] = this.view.project(...t.c);
      t.el.style.left = `${x}px`;
      t.el.style.top = `${y}px`;
    }
  }

  showTip(x, y) {
    const i = this.view.pick(x, y);
    const tip = $("tip");
    if (i < 0) { this.hideTip(); return; }
    const type = this.meta.types[this.type[i]] || "unnamed type";
    const sup = this.meta.superclasses[this.superclass[i]] || "unclassified";
    const kind = this.view.kind[i];
    const role = kind > 2.5 ? "readout" : kind > 1.5 ? "input" : kind > 0.5 ? "in this copy" : "not in this copy";
    tip.innerHTML = `<b>${type}</b> <span>· ${sup.replace(/_/g, " ")}</span><br>
      <span>body ${this.bodyId[i]} · ${role}${this.approximate[i] ? " · position approximate" : ""}</span>`;
    tip.style.left = `${Math.min(x, $("specimen").clientWidth - 200)}px`;
    tip.style.top = `${y}px`;
    tip.hidden = false;
  }

  hideTip() { $("tip").hidden = true; }
}

function niceStep(top) {
  const raw = top / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 5, 10]) if (raw <= m * p) return m * p;
  return 10 * p;
}

async function start() {
  try {
    const [meta, buffer] = await Promise.all([fetchJson("data/map.json"), fetchGz("data/map.bin")]);
    const atlas = new Atlas(meta, buffer);
    const first = new URLSearchParams(location.search).get("r");
    await atlas.select(SCENARIOS.some((s) => s.name === first) ? first : "jump");
    let last = performance.now();
    const loop = (now) => {
      atlas.tick(now - last);
      last = now;
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  } catch (err) {
    console.error(err);
    $("status").className = "status-pill error";
    $("status").textContent = "Could not start the map";
    const fb = document.createElement("div");
    fb.className = "fallback";
    fb.textContent = `The map could not start: ${err.message}. It needs WebGL and a recent browser.`;
    $("specimen").append(fb);
  }
}

start();
