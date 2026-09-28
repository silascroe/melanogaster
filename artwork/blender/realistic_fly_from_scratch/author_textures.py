"""Paint deterministic, reference-guided texture maps onto the macro fly.

Run with the portable Blender and the original .blend as the background file.
The maps are authored here as layered pigment and microstructure masks rather
than copied from a photograph. The source .blend is never overwritten.
"""

import math
from pathlib import Path

import bpy
import numpy as np


ROOT = Path(__file__).resolve().parent
MAPS = ROOT / "textures"
MAPS.mkdir(exist_ok=True)
OUTPUT = ROOT.parents[2] / "outputs" / "blender" / "realistic-fly-from-scratch"
OUTPUT.mkdir(parents=True, exist_ok=True)
SIZE = 1024


def value_noise(width, height, cells_x, cells_y, rng):
    grid = rng.random((cells_y + 1, cells_x), dtype=np.float32)
    grid[-1] = grid[0] if cells_y == 1 else grid[-1]
    xx = np.arange(width, dtype=np.float32) * cells_x / width
    yy = np.arange(height, dtype=np.float32) * cells_y / height
    x0 = xx.astype(np.int32)
    y0 = np.minimum(yy.astype(np.int32), cells_y - 1)
    fx = xx - x0
    fy = yy - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    x1 = (x0 + 1) % cells_x
    a = grid[y0[:, None], x0[None, :]]
    b = grid[y0[:, None], x1[None, :]]
    c = grid[y0[:, None] + 1, x0[None, :]]
    d = grid[y0[:, None] + 1, x1[None, :]]
    return ((a * (1 - fx) + b * fx) * (1 - fy[:, None])
            + (c * (1 - fx) + d * fx) * fy[:, None])


def field(seed):
    rng = np.random.default_rng(seed)
    result = np.zeros((SIZE, SIZE), dtype=np.float32)
    for cells, amp in ((5, 0.48), (17, 0.25), (57, 0.16), (160, 0.11)):
        result += (value_noise(SIZE, SIZE, cells, cells, rng) - 0.5) * amp
    return result


def gaussian(u, v, cx, cy, sx, sy):
    du = np.minimum(np.abs(u - cx), 1 - np.abs(u - cx))
    return np.exp(-0.5 * ((du / sx) ** 2 + ((v - cy) / sy) ** 2))


def save_map(name, rgb, alpha=None):
    rgb = np.clip(rgb, 0, 1).astype(np.float32)
    if alpha is None:
        alpha = np.ones(rgb.shape[:2], dtype=np.float32)
    rgba = np.dstack((rgb, alpha.astype(np.float32)))
    image = bpy.data.images.new(name, width=SIZE, height=SIZE, alpha=True)
    image.pixels.foreach_set(rgba.ravel())
    image.file_format = "PNG"
    image.filepath_raw = str(MAPS / (name + ".png"))
    image.save()
    image.filepath = "//textures/" + name + ".png"
    image.pack()
    print("TEXTURE", image.filepath_raw)
    return image


v, u = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32) / SIZE


def cuticle_maps(label, base, seed):
    broad = field(seed)
    fine = field(seed + 1)
    pigment = broad * 0.82 + fine * 0.44
    rough = fine * 0.18
    height = fine * 0.95 + field(seed + 2) * 0.55

    # Individually placed dark setal sockets and pale cuticle flecks. These
    # are small surface marks, not geometric hairs or copied photo pixels.
    rng = np.random.default_rng(seed + 100)
    mark_count = {"thorax": 1250, "head": 430, "abdomen": 940}[label]
    for i in range(mark_count):
        px = int(rng.integers(0, SIZE))
        py = int(rng.integers(0, SIZE))
        radius = int(rng.integers(2, 6))
        x0, x1 = max(0, px - radius * 2), min(SIZE, px + radius * 2 + 1)
        y0, y1 = max(0, py - radius * 2), min(SIZE, py + radius * 2 + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        spot = np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / (radius * radius))
        pigment[y0:y1, x0:x1] += (-0.17 if i % 7 else 0.10) * spot
        height[y0:y1, x0:x1] -= 0.10 * spot

    if label == "thorax":
        # Restrained dorsal trident and darker setal-root fields.
        dorsal = np.clip((v - 0.55) / 0.22, 0, 1)
        trident = (gaussian(u, v, 0.36, 0.76, 0.055, 0.20)
                   + gaussian(u, v, 0.64, 0.76, 0.055, 0.20)
                   + gaussian(u, v, 0.50, 0.82, 0.040, 0.18))
        pigment -= 0.17 * dorsal * np.clip(trident, 0, 1)
        pigment += 0.075 * gaussian(u, v, 0.5, 0.57, 0.4, 0.12)
        rough += 0.08 * dorsal
    elif label == "head":
        # Face is honey colored, with darker antennal/eye margins.
        pigment += 0.08 * gaussian(u, v, 0.50, 0.47, 0.21, 0.22)
        pigment -= 0.12 * (gaussian(u, v, 0.16, 0.57, 0.10, 0.30)
                           + gaussian(u, v, 0.84, 0.57, 0.10, 0.30))
        rough += 0.04 * gaussian(u, v, 0.5, 0.5, 0.3, 0.3)
    elif label == "abdomen":
        # Tergite edges and posterior darkening follow the body, not the noise.
        bands = np.zeros_like(u)
        for edge in (0.14, 0.30, 0.46, 0.63, 0.80):
            bands += np.exp(-((u - edge) / 0.022) ** 2)
        pigment -= 0.15 * np.clip(bands, 0, 1)
        pigment -= 0.17 * np.clip((u - 0.68) / 0.30, 0, 1)
        pigment += 0.06 * np.sin(2 * math.pi * v) ** 2
        rough += 0.06 * bands

    base_rgb = np.asarray(base, dtype=np.float32)
    color = np.clip(base_rgb[None, None, :] * (1 + pigment[..., None]), 0, 1)
    # Height is intentionally subtle; the existing model contains real setae.
    height_gray = np.clip(0.5 + 1.4 * height, 0, 1)
    rough_gray = np.clip(0.50 + rough, 0.1, 0.9)
    return (save_map(label + "_color", color),
            save_map(label + "_microheight", np.repeat(height_gray[..., None], 3, axis=2)),
            save_map(label + "_roughness", np.repeat(rough_gray[..., None], 3, axis=2)))


