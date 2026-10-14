// Headless run of the live page's world (site/creature.js): the cartoon fly
// walks into the sugar cube for 30 simulated seconds per seed, with intact
// wiring and with the wiring onto MDN cut. Rules, fixed before the first run:
// intact backs up at least once on every seed; cut never backs up and its
// smoothed MDN rate stays below 1 Hz. Run: node tests/web/check_web_demo.mjs

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Creature } from "../../site/creature.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const meta = JSON.parse(readFileSync(join(root, "site", "data", "obstacle_brain_v4.json"), "utf8"));
const file = readFileSync(join(root, "site", "data", "obstacle_brain_v4.bin"));
const buffer = file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength);

const SECONDS = 30;
const SEEDS = [1, 2, 3, 4, 5];
let failed = false;

for (const condition of ["intact", "disconnected"]) {
  for (const seed of SEEDS) {
    const world = new Creature(meta, buffer, { seed });
    if (condition !== "intact") world.setCondition(condition);
    const episodes = { backing: 0, "giving up": 0, pressing: 0 };
    let previous = world.fly.mode;
    let peakHz = 0;
    const chunks = (SECONDS * 1000) / world.settings.chunkMs;
    for (let k = 0; k < chunks; k++) {
      world.chunk();
      peakHz = Math.max(peakHz, world.mdnHz);
      const mode = world.fly.mode;
      if (mode !== previous && mode in episodes) episodes[mode] += 1;
      previous = mode;
    }
    const ok = condition === "intact"
      ? episodes.backing >= 1
      : episodes.backing === 0 && peakHz < 1;
    failed ||= !ok;
    console.log(`${ok ? "ok  " : "FAIL"} ${condition.padEnd(12)} seed ${seed}: pressed ${episodes.pressing}x, ` +
      `backed up ${episodes.backing}x, gave up ${episodes["giving up"]}x, peak MDN ${peakHz.toFixed(1)} Hz, ` +
      `${(world.computeMs / Math.max(1, world.brainSimMs) * 50).toFixed(1)} ms per 50 ms of brain`);
  }
}
process.exit(failed ? 1 : 0);
