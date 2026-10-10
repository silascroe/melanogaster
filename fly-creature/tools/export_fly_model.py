"""Export the packed Blender art study as a self-contained Godot glTF asset.

Usage from FlyTest root:
  tools/blender/blender-5.2.2-windows-x64/blender.exe -b \
    fly-creature/art/male_drosophila_textured.blend --python \
    fly-creature/tools/export_fly_model.py

The .blend is the editable art source. This script makes simpler glTF-compatible
materials, converts curve hairs/veins to meshes, and retains separate wing
pivots for Godot animation. It does not alter the source .blend.
"""

from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector


PROJECT = Path(__file__).resolve().parents[1]
MAPS = PROJECT / "art" / "export_maps"
MAPS.mkdir(parents=True, exist_ok=True)
DEST = PROJECT / "godot" / "assets" / "male_drosophila.glb"
DEST.parent.mkdir(parents=True, exist_ok=True)


def pixel_array(image):
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    return pixels.reshape((height, width, 4))


def write_image(name, pixels, non_color=False):
    height, width, _ = pixels.shape
    image = bpy.data.images.new(name, width=width, height=height, alpha=True)
    image.pixels.foreach_set(np.clip(pixels, 0, 1).astype(np.float32).ravel())
    image.file_format = "PNG"
    image.filepath_raw = str(MAPS / (name + ".png"))
    image.save()
    image.filepath = str(MAPS / (name + ".png"))
    if non_color:
        image.colorspace_settings.name = "Non-Color"
    return image


def tinted_image(source, name, tint):
    pixels = pixel_array(bpy.data.images[source]).copy()
    pixels[:, :, :3] *= np.asarray(tint, dtype=np.float32)
    return write_image(name, pixels)


def normal_image(source, name):
    height = pixel_array(bpy.data.images[source])[:, :, 0]
    dy, dx = np.gradient(height)
    strength = 20.0
    nx, ny, nz = -dx * strength, -dy * strength, np.ones_like(height)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    rgb = np.stack((0.5 + 0.5 * nx / norm,
                    0.5 + 0.5 * ny / norm,
                    0.5 + 0.5 * nz / norm), axis=-1)
    rgba = np.dstack((rgb, np.ones_like(height)))
    return write_image(name, rgba, non_color=True)


normal_maps = {
    part: normal_image(part + "_microheight", part + "_normal")
    for part in ("thorax", "head", "abdomen")
}


def build_material(name, color_image, rough_image=None, normal_map=None,
                   alpha=False, roughness=0.55):
    mat = bpy.data.materials[name]
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    links = mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (620, 80)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (320, 80)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = 0.28
    color = nodes.new("ShaderNodeTexImage")
    color.location = (-480, 260)
    color.image = color_image
    links.new(color.outputs["Color"], bsdf.inputs["Base Color"])
    if alpha:
        links.new(color.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.surface_render_method = "DITHERED"
        mat.use_backface_culling = False
    if rough_image is not None:
        rough = nodes.new("ShaderNodeTexImage")
        rough.location = (-480, -60)
        rough.image = rough_image
        rough.image.colorspace_settings.name = "Non-Color"
        links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    if normal_map is not None:
        normal_tex = nodes.new("ShaderNodeTexImage")
        normal_tex.location = (-480, -360)
        normal_tex.image = normal_map
        normal_node = nodes.new("ShaderNodeNormalMap")
        normal_node.location = (60, -240)
        normal_node.inputs["Strength"].default_value = 0.48
        links.new(normal_tex.outputs["Color"], normal_node.inputs["Color"])
        links.new(normal_node.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])


