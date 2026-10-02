# Measured AOTU response benchmark v1

2026-10-02. Frozen before measuring response fits. Offline diagnostic only.

Use Zenodo version 15474938's two NoP1 motion-pulse archives, validating their
published MD5 hashes. Keep each recording's identity and side metadata. Read
MATLAB v7.3 numeric arrays through optional h5py, with MATLAB dimensions
restored; read small v5 side metadata through scipy. No raw recordings in Git.
Source preprocessing has already made position positive ipsilaterally.

Extract contiguous finite stimulus intervals, rejecting incomplete boundary
segments. Accept 22.5-degree motion spans within 3 degrees, duration within
30 ms of 0.9/0.3 seconds (25/75 degrees/s), slope within 10% of that speed,
and linear-position R² >=0.98. Derive speed by least-squares position/time,
not adjacent quantized samples. Retain rejection counts. Compare extracted
counts, spans and durations to the source's finite-interval ordering; do not
claim execution parity with its MATLAB helper. No tuning extraction to rates.

Use a 250 ms pre/post observation window with no other visible stimulus in
that window. Baseline rate is mean over -250..-100 ms; keep raw pulse mean
and baseline-subtracted mean separately. Quiescent: at least 50% of pulse
samples have abs(forward)<=0.5 mm/s; running: at least 75% have forward>2 mm/s;
otherwise mixed. This is an explicit pulse-window state criterion, different
from the source's two-second buffered state window and Schmitt running mask.
Primary report quiescent and running separately; mixed descriptive only.

Freeze baseline and column-footprint candidate, normalization/ELU/direction
penalty and recorded edges. Replay native recorded stimulus positions through
their AOTU activity, before DN decoding. For left recordings, transform the
ipsilateral-positive input back to global left angles exactly once for the model.
Use full -180..180-degree diagnostic fields, not the game's 120-degree view cap.
Hidden stimulus gives zero model evoked activity. Apply sigma50ms symmetric
Gaussian observation filtering (truncate at5sigma), zero-padded outside the
isolated stimulus. This is measurement matching, not neural dynamics or a motor
delay; preserve the gameplay queue. Shape predictions remain arbitrary units.
Finite object size/contrast/elevation are not encoded by these frozen models.
The files lack acquisition metadata: report that limitation rather than claim
exact finite-stimulus parity.

32 within-side LC10a input-bundle shuffles per anatomical candidate, fixed
seed20261006 and frozen original normalization. Additional simple spatial
control: Gaussian ipsilateral-position response centered35/65 degrees,
width20 degrees, no direction penalty, with the same observation filter and
calibration allowance. These fixed values are source regression predictors,
not claimed measured physiology; no spatial parameters are fitted here.

Use deterministic leave-one-recording-out folds within type and state.
Equal weight per training recording (its pulses share its total weight).
Fit one nonnegative slope and intercept from training pulse means only,
mapping arbitrary activity to raw spikes/s. Same two parameters for every
candidate/control; no separate direction or side gains. Carry these parameters
to held-out pulse means and time courses. Baseline-subtracted metrics remove
each pulse's own pre-stimulus baseline from observation and prediction; they
do not get a second fitted gain. Do not fit temporal shift, widths or delays.
Require at least3 training recordings; missing coverage is unavailable, not zero.

Report per-recording held-out pulse-mean RMSE, baseline-subtracted pulse-mean
RMSE and time-course RMSE in spikes/s, then means/SEM across recordings.
Compare wiring ranks on identical held-out pulses with equal fitting budgets.
Report per-recording binned position/direction curves and raw direction
differences/ratios (ratio only when both evoked means are positive). Keep the
distinction between input coverage, shape, direction and temporal limitations.
Archive full pulse CSV/time courses in ignored outputs; track compact JSON,
summary CSV and overview plot. No motor/biological validation claim, no parameter
promotion and no fresh pursuit paths. This is an exploratory diagnostic, not
a predeclared acceptance test for biological accuracy.