thorax_maps = cuticle_maps("thorax", (0.30, 0.15, 0.057), 620)
head_maps = cuticle_maps("head", (0.43, 0.25, 0.092), 810)
abdomen_maps = cuticle_maps("abdomen", (0.37, 0.17, 0.072), 440)

# Uneven, translucent ommatidial pigment. Small highlights remain a shader and
# actual facet geometry, while this map controls regional red/brown variation.
eye_field = field(1590)
eye_center = gaussian(u, v, 0.51, 0.55, 0.39, 0.35)
eye_pigment = np.clip(0.8 + eye_field * 0.22 + eye_center * 0.13 - 0.11 * (1 - v), 0.57, 1.03)
eye_rgb = np.stack((0.45 * eye_pigment, 0.055 * eye_pigment, 0.022 * eye_pigment), axis=-1)
eye_map = save_map("eye_pigment", eye_rgb)

# Mostly clear wing with warm costa, faint membrane grain, and slight opacity
# variation. Veins are still modeled geometry; this is not a printed vein map.
wing_field = field(2109)
edge = np.clip((v - 0.78) / 0.22, 0, 1)
wing_rgb = np.stack((0.70 + 0.10 * edge + wing_field * 0.04,
                     0.77 + 0.025 * edge + wing_field * 0.035,
                     0.78 - 0.07 * edge + wing_field * 0.025), axis=-1)
wing_alpha = np.clip(0.12 + 0.14 * edge + wing_field * 0.025, 0.07, 0.32)
wing_map = save_map("wing_membrane", wing_rgb, wing_alpha)


def image_node(nodes, image, x, y):
    node = nodes.new("ShaderNodeTexImage")
    node.image = image
    node.location = (x, y)
    node.interpolation = "Linear"
    return node