specs = [
    ("thorax | amber cuticle", "thorax", (1, 1, 1), 0.63),
    ("thorax | ochre highlight", "thorax", (1.20, 1.24, 1.16), 0.65),
    ("head | warm honey", "head", (1, 1, 1), 0.61),
    ("abdomen | chestnut", "abdomen", (0.84, 0.81, 0.85), 0.58),
    ("abdomen | tergite gold", "abdomen", (1.27, 1.35, 1.29), 0.59),
    ("abdomen | male dark bands", "abdomen", (0.23, 0.27, 0.33), 0.63),
]
for material_name, part, tint, roughness in specs:
    slug = material_name.split("|")[1].strip().replace(" ", "_")
    color = tinted_image(part + "_color", part + "_" + slug, tint)
    build_material(material_name, color, bpy.data.images[part + "_roughness"],
                   normal_maps[part], roughness=roughness)

eye_image = bpy.data.images["eye_pigment"]
for name in ["eye | deep garnet base"] + ["eye facet | %02d" % i for i in range(8)]:
    build_material(name, eye_image, roughness=0.26)

# Godot's realtime translucent wings need more opacity than the studio Cycles
# version. Keep the color map, but lift alpha without making them solid.
wing_pixels = pixel_array(bpy.data.images["wing_membrane"]).copy()
wing_pixels[:, :, 3] = np.clip(wing_pixels[:, :, 3] * 2.1, 0.24, 0.58)
wing_game_image = write_image("wing_membrane_game", wing_pixels)
build_material("wing | translucent membrane", wing_game_image,
               alpha=True, roughness=0.35)

# Blender's leg cuticle used procedural noise, which glTF does not carry into
# Godot. Give the reusable asset a subtle image-based cuticle variation instead
# of exporting six uniformly colored plastic-looking legs.
leg_size = 512
leg_rng = np.random.default_rng(340617)
leg_noise = leg_rng.random((leg_size, leg_size), dtype=np.float32)
for _ in range(7):
    leg_noise = (leg_noise + np.roll(leg_noise, 1, 0)
                 + np.roll(leg_noise, -1, 0)
                 + np.roll(leg_noise, 1, 1)
                 + np.roll(leg_noise, -1, 1)) / 5.0
leg_v = np.arange(leg_size, dtype=np.float32)[:, None] / leg_size
leg_grain = (leg_noise - 0.5) * 0.42 + 0.055 * np.sin(leg_v * 36 * np.pi)
leg_base = np.array((0.26, 0.145, 0.080), dtype=np.float32)
leg_rgb = np.clip(leg_base[None, None, :] *
                  (1.0 + leg_grain[:, :, None]), 0, 1)
leg_rgba = np.dstack((leg_rgb, np.ones((leg_size, leg_size), dtype=np.float32)))
leg_cuticle = write_image("leg_cuticle_game", leg_rgba)
build_material("legs | warm brown", leg_cuticle, roughness=0.58)
build_material("joints | dark umber",
               tinted_image("leg_cuticle_game", "leg_joint_game", (0.43, 0.39, 0.37)),
               roughness=0.62)
build_material("tarsi | dark brown",
               tinted_image("leg_cuticle_game", "leg_tarsus_game", (0.55, 0.49, 0.45)),
               roughness=0.63)

