// A 3D point cloud of the packaged neurons, drawn with WebGL at their cell-body
// positions (approximate for sensory cells whose bodies lie outside the scan).
// Display only: it knows nothing about the model, it just glows where told.
// Each neuron has a "heat" (1 = fired just now, fading to 0) and a "kind":
// 0 not in the running brain copy, 1 in the copy, 2 input cell, 3 readout cell.

const VERT = `
attribute vec3 a_pos;
attribute float a_heat;
attribute float a_kind;
uniform mat4 u_mvp;
uniform float u_px;
uniform vec3 u_sense;
uniform float u_gain;
varying vec3 v_color;
void main() {
  gl_Position = u_mvp * vec4(a_pos, 1.0);
  float h = a_heat;
  vec3 rest = a_kind < 0.5 ? vec3(0.040, 0.052, 0.052) : vec3(0.095, 0.125, 0.118);
  float size = 1.8;
  vec3 hot = u_sense * (0.05 + 0.24 * h);
  if (a_kind > 1.5 && a_kind < 2.5) {        // input cells
    rest = u_sense * 0.10;
    size = 2.4;
  } else if (a_kind > 2.5) {                 // readout cells
    rest = vec3(0.30, 0.34, 0.33);
    hot = mix(u_sense, vec3(1.0), 0.55) * (0.6 + 1.4 * h);
    size = 7.0;
  }
  // Smaller canvases pack the same points closer; dim them so they do not white out.
  v_color = (h > 0.002 ? max(rest, hot * min(1.0, h * 4.0)) : rest) * u_gain;
  gl_PointSize = u_px * size * (1.0 + 0.35 * h);
}`;

const FRAG = `
precision mediump float;
varying vec3 v_color;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = dot(d, d);
  if (r > 0.25) discard;
  gl_FragColor = vec4(v_color * (1.0 - r * 2.6), 1.0);
}`;

function shader(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
  return s;
}

function perspective(fovY, aspect, near, far) {
  const f = 1 / Math.tan(fovY / 2);
  const nf = 1 / (near - far);
  return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0];
}

// Column-major 4x4 multiply.
function mul(a, b) {
  const o = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
    let s = 0;
    for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
    o[c * 4 + r] = s;
  }
  return o;
}

function rotation(yaw, pitch) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
  const ry = [cy, 0, -sy, 0, 0, 1, 0, 0, sy, 0, cy, 0, 0, 0, 0, 1];
  const rx = [1, 0, 0, 0, 0, cp, sp, 0, 0, -sp, cp, 0, 0, 0, 0, 1];
  return mul(rx, ry);
}

export class MapView {
  constructor(canvas, xyz, n) {
    const gl = canvas.getContext("webgl", { antialias: false, alpha: false, premultipliedAlpha: false });
    if (!gl) throw new Error("WebGL is not available");
    this.gl = gl;
    this.canvas = canvas;
    this.n = n;
    this.xyz = xyz;           // Float32Array, 3 per neuron
    this.heat = new Float32Array(n);
    this.kind = new Float32Array(n);
    this.yaw = 0;
    this.pitch = 0.12;
    this.sense = [1, 1, 1];
    this.background = [0.051, 0.078, 0.075];

    const prog = gl.createProgram();
    gl.attachShader(prog, shader(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, shader(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    gl.useProgram(prog);
    this.prog = prog;
    this.u = {
      mvp: gl.getUniformLocation(prog, "u_mvp"),
      px: gl.getUniformLocation(prog, "u_px"),
      sense: gl.getUniformLocation(prog, "u_sense"),
      gain: gl.getUniformLocation(prog, "u_gain"),
    };
    const buffer = (data, name, size, usage) => {
      const b = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, data, usage);
      const loc = gl.getAttribLocation(prog, name);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0);
      return b;
    };
    buffer(xyz, "a_pos", 3, gl.STATIC_DRAW);
    this.heatBuffer = buffer(this.heat, "a_heat", 1, gl.DYNAMIC_DRAW);
    this.kindBuffer = buffer(this.kind, "a_kind", 1, gl.STATIC_DRAW);
    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);   // additive: busy regions glow
    this.screen = new Float32Array(n * 3);
  }

  setKinds(kind) {
    this.kind.set(kind);
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.kindBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.kind, gl.STATIC_DRAW);
  }

  setSense(rgb) { this.sense = rgb; }

  matrix() {
    const w = this.canvas.clientWidth || 1, h = this.canvas.clientHeight || 1;
    const aspect = w / h;
    // Keep the whole map in view on narrow screens by backing the camera off.
    const distance = 4.4 * Math.max(1.12, 0.92 / aspect);
    const view = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0.02, -distance, 1];
    return mul(perspective(30 * Math.PI / 180, aspect, 0.1, 20), mul(view, rotation(this.yaw, this.pitch)));
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.round(this.canvas.clientWidth * dpr), h = Math.round(this.canvas.clientHeight * dpr);
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    this.dpr = dpr;
  }

  draw() {
    this.resize();
    const gl = this.gl;
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(...this.background, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.heatBuffer);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.heat);
    this.mvp = this.matrix();
    gl.uniformMatrix4fv(this.u.mvp, false, this.mvp);
    gl.uniform1f(this.u.px, this.dpr * Math.max(0.8, Math.min(1.25, this.canvas.clientWidth / 620)));
    gl.uniform3fv(this.u.sense, this.sense);
    gl.uniform1f(this.u.gain, Math.max(0.45, Math.min(1, this.canvas.clientWidth / 620)));
    gl.drawArrays(gl.POINTS, 0, this.n);
  }

  // Screen position (CSS pixels) of a 3D point under the current view.
  project(x, y, z) {
    const m = this.mvp || this.matrix();
    const cx = m[0] * x + m[4] * y + m[8] * z + m[12];
    const cy = m[1] * x + m[5] * y + m[9] * z + m[13];
    const cw = m[3] * x + m[7] * y + m[11] * z + m[15];
    return [(cx / cw * 0.5 + 0.5) * this.canvas.clientWidth, (0.5 - cy / cw * 0.5) * this.canvas.clientHeight, cw];
  }

  // Nearest drawn neuron to a CSS-pixel point, preferring the camera-near one.
  pick(px, py, radius = 9) {
    const m = this.mvp || this.matrix();
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    let best = -1, bestScore = Infinity;
    const xyz = this.xyz;
    for (let i = 0; i < this.n; i++) {
      const x = xyz[3 * i], y = xyz[3 * i + 1], z = xyz[3 * i + 2];
      const cw = m[3] * x + m[7] * y + m[11] * z + m[15];
      const sx = ((m[0] * x + m[4] * y + m[8] * z + m[12]) / cw * 0.5 + 0.5) * w;
      const sy = (0.5 - (m[1] * x + m[5] * y + m[9] * z + m[13]) / cw * 0.5) * h;
      const d2 = (sx - px) ** 2 + (sy - py) ** 2;
      const r = this.kind[i] > 2.5 ? radius + 4 : radius;
      if (d2 > r * r) continue;
      // Readouts and inputs win ties; then distance; then nearness to camera.
      const score = d2 - this.kind[i] * 40 + cw * 2;
      if (score < bestScore) { bestScore = score; best = i; }
    }
    return best;
  }
}
