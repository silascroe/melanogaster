// Exactness check: the browser engine (site/brain.js) replays the Python engine's
// recorded input schedule and must produce the same spikes and voltages, bit for
// bit. Run: node tests/web/check_web_brain.mjs (from fly-creature/).
// Vectors come from tools/export_web_brain.py.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Brain } from "../../site/brain.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const meta = JSON.parse(readFileSync(join(root, "site", "data", "obstacle_brain_v4.json"), "utf8"));
const file = readFileSync(join(root, "site", "data", "obstacle_brain_v4.bin"));
const buffer = file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength);
const vectors = JSON.parse(readFileSync(join(root, "tests", "web", "obstacle_v4_vector.json"), "utf8"));
const mdn = meta.groups.mdn;
let failures = 0;

for (const vector of vectors) {
  const brain = new Brain(meta, buffer, { condition: vector.condition });
  const hitsAt = new Map();
  vector.hit_steps.forEach((step, k) => {
    if (!hitsAt.has(step)) hitsAt.set(step, []);
    hitsAt.get(step).push(vector.hit_cells[k]);
  });
  const frameSteps = Math.round(50 / meta.params.dt_ms);
  const mdnFrames = [], spikeFrames = [];
  let mdnFrame = 0, spikeFrame = 0;
  const started = performance.now();
  for (let step = 0; step < vector.steps; step++) {
    const fired = brain.step(hitsAt.get(step) ?? []);
    spikeFrame += fired;
    for (let k = 0; k < fired; k++) if (mdn.includes(brain.fired[k])) mdnFrame += 1;
    if ((step + 1) % frameSteps === 0) {
      mdnFrames.push(mdnFrame);
      spikeFrames.push(spikeFrame);
      mdnFrame = spikeFrame = 0;
    }
  }
  const elapsed = performance.now() - started;
  const problems = [];
  if (JSON.stringify(mdnFrames) !== JSON.stringify(vector.mdn_spikes_per_50ms)) problems.push("MDN spikes per frame");
  if (JSON.stringify(spikeFrames) !== JSON.stringify(vector.spikes_per_50ms)) problems.push("total spikes per frame");
  if (vector.final_counts.some((c, i) => c !== brain.counts[i])) problems.push("final spike counts");
  const vDiff = vector.final_v.findIndex((x, i) => x !== brain.v[i]);
  if (vDiff >= 0) problems.push(`voltage of neuron ${vDiff} (${brain.v[vDiff]} vs ${vector.final_v[vDiff]})`);
  const simMs = vector.steps * meta.params.dt_ms;
  console.log(`${problems.length ? "FAIL" : "ok  "} ${vector.condition}: ${spikeFrames.reduce((a, b) => a + b, 0)} spikes, ` +
    `MDN ${mdnFrames.reduce((a, b) => a + b, 0)}; ${(elapsed / simMs * 50).toFixed(1)} ms per 50 ms simulated` +
    (problems.length ? `; differs in: ${problems.join(", ")}` : ""));
  failures += problems.length ? 1 : 0;
}
process.exit(failures ? 1 : 0);
