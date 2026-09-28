% Run the authors' unchanged model function in Octave on the deterministic
% Step 2 protocol. Compatibility shims and this harness are separate files.
source_root = fullfile(pwd, 'outputs', 'research', 'CollieWilson', 'Modeling_Code');
output_root = fullfile(pwd, 'outputs', 'research', 'verification', 'octave');
addpath(source_root);
addpath(fullfile(source_root, 'support'));
addpath(fullfile(pwd, 'tools', 'pursuit_reference_octave', 'shims'));
if ~exist(output_root, 'dir'), mkdir(output_root); endif
raw = csvread(fullfile(source_root, 'Pursuit_RFs.csv'), 1, 0);
assert(rows(raw) == 361 && columns(raw) == 15);
rf.AOTU019 = raw(:, 8);
rf.AOTU025 = raw(:, 9);
others = raw(:, [2:7 10:15]);
others(:, 1:2) = flipud(others(:, 1:2));
rf.sum = sum(others, 2);

settings.visObjPosition = -180:180;
settings.DNa02input = linspace(-2.25, 4, 1000);
settings.DNa02output = linspace(-2.25, 4, 1000);
settings.shift = -0.25;
settings.numRuns = 2;
settings.fs = 100;
settings.fpass = 0.05;
settings.AOTU019_delay = 450;
settings.Others_delay = 450;
settings.AOTU019dsi_penalty = 0.66;
settings.AOTU025dsi_penalty = 1;

static_drive = aotu_steering_model_position(rf, 'inhibitory', 1, settings);
dlmwrite(fullfile(output_root, 'static_drive.csv'), static_drive(:), 'precision', '%.17g');

rf.sum(:) = 0;
for mode = 0:2
  settings.dirselective = mode;
  [timebase, positions, channels, velocity] = aotu_steering_model( ...
      rf, 0, 120, 'inhibitory', 16, 0.65, 100, settings);
  prefix = fullfile(output_root, sprintf('mode%d_', mode));
  dlmwrite([prefix 'time.csv'], timebase(:), 'precision', '%.17g');
  dlmwrite([prefix 'positions.csv'], positions, 'precision', '%.17g');
  dlmwrite([prefix 'velocity.csv'], velocity, 'precision', '%.17g');
  settle = calculateAverageSettlingTime(timebase, positions, 2, 1) - timebase(100);
  dlmwrite([prefix 'source_settle.csv'], settle, 'precision', '%.17g');
  for c = 1:6
    dlmwrite([prefix sprintf('channel%d.csv', c)], channels(:,:,c), 'precision', '%.17g');
  endfor
endfor
disp('Octave reference traces saved');
