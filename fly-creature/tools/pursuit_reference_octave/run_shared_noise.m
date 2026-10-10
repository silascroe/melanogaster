% Check the unchanged author dynamics under common, nonzero perturbations.
% Octave's missing MATLAB lowpass is shimmed to identity. This is not the
% authors' filtered-noise protocol; the generated noise is saved for Python.
source_root = fullfile(pwd, 'outputs', 'research', 'CollieWilson', 'Modeling_Code');
output_root = fullfile(pwd, 'outputs', 'research', 'verification', 'octave_noise');
addpath(source_root);
addpath(fullfile(source_root, 'support'));
addpath(fullfile(pwd, 'tools', 'pursuit_reference_octave', 'shims'));
if ~exist(output_root, 'dir'), mkdir(output_root); endif
raw = csvread(fullfile(source_root, 'Pursuit_RFs.csv'), 1, 0);
rf.AOTU019 = raw(:,8);
rf.AOTU025 = raw(:,9);
rf.sum = zeros(361,1);
settings.visObjPosition = -180:180;
settings.DNa02input = linspace(-2.25, 4, 1000);
settings.DNa02output = settings.DNa02input;
settings.numRuns = 8;
settings.fs = 100;
settings.fpass = 0.05;
settings.AOTU019_delay = 450;
settings.Others_delay = 450;
settings.AOTU019dsi_penalty = 0.66;
settings.AOTU025dsi_penalty = 1;
for mode = 0:2
  settings.dirselective = mode;
  [timebase, positions, channels, velocity] = aotu_steering_model( ...
      rf, 0.01, 120, 'inhibitory', 16, 0.65, 100, settings);
  prefix = fullfile(output_root, sprintf('mode%d_', mode));
  dlmwrite([prefix 'positions.csv'], positions, 'precision', '%.17g');
  dlmwrite([prefix 'velocity.csv'], velocity, 'precision', '%.17g');
  settle = calculateAverageSettlingTime(timebase, positions, 2, 1) - timebase(100);
  dlmwrite([prefix 'source_settle.csv'], settle, 'precision', '%.17g');
  for c = 1:6
    dlmwrite([prefix sprintf('channel%d.csv', c)], channels(:,:,c), 'precision', '%.17g');
  endfor
endfor
rng(13);
noise = 0.01 * zscore(randn(settings.numRuns, 16 * settings.fs));
dlmwrite(fullfile(output_root, 'shared_noise.csv'), noise, 'precision', '%.17g');
disp('Octave common-noise traces saved');
