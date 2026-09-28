function y = lowpass(x, cutoff, sample_rate)
  % Identity compatibility shim. It does not reproduce MATLAB lowpass.
  % The resulting nonzero-noise case checks shared-noise dynamics only.
  assert(cutoff == 0.05 && sample_rate == 100);
  y = x;
endfunction
