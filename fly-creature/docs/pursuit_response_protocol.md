# Response-contribution diagnosis v1

2026-10-02. Investigation, not controller promotion. Reproduction: the
105-degree step has 14.701 degrees mean error in our unmirrored adaptation,
versus 8.993 in the reference; instantaneous stationary signal is 0.221 versus
0.870. Use existing retinal benchmark inputs; no new validation is consumed.

Ranked hypotheses: wide-angle attenuation arises before output decoding;
shared input normalization/ELU further weakens it; output-weight asymmetry
explains side differences but not most of the wide-angle deficit. Also measure
how the pre-ELU direction penalty changes central command switching.

Scan integer bearings -120..120 at motion -1, 0, +1. Preserve the baseline
15-degree overlap, 18-degree Gaussian width, recorded edges, gain, timing and
cap. Decompose raw contact drive, normalized input, activated output, per-AOTU
signed steering contribution, unclipped/clipped DN and final command.

One-factor counterfactuals, declared before their results: symmetrize only
paired raw input fields; symmetrize only paired output weights (including side
swap); normalize each input channel to its own original pre-overlap peak;
replace only ELU by linear normalized input; use unit-magnitude canonical
output edges without changing their sign/topology; quantize only DN output as
the source does. Diagnostic transformations are engineered and have no assumed
biological authority. No author RF fed through our recorded weights.

Measure wide-angle stationary strength, effective direction attenuation,
mirrored command asymmetry, central direction-switch jump and clipping. Replay
all 22 previously evaluated world streams with unchanged body/queue settings;
compare against saved baseline metrics. Match closed-loop error only as a
diagnostic, not proof of a fix. Separate factors do not isolate interactions.
Save local full curves, compact contribution samples/summary, and a plotted
comparison. Do not redistribute the licensed external response table.
