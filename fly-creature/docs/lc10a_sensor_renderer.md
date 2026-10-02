# Retinal renderer: first runnable sensory boundary

The offline renderer consumes the [LC10a input contract](lc10a_sensor_contract.md)
and 68 probe definitions. It produces retinal luminance images and pixel/photometry
summaries. It deliberately stops before generating neural activity. Rendering a
stimulus is not simulating LC10a.

## What it implements

`src/fly_creature/retina.py` creates a 176x32 grid spanning 330x60 degrees at
1.875 degrees per pixel. For each probe it draws a persistent normalized
background, optional moving vertical square grating, and moving finite rectangle
or disc with independent azimuth/elevation. Affected pixels use eight-by-eight
subpixel sampling to estimate fractional target coverage, then mix target
luminance over the background. The same input row produces deterministic frames.

`tools/run_lc10a_probes.py` walks all 68 three-second probes at their declared
2 ms interval (102,000 frames). It streams one row per sample to `trace.csv`
without keeping the movie in memory. `summary.csv` reports target pixel area,
mean luminance range and a digest of sampled frames. The SVG contact sheet embeds
early, middle and late in-stimulus frames for representative width, height, disc,
surround, contrast and paper-bar probes; separate PNGs accompany it. `report.json`
records input/source digests, dimensions and output hashes. The checked compact
report, probe summary and contact sheet are saved in `docs/evidence/`.

The previous point/Gaussian adapter is not called here. That adapter accepts a
bearing and an assumed Gaussian width; these images show the extra stimulus
dimensions it cannot receive. This code supplies no LC10a response law, state
multiplier, firing rate, calcium value, AOTU projection, motor output or body
feedback. Luminance is normalized and synthetic, not calibrated to the
experimental display. The paper bar dimensions in a synthetic probe are not
proof that every archived recording used that pattern.

## Reproduce

From the workspace root:

```powershell
.\.venv\Scripts\python.exe fly-creature/tools/build_lc10a_probe_matrix.py --output-dir fly-creature/outputs/research/lc10a-contract-v1
.\.venv\Scripts\python.exe fly-creature/tools/run_lc10a_probes.py --output-dir fly-creature/outputs/research/lc10a-render-v1
```

An optional positive `--sample-interval-s` must be at least each probe's `dt_s`
and deliberately samples more sparsely. Full time traces and individual frames
belong in ignored `outputs/research/`; only compact summaries/contact sheet are
tracked. Passing the geometry probe matrix demonstrates that the declared image
can be drawn and measured. It does not validate an LC10a response or a biological
input pathway.
