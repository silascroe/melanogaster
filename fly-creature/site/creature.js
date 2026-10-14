// The live demo's world: the obstacle brain copy (subset v4) plus an engineered
// cartoon body walking into a sugar cube. The loop mirrors the Godot game
// (godot/main.gd + brain_session.py): foreleg contact feeds 150 Hz Poisson input
// to the foreleg bristle neurons, MDN is read every 50 ms and smoothed, and the
// body backs up while the smoothed rate is at least 8 Hz. Walking, the minimum
// back-up, turning away and giving up are engineered; the spikes come from
// brain.js. No DOM here, so tests/web/check_web_demo.mjs can run it in Node.

import { Brain, seededRandom, poissonHits } from "./brain.js";

export const SETTINGS = Object.freeze({
  inputHz: 150,
  readMs: 50,              // MDN is read and smoothed every 50 ms
  chunkMs: 10,             // brain and body advance together in 10 ms chunks
  quietResetMs: 500,       // a copy returns to rest after 500 ms without input
  smooth: 1 - Math.exp(-0.05 / 0.15),
  backupHz: 8,
  holdS: 0.8,              // engineered minimum back-up
  giveUpS: 1.5,            // engineered: turn away if MDN never answers
  walkMps: 1.05,
  backMps: 0.5,
  turnRadps: 2.4,
  reachM: 0.42,            // foreleg tips ahead of the body centre
  cubeHalfM: 0.45,
  contactMarginM: 0.06,
  leaveRadiusM: 2.0,       // inside the arena walls, so leaving always ends
  arenaHalfW: 3.2,
  arenaHalfH: 2.56,
  historyReads: 120,       // 6 s of 50 ms readings
});

export class Creature {
  constructor(meta, buffer, { seed = 1 } = {}) {
    const S = SETTINGS;
    this.meta = meta;
    this.buffer = buffer;
    this.n = meta.n;
    this.brains = { intact: new Brain(meta, buffer, { condition: "intact" }) };
    this.condition = "intact";
    this.brain = this.brains.intact;
    this.xy = this.brain.xy;
    this.foreleg = Uint16Array.from(meta.groups.foreleg);
    this.mdnCells = meta.groups.mdn;

    // Colour class per neuron: 0 other, 1 descending, 2 foreleg input, 3 MDN.
    const descending = meta.superclasses.indexOf("descending_neuron");
    this.kind = new Uint8Array(this.n);
    for (let i = 0; i < this.n; i++) if (this.brain.flags[2 * i + 1] === descending) this.kind[i] = 1;
    for (const i of this.foreleg) this.kind[i] = 2;
    for (const i of this.mdnCells) this.kind[i] = 3;

    this.random = seededRandom(seed);
    this.hitBuffer = new Uint16Array(this.foreleg.length);
    this.noHits = new Uint16Array(0);

    this.active = false;       // false: the copy is at rest and is not stepped
    this.quietMs = 0;
    this.mdnHz = 0;
    this.backing = false;
    this.contact = false;
    this.input = false;
    this.touchHeld = false;
    this.chunkInRead = 0;
    this.mdnSpikes = 0;
    this.readId = 1;
    this.distinct = 0;
    this.stamp = new Uint32Array(this.n);
    this.firingLastRead = 0;
    this.inputThisRead = false;
    this.heat = new Float32Array(this.n);
    this.history = [];
    this.timeMs = 0;
    this.computeMs = 0;
    this.brainSimMs = 0;

    this.fly = {
      x: -2.1, y: 0.9, heading: 0, mode: "approach", modeTime: 0,
      turnLeft: 0, holdLeft: 0, offset: 0.15, trail: [], trailClock: 0,
    };
    this.fly.heading = Math.atan2(-this.fly.y, -this.fly.x);
    this.settings = S;
  }

  setCondition(condition) {
    this.brains[condition] ??= new Brain(this.meta, this.buffer, { condition });
    this.condition = condition;
    this.brain = this.brains[condition];
    this.active = false;
    this.heat.fill(0);
  }

  forelegContact() {
    const { fly } = this, S = SETTINGS;
    const tx = fly.x + Math.cos(fly.heading) * S.reachM;
    const ty = fly.y + Math.sin(fly.heading) * S.reachM;
    const edge = S.cubeHalfM + S.contactMarginM;
    return Math.abs(tx) <= edge && Math.abs(ty) <= edge;
  }

  enter(mode) {
    this.fly.mode = mode;
    this.fly.modeTime = 0;
  }

  startTurnAway(mode) {
    this.enter(mode);
    const away = 2.3 + this.random() * 0.7;
    this.fly.turnLeft = this.random() < 0.5 ? -away : away;
  }

