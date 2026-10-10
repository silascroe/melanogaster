function y = wrapTo180(x)
  y = mod(x + 180, 360) - 180;
  y(y == -180 & x > 0) = 180;
endfunction