def apply_cuticle(mat, maps, roughness, tint=(1, 1, 1)):
    tree = mat.node_tree
    tree.nodes.clear()
    nodes, links = tree.nodes, tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (620, 40)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (340, 40)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Coat Weight"].default_value = 0.0
    bsdf.inputs["Specular IOR Level"].default_value = 0.22
    color = image_node(nodes, maps[0], -570, 200)
    tint_node = nodes.new("ShaderNodeVectorMath")
    tint_node.operation = "MULTIPLY"
    tint_node.location = (30, 230)
    tint_node.inputs[1].default_value = tint
    micro = image_node(nodes, maps[1], -570, -30)
    micro.image.colorspace_settings.name = "Non-Color"
    micro.image.pack()
    rough = image_node(nodes, maps[2], -570, -260)
    rough.image.colorspace_settings.name = "Non-Color"
    rough.image.pack()
    bump = nodes.new("ShaderNodeBump")
    bump.location = (80, -80)
    bump.inputs["Strength"].default_value = 0.36
    bump.inputs["Distance"].default_value = 0.016
    rough_mix = nodes.new("ShaderNodeMapRange")
    rough_mix.location = (80, -270)
    rough_mix.inputs["From Min"].default_value = 0
    rough_mix.inputs["From Max"].default_value = 1
    rough_mix.inputs["To Min"].default_value = roughness - 0.13
    rough_mix.inputs["To Max"].default_value = roughness + 0.13
    links.new(color.outputs["Color"], tint_node.inputs[0])
    links.new(tint_node.outputs["Vector"], bsdf.inputs["Base Color"])
    links.new(micro.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(rough.outputs["Color"], rough_mix.inputs["Value"])
    links.new(rough_mix.outputs["Result"], bsdf.inputs["Roughness"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])


apply_cuticle(bpy.data.materials["thorax | amber cuticle"], thorax_maps, 0.63)
apply_cuticle(bpy.data.materials["thorax | ochre highlight"], thorax_maps, 0.65,
              (1.20, 1.24, 1.16))
apply_cuticle(bpy.data.materials["head | warm honey"], head_maps, 0.61)
apply_cuticle(bpy.data.materials["abdomen | chestnut"], abdomen_maps, 0.58,
              (0.84, 0.81, 0.85))
apply_cuticle(bpy.data.materials["abdomen | tergite gold"], abdomen_maps, 0.59,
              (1.27, 1.35, 1.29))
apply_cuticle(bpy.data.materials["abdomen | male dark bands"], abdomen_maps, 0.63,
              (0.23, 0.27, 0.33))


def abdomen_uv(obj):
    uv_layer = obj.data.uv_layers.new(name="longitudinal abdomen")
    for poly in obj.data.polygons:
        for loop_index in poly.loop_indices:
            vertex_index = obj.data.loops[loop_index].vertex_index
            p = obj.data.vertices[vertex_index].co
            x = np.clip((p.x - 0.47) / (2.04 - 0.47), 0, 1)
            angle = math.atan2((p.z - 1.15) / 0.43, p.y / 0.49)
            uv_layer.data[loop_index].uv = (float(x), (angle / (2 * math.pi)) % 1)


abdomen_uv(bpy.data.objects["02 abdomen | male tergites"])

# Lens mesh lacks a UV map. Its generated X/Z coordinates provide one shared
# pigment field across the entire compound eye, not a repeated image per facet.
for mat in [bpy.data.materials["eye | deep garnet base"]] + [
    bpy.data.materials["eye facet | %02d" % i] for i in range(8)
]:
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    bsdf = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-620, 100)
    separate = nodes.new("ShaderNodeSeparateXYZ")
    separate.location = (-410, 100)
    combine = nodes.new("ShaderNodeCombineXYZ")
    combine.location = (-210, 100)
    image = image_node(nodes, eye_map, 0, 120)
    links.new(coord.outputs["Generated"], separate.inputs["Vector"])
    links.new(separate.outputs["X"], combine.inputs["X"])
    links.new(separate.outputs["Z"], combine.inputs["Y"])
    links.new(combine.outputs["Vector"], image.inputs["Vector"])
    links.new(image.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.25 if "facet" in mat.name else 0.34
    bsdf.inputs["Coat Weight"].default_value = 0.28

for side in (-1, 1):
    obj = bpy.data.objects["wing | %s thin membrane" % side]
    uv_layer = obj.data.uv_layers.new(name="root to tip")
    for poly in obj.data.polygons:
        for loop_index in poly.loop_indices:
            vertex_index = obj.data.loops[loop_index].vertex_index
            uv_layer.data[loop_index].uv = (vertex_index // 13 / 26,
                                            (vertex_index % 13) / 12)

wing_mat = bpy.data.materials["wing | translucent membrane"]
nodes, links = wing_mat.node_tree.nodes, wing_mat.node_tree.links
wing_image = image_node(nodes, wing_map, -550, -150)
principled = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
mix = next(n for n in nodes if n.type == "MIX_SHADER")
links.new(wing_image.outputs["Color"], principled.inputs["Base Color"])
links.new(wing_image.outputs["Alpha"], mix.inputs[0])
principled.inputs["Roughness"].default_value = 0.31

scene = bpy.context.scene
scene.camera = bpy.data.objects["macro three-quarter camera"]
scene.render.resolution_x = 1800
scene.render.resolution_y = 1350
scene.cycles.samples = 96
scene.render.filepath = str(OUTPUT / "male_drosophila_textured_macro.png")
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "CUDA"
    prefs.get_devices()
    if any(d.type == "CUDA" for d in prefs.devices):
        for device in prefs.devices:
            device.use = device.type == "CUDA"
        scene.cycles.device = "GPU"
except Exception as exc:
    scene.cycles.device = "CPU"
    print("CYCLES_CPU_FALLBACK", exc)

bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "male_drosophila_textured.blend"))
bpy.ops.render.render(write_still=True)
print("ARTIFACT", scene.render.filepath)

scene.camera = bpy.data.objects["compound eye and thorax detail camera"]
scene.render.filepath = str(OUTPUT / "male_drosophila_textured_detail.png")
scene.cycles.samples = 96
bpy.ops.render.render(write_still=True)
print("ARTIFACT", scene.render.filepath)

scene.camera = bpy.data.objects["macro three-quarter camera"]
scene.render.filepath = str(OUTPUT / "male_drosophila_textured_macro.png")
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "male_drosophila_textured.blend"))
