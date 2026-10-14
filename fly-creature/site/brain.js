// Leaky integrate-and-fire brain for the browser: a port of
// src/fly_creature/brain_model.py (Shiu et al. 2024 settings). Every step does
// the same floating-point operations in the same order as the Python one-core
// engine, so a recorded input schedule gives identical spikes
// (tests/web/check_web_brain.mjs). Only the random input stream differs.

export class Brain {
  // meta: parsed obstacle_brain_v4.json; buffer: ArrayBuffer of the .bin file.
  constructor(meta, buffer, { condition = "intact" } = {}) {
    const p = meta.params;
    const n = (this.n = meta.n);
    const view = (name, Type) => {
      const a = meta.arrays[name];
      return new Type(buffer, a.offset, a.length);
    };
    const indptr = view("indptr", Uint32Array);
    const post = view("post", Uint16Array);
    const signed = view("signed", Int16Array);
    this.xy = view("xy", Float32Array);
    this.flags = view("flags", Uint8Array);

    // Python stores weights as float32(signed * w_syn) and adds them as float64.
    // Cut wiring drops every connection onto the action neurons, keeping order.
    const cut = new Uint8Array(n);
    if (condition === "disconnected") for (const i of meta.cut_targets) cut[i] = 1;
    else if (condition !== "intact") throw new Error("condition must be intact or disconnected");
    this.indptr = new Uint32Array(n + 1);
    const keptPost = [];
    const keptWeight = [];
    for (let i = 0; i < n; i++) {
      for (let e = indptr[i]; e < indptr[i + 1]; e++) {
        if (cut[post[e]]) continue;
        keptPost.push(post[e]);
        keptWeight.push(Math.fround(signed[e] * p.w_syn_mv));
      }
      this.indptr[i + 1] = keptPost.length;
    }
    this.post = Uint16Array.from(keptPost);
    this.weight = Float64Array.from(keptWeight);

    this.delay = Math.round(p.t_dly_ms / p.dt_ms);
    this.refractorySteps = Math.round(p.t_rfc_ms / p.dt_ms);
    this.v0 = p.v_0_mv;
    this.vRst = p.v_rst_mv;
    this.vTh = p.v_th_mv;
    this.vDecay = p.dt_ms / p.t_mbr_ms;
    this.gDecay = p.dt_ms / p.tau_ms;
    this.kick = p.w_syn_mv * p.f_poi;
    this.dtMs = p.dt_ms;

    this.v = new Float64Array(n).fill(p.v_0_mv);
    this.g = new Float64Array(n);
    this.refractoryLeft = new Int32Array(n);
    this.noRefractory = new Uint8Array(n);
    for (const i of meta.inputs) this.noRefractory[i] = 1;
    this.pending = new Float64Array((this.delay + 1) * n);
    this.counts = new Uint32Array(n);
    this.fired = new Uint16Array(n);
    this.firedCount = 0;
    this.stepIndex = 0;
  }

  // Back to rest, as the game does after 500 ms without input.
  reset() {
    this.v.fill(this.v0);
    this.g.fill(0);
    this.refractoryLeft.fill(0);
    this.pending.fill(0);
    this.counts.fill(0);
    this.stepIndex = 0;
    this.firedCount = 0;
  }

  // One 0.1 ms step. `hits` lists input neurons receiving a Poisson event (a
  // neuron may appear more than once). Returns the number of neurons that fired;
  // their indices are this.fired[0 .. count).
  step(hits) {
    const { n, v, g, refractoryLeft, pending, delay } = this;
    const row = (this.stepIndex % (delay + 1)) * n;
    const v0 = this.v0, vDecay = this.vDecay, minusGDecay = -this.gDecay;
    for (let i = 0; i < n; i++) {
      g[i] += pending[row + i];
      pending[row + i] = 0.0;
      if (refractoryLeft[i] === 0) {
        const dv = (v0 - v[i] + g[i] - 0.0) * vDecay; // - w: adaptation is off (w = 0)
        const dg = g[i] * minusGDecay;
        v[i] += dv;
        g[i] += dg;
      } else {
        refractoryLeft[i] -= 1;
      }
    }
    for (let k = 0; k < hits.length; k++) v[hits[k]] += this.kick;
    const fired = this.fired, counts = this.counts, vTh = this.vTh, vRst = this.vRst;
    let m = 0;
    for (let i = 0; i < n; i++) {
      if (v[i] > vTh) {
        v[i] = vRst;
        g[i] = 0.0;
        refractoryLeft[i] = this.noRefractory[i] ? 0 : this.refractorySteps;
        counts[i] += 1;
        fired[m++] = i;
      }
    }
    // The out slot was emptied last step, so adding straight into it equals the
    // Python engine's sum-then-add.
    const out = ((this.stepIndex + delay) % (delay + 1)) * n;
    const { indptr, post, weight } = this;
    for (let k = 0; k < m; k++) {
      const i = fired[k];
      for (let e = indptr[i]; e < indptr[i + 1]; e++) pending[out + post[e]] += weight[e];
    }
    this.stepIndex += 1;
    this.firedCount = m;
    return m;
  }
}

// Small seeded generator (mulberry32) for the live demo's Poisson input.
export function seededRandom(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Poisson input: each listed neuron gets an event this step with probability
// rate * dt. Fills `out` and returns how many entries were written.
export function poissonHits(cells, rateHz, dtMs, random, out) {
  const prob = (rateHz * dtMs) / 1000.0;
  let m = 0;
  if (prob <= 0) return 0;
  for (let k = 0; k < cells.length; k++) if (random() < prob) out[m++] = cells[k];
  return m;
}