  // Engineered body: one step of the walking/backing state machine.
  bodyStep(dt) {
    const { fly } = this, S = SETTINGS;
    const contact = this.contact;
    fly.modeTime += dt;
    if (this.backing && fly.mode !== "backing") {
      this.enter("backing");
      fly.holdLeft = S.holdS;
    }
    const forward = (speed) => {
      fly.x += Math.cos(fly.heading) * speed * dt;
      fly.y += Math.sin(fly.heading) * speed * dt;
    };
    switch (fly.mode) {
      case "approach": {
        if (contact) { this.enter("pressing"); break; }
        const want = Math.atan2(-fly.y, -fly.x) + fly.offset;
        let diff = Math.atan2(Math.sin(want - fly.heading), Math.cos(want - fly.heading));
        diff = Math.max(-S.turnRadps * dt, Math.min(S.turnRadps * dt, diff));
        fly.heading += diff;
        forward(S.walkMps);
        break;
      }
      case "pressing":
        if (!contact) this.enter("approach");
        else if (fly.modeTime >= S.giveUpS) this.startTurnAway("giving up");
        break;
      case "backing":
        forward(-S.backMps);
        fly.holdLeft -= dt;
        if (fly.holdLeft <= 0 && !this.backing) this.startTurnAway("turning away");
        break;
      case "turning away":
      case "giving up": {
        const step = Math.min(Math.abs(fly.turnLeft), S.turnRadps * dt) * Math.sign(fly.turnLeft);
        fly.heading += step;
        fly.turnLeft -= step;
        if (Math.abs(fly.turnLeft) < 1e-6) this.enter("leaving");
        break;
      }
      case "leaving":
        forward(S.walkMps);
        if (Math.hypot(fly.x, fly.y) > S.leaveRadiusM) {
          fly.offset = (this.random() - 0.5) * 0.6;
          this.enter("approach");
        }
        break;
    }
    fly.x = Math.max(-S.arenaHalfW + 0.4, Math.min(S.arenaHalfW - 0.4, fly.x));
    fly.y = Math.max(-S.arenaHalfH + 0.4, Math.min(S.arenaHalfH - 0.4, fly.y));
    fly.trailClock += dt;
    if (fly.trailClock >= 0.1) {
      fly.trailClock = 0;
      fly.trail.push(fly.x, fly.y);
      if (fly.trail.length > 80) fly.trail.splice(0, 2);
    }
  }

  // Brain: one chunk of the copy, then the 50 ms MDN read when due.
  brainChunk() {
    const S = SETTINGS;
    const input = this.input;
    if (input) {
      if (!this.active) { this.brain.reset(); this.active = true; }
      this.quietMs = 0;
      this.inputThisRead = true;
    } else if (this.active) {
      this.quietMs += S.chunkMs;
      if (this.quietMs >= S.quietResetMs) this.active = false;
    }
    if (this.active) {
      const { brain, heat, stamp, kind, foreleg, hitBuffer } = this;
      const steps = Math.round(S.chunkMs / brain.dtMs);
      const t0 = performance.now();
      for (let s = 0; s < steps; s++) {
        const m = input ? poissonHits(foreleg, S.inputHz, brain.dtMs, this.random, hitBuffer) : 0;
        const fired = brain.step(m ? hitBuffer.subarray(0, m) : this.noHits);
        for (let k = 0; k < fired; k++) {
          const i = brain.fired[k];
          heat[i] = 1;
          if (kind[i] === 3) this.mdnSpikes += 1;
          if (stamp[i] !== this.readId) { stamp[i] = this.readId; this.distinct += 1; }
        }
      }
      this.computeMs += performance.now() - t0;
      this.brainSimMs += S.chunkMs;
    }
    this.chunkInRead += 1;
    if (this.chunkInRead * S.chunkMs >= S.readMs) {
      const rate = this.mdnSpikes / this.mdnCells.length / (S.readMs / 1000);
      this.mdnHz += S.smooth * (rate - this.mdnHz);
      this.backing = this.mdnHz >= S.backupHz;
      this.history.push({ hz: this.mdnHz, input: this.inputThisRead });
      if (this.history.length > S.historyReads) this.history.shift();
      this.firingLastRead = this.distinct;
      this.chunkInRead = 0;
      this.mdnSpikes = 0;
      this.distinct = 0;
      this.readId += 1;
      this.inputThisRead = false;
    }
  }

  // Advance brain and body together by one chunk (10 ms).
  chunk() {
    this.contact = this.forelegContact();
    this.input = this.contact || this.touchHeld;
    this.brainChunk();
    this.bodyStep(SETTINGS.chunkMs / 1000);
    this.timeMs += SETTINGS.chunkMs;
  }

  // Fade the display glow by elapsed simulated time.
  fade(ms) {
    const decay = Math.exp(-ms / 90);
    const heat = this.heat;
    for (let i = 0; i < heat.length; i++) heat[i] *= decay;
  }
}
