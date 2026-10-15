// Consistency check for the home page's recorded replays (site/data/replay_*.*)
// and the neuron map (site/data/map.*), built by tools/export_web_replays.py.
// The page draws whatever these files say, so they must agree with themselves:
// every frame's lit neurons match the recorded count, only neurons of the
// running copy ever light up, the intact copy shows its reaction and the cut
// copy never does.
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";

const data = (name) => fileURLToPath(new URL(`../../site/data/${name}`, import.meta.url));
const map = JSON.parse(readFileSync(data("map.json"), "utf8"));
const mapBin = gunzipSync(readFileSync(data("map.bin")));
let failures = 0;
const check = (ok, message) => {
  if (!ok) { failures++; console.log(`FAIL ${message}`); }
};

const sizes = { int16: 2, uint8: 1, uint16: 2, uint32: 4 };
for (const [name, spec] of Object.entries(map.arrays)) {
  check(spec.offset + spec.length * sizes[spec.dtype] <= mapBin.length, `map array ${name} fits`);
}
check(map.arrays.xyz.length === 3 * map.n, "map has three coordinates per neuron");

// null: no action in either condition (bitter is refused; its MN9 rebound comes after contact).
const EXPECTED = { jump: "jump", feed: "feed", bitter: null, turn: "turn right", groom: "groom", backup: "back up" };
const popcount = (b) => { let c = 0; while (b) { c += b & 1; b >>= 1; } return c; };

for (const [name, expected] of Object.entries(EXPECTED)) {
  const meta = JSON.parse(readFileSync(data(`replay_${name}.json`), "utf8"));
  const bits = gunzipSync(readFileSync(data(`replay_${name}.bin`)));
  const { frames, bytes_per_frame: bpf } = meta;
  check(bits.length === 2 * frames * bpf, `${name}: ${bits.length} bytes for 2 x ${frames} x ${bpf}`);
  check(bpf === Math.ceil(map.n / 8), `${name}: one bit per map neuron`);
  const member = Buffer.from(map.packages[meta.package], "base64");
  ["intact", "disconnected"].forEach((condition, c) => {
    const cond = meta.conditions[condition];
    let outside = 0, mismatched = 0;
    for (let f = 0; f < frames; f++) {
      let lit = 0;
      for (let b = 0; b < bpf; b++) {
        const byte = bits[(c * frames + f) * bpf + b];
        lit += popcount(byte);
        outside += popcount(byte & ~member[b]);
      }
      if (lit !== cond.neurons_fired[f]) mismatched++;
    }
    check(mismatched === 0, `${name}/${condition}: ${mismatched} frames where lit neurons differ from the recorded count`);
    check(outside === 0, `${name}/${condition}: ${outside} lit neurons outside the ${meta.package} copy`);
    const wanted = condition === "intact" ? expected : null;
    check(wanted ? cond.action.some((a) => a.includes(wanted)) : !cond.action.some(Boolean),
      `${name}/${condition}: ${wanted ? `shows "${wanted}"` : "shows no action"}`);
    for (const key of meta.readouts) check(cond.rates_hz[key].length === frames, `${name}/${condition}: ${key} rate per frame`);
  });
  const onset = Math.round(meta.rest_ms / meta.frame_ms);
  if (name === "bitter") {
    // The page describes MN9's rebound after contact; the replay must still show it.
    const off = onset + Math.round(meta.stimulus_ms / meta.frame_ms);
    const rebound = Math.max(...meta.conditions.intact.smoothed_hz.mn9.slice(off));
    check(rebound >= meta.thresholds.feed_hz, `bitter: MN9 rebound after contact (${rebound} Hz) is visible`);
  }
  check(meta.conditions.intact.neurons_fired.slice(0, onset).every((n) => n === 0), `${name}: silent before the input`);
  for (const cells of [...Object.values(meta.cells.inputs), ...Object.values(meta.cells.readouts)]) {
    check(cells.length > 0 && cells.every((i) => (member[i >> 3] >> (i & 7)) & 1), `${name}: named cells are in the copy`);
  }
  console.log(`${name}: ${frames} frames, ${meta.package} (${meta.package_neurons} neurons), peak ${Math.max(...meta.conditions.intact.neurons_fired)} firing`);
}

if (failures) {
  console.log(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("replays consistent");
