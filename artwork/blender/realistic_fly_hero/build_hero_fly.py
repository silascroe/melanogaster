"""Build a standalone, high-detail procedural male Drosophila macro scene.

This is a new scene. It deliberately does not alter the Decision Chamber or
the earlier realistic-fly study.

Run from any working directory with:
    blender.exe -b --python-exit-code 1 --python artwork/blender/realistic_fly_hero/build_hero_fly.py
"""

from __future__ import annotations

import bisect
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


RNG = random.Random(20260924)
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
SCENE_PATH = SCRIPT_DIR / "male_drosophila_hero.blend"
RENDER_PATH = REPO_ROOT / "outputs" / "blender" / "realistic-fly-hero" / "male_drosophila_hero.png"
DETAIL_RENDER_PATH = REPO_ROOT / "outputs" / "blender" / "realistic-fly-hero" / "male_drosophila_hero-detail.png"


def new_collection(name):
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def move_to_collection(obj, collection, parent=None):
    for previous in list(obj.users_collection):
        previous.objects.unlink(obj)
    collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def empty(name, collection, parent=None):
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def simple_material(name, color, roughness=0.42, metallic=0.0, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Coat Weight"].default_value = coat
    shader.inputs["Coat Roughness"].default_value = 0.3
    return mat


def cuticle_material(name, color, roughness=0.4, micro_scale=300.0, micro_strength=0.12):
    """Layer restrained color/roughness variation over fine cuticle grain."""
    mat = simple_material(name, color, roughness, coat=0.07)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexCoord")
    broad = nodes.new("ShaderNodeTexNoise")
    broad.inputs["Scale"].default_value = 24.0
    broad.inputs["Detail"].default_value = 3.0
    broad.inputs["Roughness"].default_value = 0.68
    ramp = nodes.new("ShaderNodeValToRGB")
    low = tuple(channel * 0.76 for channel in color) + (1.0,)
    high = tuple(min(1.0, channel * 1.22 + 0.006) for channel in color) + (1.0,)
    ramp.color_ramp.elements[0].color = low
    ramp.color_ramp.elements[1].color = high
    links.new(tex.outputs["Generated"], broad.inputs["Vector"])
    links.new(broad.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])

    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = micro_scale
    fine.inputs["Detail"].default_value = 2.0
    fine.inputs["Roughness"].default_value = 0.74
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = micro_strength
    bump.inputs["Distance"].default_value = 0.012
    links.new(tex.outputs["Generated"], fine.inputs["Vector"])
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])

    roughness_range = nodes.new("ShaderNodeMapRange")
    roughness_range.inputs["To Min"].default_value = max(0.16, roughness - 0.08)
    roughness_range.inputs["To Max"].default_value = min(0.9, roughness + 0.1)
    links.new(broad.outputs["Fac"], roughness_range.inputs["Value"])
    links.new(roughness_range.outputs["Result"], shader.inputs["Roughness"])
    return mat