# The original faceted eye has one joined mesh per side and no UVs because its
# Blender shader used Generated coordinates. Map each lens vertex across X/Z.
for side in (-1, 1):
    obj = bpy.data.objects["eye | %s individual ommatidia" % side]
    xs = [v.co.x for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    uv = obj.data.uv_layers.new(name="eye pigment XZ")
    for poly in obj.data.polygons:
        for loop_index in poly.loop_indices:
            p = obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
            uv.data[loop_index].uv = ((p.x - x0) / (x1 - x0),
                                      (p.z - z0) / (z1 - z0))

# Export only the fly. The floor, studio cameras, and lights are presentation
# equipment; carrying them into the creature scene would be a nasty surprise.
for obj in list(bpy.data.objects):
    if obj.type in {"LIGHT", "CAMERA"} or obj.name == "studio macro surface":
        bpy.data.objects.remove(obj, do_unlink=True)

# glTF does not render Blender curve bevels as fly hairs or veins. Convert all
# 27 curves to meshes while preserving their materials and object names.
for obj in list(bpy.data.objects):
    if obj.type == "CURVE":
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.convert(target="MESH")

# Keep the sculpted leg meshes but split their transforms at the knees. A foot
# marker lets Godot solve a two-segment pose for a planted or lifted foot.
# This is presentation rigging, not insect muscle simulation.
for side, side_name, first_ordinal in ((-1, "Neg", 0), (1, "Pos", 3)):
    for leg_index, hip_x in enumerate((-0.34, 0.05, 0.42)):
        ordinal = first_ordinal + leg_index
        prefix = "leg %s.%s " % (side, leg_index)
        knee_location = bpy.data.objects[prefix + "knee"].matrix_world.translation.copy()
        claws = [bpy.data.objects["claw" if ordinal * 2 + i == 0
                                  else "claw.%03d" % (ordinal * 2 + i)]
                 for i in (0, 1)]
        claw_tip_z = min((obj.matrix_world @ vertex.co).z
                         for obj in claws for vertex in obj.data.vertices)
        foot_location = Vector((
            sum(obj.matrix_world.translation.x for obj in claws) / 2,
            sum(obj.matrix_world.translation.y for obj in claws) / 2,
            claw_tip_z,
        ))
        pivot = bpy.data.objects.new("Leg%s%dPivot" % (side_name, leg_index), None)
        bpy.context.collection.objects.link(pivot)
        pivot.location = (hip_x, side * 0.31, 0.99)
        bpy.context.view_layer.update()

        knee_pivot = bpy.data.objects.new(
            "Leg%s%dKneePivot" % (side_name, leg_index), None)
        bpy.context.collection.objects.link(knee_pivot)
        knee_world = Matrix.Translation(knee_location)
        knee_pivot.matrix_world = knee_world
        knee_pivot.parent = pivot
        knee_pivot.matrix_world = knee_world

        foot = bpy.data.objects.new("Leg%s%dFoot" % (side_name, leg_index), None)
        bpy.context.collection.objects.link(foot)
        foot_world = Matrix.Translation(foot_location)
        foot.matrix_world = foot_world
        foot.parent = knee_pivot
        foot.matrix_world = foot_world

        leg_parts = [obj for obj in bpy.data.objects if obj.name.startswith(prefix)]
        upper = [obj for obj in leg_parts
                 if "tibia" not in obj.name and "tarsus" not in obj.name]
        lower = [obj for obj in leg_parts
                 if "tibia" in obj.name or "tarsus" in obj.name]
        lower.extend(claws)
        setae = "tibial setae" if ordinal == 0 else "tibial setae.%03d" % ordinal
        lower.append(bpy.data.objects[setae])
        if leg_index == 0:
            comb = "male foreleg | sex comb" if side == -1 else "male foreleg | sex comb.001"
            lower.append(bpy.data.objects[comb])
        for obj in upper + lower:
            old_world = obj.matrix_world.copy()
            obj.parent = pivot if obj in upper else knee_pivot
            obj.matrix_world = old_world

for side, pivot_name in ((-1, "WingNearPivot"), (1, "WingFarPivot")):
    pivot = bpy.data.objects.new(pivot_name, None)
    bpy.context.collection.objects.link(pivot)
    pivot.location = (0.06, side * 0.43, 1.59)
    bpy.context.view_layer.update()
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and obj.name.startswith("wing | %s " % side):
            old_world = obj.matrix_world.copy()
            obj.parent = pivot
            obj.matrix_world = old_world

root = bpy.data.objects.new("FlyVisual", None)
bpy.context.collection.objects.link(root)
for obj in list(bpy.data.objects):
    if obj != root and obj.parent is None:
        old_world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = old_world

bpy.ops.object.select_all(action="SELECT")
bpy.context.view_layer.objects.active = root
bpy.ops.export_scene.gltf(
    filepath=str(DEST),
    export_format="GLB",
    use_selection=True,
    export_cameras=False,
    export_lights=False,
    export_animations=False,
    export_materials="EXPORT",
    export_apply=False,
)
print("FLY_GLB", DEST, DEST.stat().st_size)