def add_uv_sphere(name, location, scale, mat, collection, parent=None,
                  segments=48, rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, radius=1.0, location=location
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    for poly in obj.data.polygons:
        poly.use_smooth = True
    if mat:
        obj.data.materials.append(mat)
    return move_to_collection(obj, collection, parent)


def add_curve_bundle(name, paths, radius, mat, collection, parent=None,
                     resolution=1, bevel_resolution=2):
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = radius
    curve.bevel_resolution = bevel_resolution
    curve.use_fill_caps = True
    for path in paths:
        if len(path) < 2:
            continue
        spline = curve.splines.new("POLY")
        spline.points.add(len(path) - 1)
        for point, coordinate in zip(spline.points, path):
            point.co = (*Vector(coordinate), 1.0)
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    curve.materials.append(mat)
    if parent is not None:
        obj.parent = parent
    return obj


def add_tapered_link(name, start, end, radius_start, radius_end, mat,
                     collection, parent=None, sides=16):
    start, end = Vector(start), Vector(end)
    delta = end - start
    bpy.ops.mesh.primitive_cone_add(
        vertices=sides, radius1=radius_start, radius2=radius_end,
        depth=max(delta.length, 0.0001), location=(start + end) * 0.5,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = delta.to_track_quat("Z", "Y")
    for poly in obj.data.polygons:
        poly.use_smooth = len(poly.vertices) == 4
    obj.data.materials.append(mat)
    return move_to_collection(obj, collection, parent)


def catmull(points, t):
    """Catmull-Rom interpolation for compact, art-directable body profiles."""
    n = len(points)
    scaled = max(0.0, min(0.999999, t)) * (n - 1)
    index = int(scaled)
    u = scaled - index
    p0 = points[max(0, index - 1)]
    p1 = points[index]
    p2 = points[min(n - 1, index + 1)]
    p3 = points[min(n - 1, index + 2)]
    return tuple(
        0.5 * ((2 * a) + (-p0[j] + p2[j]) * u
               + (2 * p0[j] - 5 * a + 4 * p2[j] - p3[j]) * u * u
               + (-p0[j] + 3 * a - 3 * p2[j] + p3[j]) * u * u * u)
        for j, a in enumerate(p1)
    )


def make_x_shell(name, x_start, x_end, profile, axial_steps, radial_steps,
                 mat, collection, parent=None, segmentation=None):
    """Closed smooth surface swept along X from (ry, rz, center_z) profiles."""
    vertices, faces, material_indices = [], [], []
    for i in range(axial_steps + 1):
        u = i / axial_steps
        ry, rz, center_z = catmull(profile, u)
        x = x_start + (x_end - x_start) * u
        for j in range(radial_steps):
            angle = math.tau * j / radial_steps
            vertices.append((x, ry * math.cos(angle), center_z + rz * math.sin(angle)))
    for i in range(axial_steps):
        x_center = x_start + (x_end - x_start) * (i + 0.5) / axial_steps
        for j in range(radial_steps):
            a = i * radial_steps + j
            a_next = i * radial_steps + ((j + 1) % radial_steps)
            b = (i + 1) * radial_steps + j
            b_next = (i + 1) * radial_steps + ((j + 1) % radial_steps)
            faces.append((a, a_next, b_next, b))
            if segmentation is None:
                material_indices.append(0)
            else:
                bounds, segment_mats = segmentation
                seg = max(0, min(len(bounds) - 2, bisect.bisect_right(bounds, x_center) - 1))
                fraction = (x_center - bounds[seg]) / (bounds[seg + 1] - bounds[seg])
                if seg >= 4:
                    material_indices.append(segment_mats[seg][0])
                elif fraction > 0.78:
                    material_indices.append(segment_mats[seg][1])
                else:
                    material_indices.append(segment_mats[seg][0])
    start_center = len(vertices)
    vertices.append((x_start, 0.0, profile[0][2]))
    end_center = len(vertices)
    vertices.append((x_end, 0.0, profile[-1][2]))
    for j in range(radial_steps):
        next_j = (j + 1) % radial_steps
        faces.append((start_center, next_j, j))
        faces.append((end_center, axial_steps * radial_steps + j,
                      axial_steps * radial_steps + next_j))
        if segmentation is not None:
            material_indices.extend((0, segment_mats[-1][0]))
        else:
            material_indices.extend((0, 0))

    mesh = bpy.data.meshes.new(name + " · precision shell mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if isinstance(mat, (tuple, list)):
        for slot_mat in mat:
            mesh.materials.append(slot_mat)
        for poly, mat_index in zip(mesh.polygons, material_indices):
            poly.material_index = mat_index
    else:
        mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = True
    if parent is not None:
        obj.parent = parent
    return obj


def ellipsoid_point(center, scale, latitude, longitude):
    c = math.cos(latitude)
    return Vector((
        center[0] + scale[0] * c * math.cos(longitude),
        center[1] + scale[1] * c * math.sin(longitude),
        center[2] + scale[2] * math.sin(latitude),
    ))


def add_ellipsoid_setae(name, center, scale, count, max_length, radius, mat,
                        collection, parent, dorsal=True, seed_offset=0):
    rng = random.Random(20260924 + seed_offset)
    paths = []
    for index in range(count):
        longitude = math.tau * ((index * 0.61803398875) % 1.0)
        if dorsal:
            z_fraction = 0.08 + 0.89 * ((index * 0.754877666) % 1.0)
            latitude = math.asin(z_fraction)
        else:
            latitude = math.asin(rng.uniform(-0.95, 0.95))
        point = ellipsoid_point(center, scale, latitude, longitude)
        normal = Vector(((point.x - center[0]) / scale[0] ** 2,
                         (point.y - center[1]) / scale[1] ** 2,
                         (point.z - center[2]) / scale[2] ** 2)).normalized()
        length = max_length * rng.uniform(0.42, 1.0)
        direction = (normal * 0.76 + Vector((0.24, rng.uniform(-0.12, 0.12), 0.27))).normalized()
        paths.append((point, point + direction * (length * 0.55), point + direction * length))
    return add_curve_bundle(name, paths, radius, mat, collection, parent)


def make_compound_eye(name, center, scale, collection, parent, palette):
    vertices, faces, material_indices = [], [], []
    radius_x, radius_y, radius_z = scale
    lens_count = 0
    step = 0.027
    row_count = 31
    for row in range(row_count):
        latitude = -1.24 + row * (2.48 / (row_count - 1))
        circumference = max(13, round(math.tau * max(radius_x, radius_y)
                                      * math.cos(latitude) / step))
        phase = (row % 2) * math.pi / circumference
        for col in range(circumference):
            longitude = math.tau * col / circumference + phase
            point = ellipsoid_point(center, scale, latitude, longitude)
            normal = Vector(((point.x - center[0]) / radius_x ** 2,
                             (point.y - center[1]) / radius_y ** 2,
                             (point.z - center[2]) / radius_z ** 2)).normalized()
            tangent = Vector((0.0, 0.0, 1.0)).cross(normal)
            if tangent.length_squared < 1e-8:
                tangent = Vector((1.0, 0.0, 0.0)).cross(normal)
            tangent.normalize()
            bitangent = normal.cross(tangent).normalized()
            first = len(vertices)
            vertices.append(tuple(point + normal * 0.0035))
            lens_radius = step * 0.43
            for corner in range(6):
                angle = math.tau * corner / 6.0
                rim = point + tangent * (math.cos(angle) * lens_radius)
                rim += bitangent * (math.sin(angle) * lens_radius)
                vertices.append(tuple(rim + normal * 0.0015))
            tint = RNG.randrange(len(palette))
            for corner in range(6):
                faces.append((first, first + 1 + corner,
                              first + 1 + ((corner + 1) % 6)))
                material_indices.append(tint)
            lens_count += 1
    mesh = bpy.data.meshes.new(name + " · hexagonal corneal lens mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for mat in palette:
        mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    for polygon, material_index in zip(mesh.polygons, material_indices):
        polygon.material_index = material_index
    obj.parent = parent
    obj["lens_count"] = lens_count
    obj["construction"] = "individually shaded hexagonal corneal facets"
    return obj


def wing_point(t, across, side):
    center = Vector((-0.12 + 1.53 * t,
                     side * (0.24 + 0.62 * t),
                     1.19 + 0.07 * math.sin(math.pi * t) - 0.045 * t + side * 0.012))
    tangent = Vector((1.53, side * 0.62, 0.0)).normalized()
    perpendicular = Vector((-tangent.y, tangent.x, 0.0))
    width = 0.025 + 0.315 * (math.sin(math.pi * t) ** 0.73) * (0.92 + 0.08 * t)
    point = center + perpendicular * (across * width)
    point.z += 0.04 * (1.0 - across * across) * math.sin(math.pi * t)
    return point


def make_wing(side_name, side, collection, parent, membrane_mat, vein_mat):
    nx, ny = 56, 24
    vertices, faces = [], []
    for i in range(nx + 1):
        t = i / nx
        for j in range(ny + 1):
            across = -1.0 + 2.0 * j / ny
            vertices.append(tuple(wing_point(t, across, side)))
    for i in range(nx):
        for j in range(ny):
            a = i * (ny + 1) + j
            b = a + ny + 1
            faces.append((a, b, b + 1, a + 1))
    mesh = bpy.data.meshes.new(f"Hyaline wing membrane mesh · {side_name}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(membrane_mat)
    membrane = bpy.data.objects.new(f"Hyaline wing membrane · {side_name}", mesh)
    collection.objects.link(membrane)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    membrane.parent = parent
    membrane["wing_surface"] = "thin chitin film, modeled as a curved mesh"

    paths = []
    # Five longitudinal veins, the costa/subcosta, basal vein, and two crossveins.
    for index, across0 in enumerate((-0.68, -0.39, -0.08, 0.25, 0.56)):
        path = []
        for sample in range(38):
            t = 0.035 + 0.92 * sample / 37
            across = across0 + 0.035 * math.sin(math.pi * t + index * 0.63)
            path.append(wing_point(t, across, side))
        paths.append(path)
    paths.append([wing_point(0.015 + 0.95 * k / 42, 0.91, side) for k in range(43)])
    paths.append([wing_point(0.02 + 0.78 * k / 34, 0.72, side) for k in range(35)])
    paths.append([wing_point(0.12 + 0.20 * k / 18, -0.72 + 1.52 * k / 18, side)
                  for k in range(19)])
    paths.append([wing_point(0.39 + 0.12 * math.sin(math.pi * k / 22),
                             -0.58 + 1.35 * k / 22, side) for k in range(23)])
    paths.append([wing_point(0.66 + 0.08 * math.sin(math.pi * k / 22),
                             -0.46 + 1.18 * k / 22, side) for k in range(23)])
    # Delicate short branches suggest the fine anastomosing network without clutter.
    for t0 in (0.25, 0.52, 0.75):
        paths.append([wing_point(t0 + 0.06 * k / 12, -0.18 + 0.36 * k / 12, side)
                      for k in range(13)])
    veins = add_curve_bundle(f"Wing vein network · {side_name}", paths, 0.0028,
                             vein_mat, collection, parent, bevel_resolution=2)
    veins["vein_count"] = len(paths)
    veins["longitudinal_veins"] = 5
    veins["crossveins"] = 2
    return membrane, veins


def make_leg(pair, side_name, side_sign, start, knee, ankle, toe, collection, fly_root,
             leg_mat, dark_mat, joint_mat, seta_mat, comb_mat):
    start, knee, ankle, toe = map(Vector, (start, knee, ankle, toe))
    root = empty(f"Leg assembly · {pair} {side_name}", collection, fly_root)
    coxa_end = start.lerp(knee, 0.20)
    add_tapered_link(f"{pair} {side_name} coxa", start, coxa_end,
                     0.055, 0.042, leg_mat, collection, root)
    add_uv_sphere(f"{pair} {side_name} coxal joint", coxa_end,
                  (0.047, 0.046, 0.048), joint_mat, collection, root, 24, 16)
    add_tapered_link(f"{pair} {side_name} femur", coxa_end, knee,
                     0.057, 0.033, leg_mat, collection, root, sides=20)
    add_uv_sphere(f"{pair} {side_name} knee", knee, (0.037, 0.035, 0.037),
                  joint_mat, collection, root, 20, 14)
    add_tapered_link(f"{pair} {side_name} tibia", knee, ankle,
                     0.029, 0.014, dark_mat, collection, root)
    add_uv_sphere(f"{pair} {side_name} tibio-tarsal joint", ankle,
                  (0.022, 0.021, 0.022), joint_mat, collection, root, 16, 12)

    nodes = [ankle]
    for fraction in (0.25, 0.48, 0.68, 0.84, 1.0):
        nodes.append(ankle.lerp(toe, fraction))
    for index, (a, b) in enumerate(zip(nodes[:-1], nodes[1:]), 1):
        add_tapered_link(f"{pair} {side_name} tarsomere {index}", a, b,
                         0.014 - 0.0014 * (index - 1),
                         0.012 - 0.0014 * (index - 1), dark_mat, collection, root, sides=12)
        if index < 5:
            add_uv_sphere(f"{pair} {side_name} tarsal joint {index}", b,
                          (0.014, 0.013, 0.014), joint_mat, collection, root, 14, 10)

    # Longitudinal tibial spines and short setae give the limbs a fine silhouette.
    axis = (ankle - knee).normalized()
    normal = axis.cross(Vector((0, 1, 0)))
    if normal.length_squared < 1e-8:
        normal = axis.cross(Vector((1, 0, 0)))
    normal.normalize()
    spine_paths = []
    for index in range(13):
        t = 0.10 + 0.063 * index
        point = knee.lerp(ankle, t)
        direction = (normal * side_sign + Vector((0.0, 0.0, 0.18))).normalized()
        length = 0.026 * (1.0 - 0.22 * abs(t - 0.5))
        spine_paths.append((point, point + direction * length * 0.7,
                            point + direction * length))
    add_curve_bundle(f"{pair} {side_name} tibial spines", spine_paths,
                     0.0016, seta_mat, collection, root)

    claw_paths = []
    for offset in (-1, 1):
        claw_paths.append((toe, toe + Vector((0.018, side_sign * offset * 0.009, -0.005)),
                           toe + Vector((0.032, side_sign * offset * 0.015, 0.004))))
    add_curve_bundle(f"{pair} {side_name} paired claws", claw_paths,
                     0.0022, dark_mat, collection, root)

    if pair == "fore":
        # The D. melanogaster male sex comb is an array of modified first-tarsomere bristles.
        direction = (nodes[1] - nodes[0]).normalized()
        comb_direction = direction.cross(Vector((0.0, 1.0, 0.0))).normalized()
        teeth = []
        for index in range(11):
            t = 0.22 + 0.052 * index
            base = nodes[0].lerp(nodes[1], t)
            mid = base + comb_direction * 0.018 + direction * 0.005
            tip = base + comb_direction * 0.031 + direction * 0.012
            teeth.append((base, mid, tip))
        comb = add_curve_bundle(f"Male sex comb · {side_name} fore tarsus", teeth,
                                0.0025, comb_mat, collection, root)
        comb["tooth_count"] = len(teeth)
    return root


def add_area_light(name, location, target, power, color, size, collection):
    light_data = bpy.data.lights.new(name, type="AREA")
    light_data.energy = power
    light_data.color = color
    light_data.shape = "DISK"
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    collection.objects.link(light)
    light.location = location
    light.rotation_euler = (Vector(target) - light.location).to_track_quat("-Z", "Y").to_euler()
    return light


def make_camera(collection, name="Hero macro camera · 85 mm",
                location=(-4.25, -7.0, 3.2), target=(0.0, 0.0, 0.85),
                lens=85.0, focus_location=(-0.55, -0.12, 0.91), fstop=20.0):
    data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, data)
    collection.objects.link(camera)
    camera.location = location
    target = Vector(target)
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    data.lens = lens
    data.dof.use_dof = True
    data.dof.aperture_fstop = fstop
    data.dof.aperture_blades = 9
    focus = bpy.data.objects.new("Focus target · " + name, None)
    collection.objects.link(focus)
    focus.location = focus_location
    data.dof.focus_object = focus
    bpy.context.scene.camera = camera
    return camera


def create_fly(collection):
    root = empty("Drosophila · hero model root", collection)

    amber = cuticle_material("Cuticle · amber notum", (0.24, 0.092, 0.027), 0.43, 360, 0.11)
    thorax_side = cuticle_material("Cuticle · shaded pleura", (0.105, 0.038, 0.016), 0.49, 280, 0.10)
    head_mat = cuticle_material("Cuticle · head capsule", (0.19, 0.065, 0.021), 0.41, 360, 0.10)
    scutellum_mat = cuticle_material("Cuticle · scutellum", (0.21, 0.076, 0.020), 0.44, 310, 0.1)
    leg_mat = cuticle_material("Cuticle · proximal leg amber", (0.19, 0.062, 0.018), 0.39, 300, 0.10)
    dark_leg_mat = cuticle_material("Cuticle · distal leg brown", (0.075, 0.024, 0.010), 0.37, 320, 0.08)
    joint_mat = cuticle_material("Cuticle · leg articulations", (0.11, 0.036, 0.012), 0.43, 330, 0.08)
    bristle_mat = simple_material("Setae · chestnut chitin", (0.105, 0.037, 0.014), 0.52)
    seta_light = simple_material("Setae · fine golden microtrichia", (0.18, 0.073, 0.024), 0.48)
    comb_mat = simple_material("Sex comb · melanized teeth", (0.026, 0.009, 0.005), 0.42)
    mouth_mat = cuticle_material("Mouthparts · tawny cuticle", (0.17, 0.063, 0.021), 0.4, 300, 0.08)
    seam_mat = simple_material("Sutures · warm dark brown", (0.055, 0.019, 0.008), 0.5)
    spiracle_mat = simple_material("Spiracles · recessed openings", (0.012, 0.006, 0.003), 0.65)

    eye_base = simple_material("Ocular capsule · deep carmine", (0.065, 0.003, 0.012), 0.37, coat=0.04)
    eye_palette = [
        simple_material("Corneal facets · oxblood", (0.12, 0.003, 0.016), 0.36, coat=0.03),
        simple_material("Corneal facets · ruby", (0.22, 0.006, 0.030), 0.34, coat=0.04),
        simple_material("Corneal facets · wine", (0.095, 0.002, 0.012), 0.38, coat=0.03),
        simple_material("Corneal facets · warm glint", (0.28, 0.012, 0.038), 0.33, coat=0.04),
    ]

    # Continuous ring-defined abdomen, with six independently shaded tergite regions.
    abdomen_x0, abdomen_x1 = 0.10, 1.56
    segment_bounds = [0.10, 0.30, 0.53, 0.77, 1.02, 1.28, 1.56]
    body_profile = [
        (0.245, 0.205, 0.76), (0.335, 0.285, 0.75),
        (0.375, 0.305, 0.73), (0.360, 0.300, 0.70),
        (0.325, 0.274, 0.675), (0.270, 0.238, 0.65),
        (0.188, 0.174, 0.625), (0.045, 0.055, 0.61),
    ]
    segment_colors = [
        (0.23, 0.087, 0.025), (0.29, 0.112, 0.032),
        (0.27, 0.092, 0.025), (0.22, 0.066, 0.019),
        (0.035, 0.012, 0.008), (0.024, 0.008, 0.006),
    ]
    abdomen_mats = []
    for index, color in enumerate(segment_colors):
        base = cuticle_material(f"Tergite A{index + 1} · cuticle", color,
                                0.42 if index < 4 else 0.38, 380, 0.12)
        posterior = (cuticle_material(f"Tergite A{index + 1} · posterior pigment band",
                                      (0.11, 0.034, 0.012) if index < 3 else (0.075, 0.023, 0.009),
                                      0.39, 340, 0.1) if index < 4 else base)
        abdomen_mats.append((base, posterior))
    flat_slots = [mat for pair in abdomen_mats for mat in pair]
    segment_slots = [(2 * i, 2 * i + 1) for i in range(6)]
    abdomen = make_x_shell("Continuous sculpted abdomen shell", abdomen_x0, abdomen_x1,
                           body_profile, 220, 96, flat_slots, collection, root,
                           segmentation=(segment_bounds, segment_slots))
    abdomen["segment_count"] = 6
    abdomen["male_terminal_tergites"] = "A5-A6"
    abdomen["geometry"] = "single smooth manifold shell with region-assigned tergite pigmentation"

    # A ventral sternite surface softens the underside without turning the body into stacked balls.
    ventral_mat = cuticle_material("Sternites · muted ochre", (0.13, 0.046, 0.015), 0.48, 280, 0.08)
    add_uv_sphere("Ventral abdominal sternites", (0.78, 0.0, 0.55),
                  (0.67, 0.265, 0.15), ventral_mat, collection, root, 56, 36)

    # Thoracic shell with gentle lateral taper, separate pleural colors and scutellum.
    thorax_profile = [
        (0.10, 0.15, 0.92), (0.25, 0.28, 0.93),
        (0.37, 0.36, 0.93), (0.40, 0.37, 0.91),
        (0.37, 0.34, 0.88), (0.30, 0.28, 0.84),
        (0.10, 0.12, 0.82),
    ]
    thorax = make_x_shell("Thorax · continuous arched notum", -0.83, 0.49,
                          thorax_profile, 150, 96, amber, collection, root)
    thorax["surface"] = "mottled cuticle with micro-bump and roughness breakup"
    add_uv_sphere("Pleural plate · near", (-0.17, -0.31, 0.72),
                  (0.43, 0.13, 0.24), thorax_side, collection, root)
    add_uv_sphere("Pleural plate · far", (-0.17, 0.31, 0.72),
                  (0.43, 0.13, 0.24), thorax_side, collection, root)
    add_uv_sphere("Scutellum · shell", (0.30, 0.0, 0.91),
                  (0.20, 0.34, 0.19), scutellum_mat, collection, root, 56, 36)
    add_uv_sphere("Haltere root membrane", (0.39, 0.0, 0.86),
                  (0.105, 0.18, 0.105), thorax_side, collection, root)

    # Three understated longitudinal notal vittae and the transverse scutellar suture.
    notal_paths = []
    for y in (-0.15, 0.0, 0.15):
        path = []
        for index in range(40):
            t = index / 39
            x = -0.72 + 0.91 * t
            u = (x + 0.83) / 1.32
            ry, rz, cz = catmull(thorax_profile, u)
            frac = min(0.92, abs(y) / ry)
            z = cz + rz * math.sqrt(max(0.02, 1.0 - frac * frac)) + 0.002
            path.append((x, y + 0.006 * math.sin(t * math.pi * 2), z))
        notal_paths.append(path)
    add_curve_bundle("Notum · three subdued longitudinal vittae", notal_paths,
                     0.010, seam_mat, collection, root)

    # Fine dorsal sutures mark the six abdominal tergite boundaries.
    suture_paths = []
    for x in segment_bounds[1:-1]:
        u = (x - abdomen_x0) / (abdomen_x1 - abdomen_x0)
        ry, rz, cz = catmull(body_profile, u)
        suture_paths.append([
            (x, ry * math.cos(math.pi * i / 32) * 1.002,
             cz + rz * math.sin(math.pi * i / 32) * 1.004)
            for i in range(33)
        ])
    add_curve_bundle("Abdominal tergite sutures", suture_paths, 0.0024,
                     seam_mat, collection, root)

    # Six shallow spiracles, two at each lateral edge of A2-A4.
    for idx, x in enumerate((0.40, 0.62, 0.86), 2):
        u = (x - abdomen_x0) / (abdomen_x1 - abdomen_x0)
        ry, rz, cz = catmull(body_profile, u)
        for side, label in ((-1, "near"), (1, "far")):
            add_uv_sphere(f"Spiracle A{idx} · {label}", (x, side * ry * 0.94, cz - 0.035),
                          (0.022, 0.009, 0.012), spiracle_mat, collection, root, 16, 10)

    # Head capsule and paired faceted eyes.
    head_center = (-0.99, 0.0, 0.92)
    head_scale = (0.355, 0.322, 0.325)
    add_uv_sphere("Head capsule · sculpted", head_center, head_scale,
                  head_mat, collection, root, 80, 56)
    add_uv_sphere("Cervical membrane", (-0.70, 0.0, 0.86),
                  (0.20, 0.23, 0.23), thorax_side, collection, root)
    eye_centers = {"near": (-1.035, -0.244, 0.965), "far": (-1.035, 0.244, 0.965)}
    eye_scale = (0.255, 0.180, 0.286)
    for side_name, center in eye_centers.items():
        add_uv_sphere(f"Ocular capsule · {side_name}", center, eye_scale,
                      eye_base, collection, root, 64, 48)
        make_compound_eye(f"Corneal ommatidia · {side_name}", center,
                          eye_scale, collection, root, eye_palette)

    # Arista-bearing antennae, palps and a compact retractile proboscis.
    antenna_paths = []
    for side in (-1, 1):
        base = Vector((-1.265, side * 0.11, 1.10))
        pedicel = base + Vector((-0.035, side * 0.018, 0.055))
        funiculus = pedicel + Vector((-0.048, side * 0.012, 0.018))
        tip = funiculus + Vector((-0.09, side * 0.01, 0.19))
        antenna_paths.append((base, pedicel, funiculus))
        antenna_paths.append((funiculus, funiculus.lerp(tip, 0.5), tip))
        axis = (tip - funiculus).normalized()
        lateral = axis.cross(Vector((0.0, 1.0, 0.0))).normalized()
        for i in range(10):
            t = 0.12 + i * 0.082
            point = funiculus.lerp(tip, t)
            length = 0.040 * math.sin(math.pi * t) ** 0.6
            for sign in (-1, 1):
                antenna_paths.append((point, point + lateral * sign * length * 0.55,
                                      point + lateral * sign * length))
    aristae = add_curve_bundle("Aristae · plumose pair", antenna_paths, 0.0022,
                               bristle_mat, collection, root)
    aristae["paired_feathered_aristae"] = True
    add_tapered_link("Proboscis · rostrum", (-1.20, 0.0, 0.70),
                     (-1.26, 0.0, 0.50), 0.044, 0.032,
                     mouth_mat, collection, root, sides=24)
    add_uv_sphere("Proboscis · labellum", (-1.265, 0.0, 0.475),
                  (0.075, 0.068, 0.043), mouth_mat, collection, root)
    for side, label in ((-1, "near"), (1, "far")):
        add_uv_sphere(f"Maxillary palp · {label}", (-1.20, side * 0.10, 0.57),
                      (0.055, 0.038, 0.063), mouth_mat, collection, root, 24, 16)

    # Very fine hairs are curves, not a bump map pretending to be visible anatomy.
    thorax_center = (-0.22, 0.0, 0.91)
    thorax_scale = (0.63, 0.39, 0.37)
    add_ellipsoid_setae("Thoracic microtrichia", thorax_center, thorax_scale,
                        3200, 0.036, 0.00062, seta_light, collection, root, True, 1)
    add_ellipsoid_setae("Head capsule fine setae", head_center, head_scale,
                        360, 0.028, 0.00075, bristle_mat, collection, root, True, 2)
    abdomen_paths = []
    for index in range(820):
        x = RNG.uniform(0.25, 1.43)
        u = (x - abdomen_x0) / (abdomen_x1 - abdomen_x0)
        ry, rz, cz = catmull(body_profile, u)
        theta = RNG.uniform(0.20, math.pi - 0.20)
        point = Vector((x, ry * math.cos(theta), cz + rz * math.sin(theta)))
        normal = Vector((0.10, math.cos(theta) / max(ry, 0.01),
                         math.sin(theta) / max(rz, 0.01))).normalized()
        length = RNG.uniform(0.017, 0.037)
        abdomen_paths.append((point, point + normal * length * 0.5,
                              point + normal * length))
    add_curve_bundle("Abdominal cuticular setae", abdomen_paths, 0.00095,
                     bristle_mat, collection, root)

    # Bilateral, ordered macrochaetae on the thorax read as insect bristles, not fur.
    macro_paths = []
    for side in (-1, 1):
        for x in (-0.60, -0.42, -0.20, 0.02, 0.20):
            for y in (0.12, 0.24, 0.32):
                t = (x + 0.83) / 1.32
                ry, rz, cz = catmull(thorax_profile, t)
                frac = min(0.88, y / ry)
                point = Vector((x, side * y, cz + rz * math.sqrt(1 - frac * frac)))
                normal = Vector((0.0, side * y / ry ** 2,
                                 math.sqrt(max(0.02, 1 - frac * frac)) / rz)).normalized()
                length = RNG.uniform(0.065, 0.115)
                direction = (normal * 0.72 + Vector((0.2, side * 0.12, 0.34))).normalized()
                macro_paths.append((point, point + direction * length * 0.52,
                                    point + direction * length))
    macro = add_curve_bundle("Thoracic macrochaetae · orderly rows", macro_paths,
                             0.0024, bristle_mat, collection, root)
    macro["bristle_count"] = len(macro_paths)

    # Six distinctly articulated legs, placed as three bilateral pairs.
    leg_specs = [
        ("fore", "left", -1, (-0.50, -0.27, 0.67), (-0.69, -0.63, 0.42), (-1.00, -0.92, 0.105), (-1.17, -1.04, 0.035)),
        ("fore", "right", 1, (-0.50, 0.27, 0.67), (-0.69, 0.63, 0.42), (-1.00, 0.92, 0.105), (-1.17, 1.04, 0.035)),
        ("mid", "left", -1, (-0.15, -0.35, 0.62), (-0.04, -0.75, 0.40), (0.11, -1.00, 0.105), (0.02, -1.11, 0.035)),
        ("mid", "right", 1, (-0.15, 0.35, 0.62), (-0.04, 0.75, 0.40), (0.11, 1.00, 0.105), (0.02, 1.11, 0.035)),
        ("hind", "left", -1, (0.20, -0.29, 0.58), (0.54, -0.70, 0.38), (0.86, -0.98, 0.105), (1.08, -1.08, 0.035)),
        ("hind", "right", 1, (0.20, 0.29, 0.58), (0.54, 0.70, 0.38), (0.86, 0.98, 0.105), (1.08, 1.08, 0.035)),
    ]
    for spec in leg_specs:
        make_leg(*spec, collection, root, leg_mat, dark_leg_mat,
                 joint_mat, seta_light, comb_mat)

    # Halteres: tiny posterior balancing organs behind the wing hinges.
    haltere_mat = cuticle_material("Halteres · pale sensory clubs", (0.40, 0.22, 0.075), 0.38, 240, 0.08)
    for side, label in ((-1, "near"), (1, "far")):
        stalk = (0.36, side * 0.34, 0.91)
        club = (0.39, side * 0.57, 0.93)
        add_tapered_link(f"Haltere stalk · {label}", stalk, club,
                         0.014, 0.010, haltere_mat, collection, root)
        add_uv_sphere(f"Haltere knob · {label}", club,
                      (0.047, 0.040, 0.044), haltere_mat, collection, root, 28, 18)

    # Thin optical film mixed with transparency; all venation is separate and editable.
    wing_mat = bpy.data.materials.new("Wing membrane · optically thin")
    wing_mat.diffuse_color = (0.72, 0.61, 0.43, 0.42)
    wing_mat.use_nodes = True
    nodes, links = wing_mat.node_tree.nodes, wing_mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (0.72, 0.61, 0.43, 1.0)
    shader.inputs["Roughness"].default_value = 0.21
    shader.inputs["IOR"].default_value = 1.33
    shader.inputs["Transmission Weight"].default_value = 0.9
    if "Thin Wall" in shader.inputs:
        shader.inputs["Thin Wall"].default_value = True
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    # Nearly clear at normal viewing scale; pigment, reflected softboxes and
    # the independently modeled veins keep the thin wing readable.
    mix.inputs[0].default_value = 0.08
    output = nodes.get("Material Output")
    links.new(transparent.outputs["BSDF"], mix.inputs[1])
    links.new(shader.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])
    vein_mat = simple_material("Wing veins · amber chitin", (0.16, 0.064, 0.024), 0.36, coat=0.06)
    for side, label in ((-1, "near"), (1, "far")):
        make_wing(label, side, collection, root, wing_mat, vein_mat)

    # Wing-root bristles and fine setae along the scutellum margin.
    scutellar_paths = []
    for side in (-1, 1):
        for index in range(15):
            x = 0.16 + index * 0.018
            base = Vector((x, side * (0.22 + 0.008 * index), 1.00))
            scutellar_paths.append((base, base + Vector((0.012, side * 0.026, 0.027)),
                                    base + Vector((0.026, side * 0.050, 0.043))))
    add_curve_bundle("Scutellum · posterior bristle fringe", scutellar_paths,
                     0.0020, bristle_mat, collection, root)
    return root


def make_studio(scene):
    studio = new_collection("STUDIO | macro specimen photography")
    backdrop = simple_material("Backdrop · charcoal blue-grey", (0.042, 0.055, 0.064), 0.83)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0.0, 0.0, -0.004))
    floor = bpy.context.object
    floor.name = "Infinite matte studio floor"
    floor.data.materials.append(backdrop)
    move_to_collection(floor, studio)

    camera = make_camera(studio)
    add_area_light("Key softbox · warm overhead", (-3.5, -3.9, 5.4), (-0.15, 0.0, 0.72),
                   430.0, (1.0, 0.82, 0.66), 3.1, studio)
    add_area_light("Fill card · cool near-side", (-1.3, -4.5, 2.2), (-0.25, -0.1, 0.80),
                   180.0, (0.68, 0.79, 1.0), 3.0, studio)
    add_area_light("Rim strip · posterior", (2.2, 2.7, 3.7), (0.15, 0.0, 0.85),
                   510.0, (1.0, 0.68, 0.39), 2.2, studio)
    add_area_light("Eye catchlight · small card", (-3.7, -1.4, 2.0), (-1.0, -0.1, 0.95),
                   38.0, (1.0, 0.93, 0.81), 0.24, studio)

    world = bpy.data.worlds.new("Macro studio · subdued ambient")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.12, 0.15, 0.18, 1.0)
    background.inputs["Strength"].default_value = 0.22
    return camera


def configure_optix(scene):
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "OPTIX"
    preferences.get_devices()
    optix_devices = [device for device in preferences.devices if device.type == "OPTIX"]
    if not optix_devices:
        raise RuntimeError("This scene was approved for the installed NVIDIA OptiX path, but Blender found no OptiX device.")
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
    scene.cycles.device = "GPU"
    print("OptiX devices:", ", ".join(device.name for device in optix_devices))


def build_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)

    scene = bpy.context.scene
    scene.name = "Male Drosophila · procedural hero macro"
    fly_collection = new_collection("FLY | male Drosophila hero")
    create_fly(fly_collection)
    make_studio(scene)

    scene.render.engine = "CYCLES"
    scene.cycles.samples = 96
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 8
    scene.cycles.transparent_max_bounces = 8
    scene.cycles.use_adaptive_sampling = True
    scene.render.resolution_x = 2048
    scene.render.resolution_y = 1536
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.filepath = str(RENDER_PATH)
    scene.render.use_file_extension = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -0.15
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.render.threads_mode = "AUTO"
    scene.render.image_settings.compression = 88
    scene.render.use_persistent_data = True
    scene.render.film_transparent = False
    scene.camera.data.lens = 85.0
    scene.frame_set(1)
    configure_optix(scene)

    notes = bpy.data.texts.new("READ ME · procedural hero fly")
    notes.write(
        "Standalone procedural macro interpretation of an adult male Drosophila melanogaster.\n"
        "This is a hand-authored procedural model, not a specimen scan or photogrammetry asset.\n"
        "The abdomen is a single smooth shell with six region-shaded tergites; A5 and A6 are fully dark.\n"
        "Each eye has individually shaded hexagonal corneal facets; wings and vein networks are separate meshes/curves.\n"
        "Male D. melanogaster foreleg sex combs are represented with 11 modified bristles apiece.\n"
        "Anatomical references:\n"
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC11457947/ (wild-type anatomical atlas)\n"
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC3462374/ (sex comb location and morphology)\n"
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC5608185/ (adult abdominal tergites and pigmentation)\n"
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC8982031/ (five longitudinal wing veins and crossveins)\n"
        "Build script: artwork/blender/realistic_fly_hero/build_hero_fly.py\n"
        "Render: outputs/blender/realistic-fly-hero/male_drosophila_hero.png\n"
    )
    RENDER_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCENE_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    hero_camera = scene.camera
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    bpy.ops.render.render(write_still=True)

    # A second camera lets the rendered eye, cuticle, bristles, and wing-root detail
    # be inspected at useful scale; the saved scene returns to the full-body view.
    studio = bpy.data.collections["STUDIO | macro specimen photography"]
    detail_camera = make_camera(
        studio,
        name="Detail camera · compound eye and wing root",
        location=(-3.05, -4.85, 2.58),
        target=(-0.58, -0.12, 0.98),
        lens=105.0,
        focus_location=(-0.72, -0.18, 0.98),
        fstop=24.0,
    )
    scene.camera = detail_camera
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1350
    scene.render.filepath = str(DETAIL_RENDER_PATH)
    bpy.ops.render.render(write_still=True)

    scene.camera = hero_camera
    scene.render.resolution_x = 2048
    scene.render.resolution_y = 1536
    scene.render.filepath = str(RENDER_PATH)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print(f"Saved Blender scene: {SCENE_PATH}")
    print(f"Saved render preview: {RENDER_PATH}")
    print(f"Fly object count: {len(bpy.data.collections['FLY | male Drosophila hero'].objects)}")


if __name__ == "__main__":
    build_scene()
