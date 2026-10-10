"""Build a standalone, macro-photographic male Drosophila scene in Blender.

Run from the repository root with:
    .\tools\blender\blender-5.2.2-windows-x64\blender.exe -b --python artwork\blender\realistic_fly\build_realistic_fly.py

This deliberately writes a new scene and preview in their own folders. It does
not open or alter the existing Decision Chamber scene or its Godot export.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


RNG = random.Random(20260924)
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
SCENE_PATH = SCRIPT_DIR / "realistic_male_fruit_fly.blend"
RENDER_PATH = REPO_ROOT / "outputs" / "blender" / "realistic-fly" / "realistic_male_fruit_fly.png"


def new_collection(name: str):
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def place_object(obj, collection, parent=None):
    for previous_collection in list(obj.users_collection):
        previous_collection.objects.unlink(obj)
    collection.objects.link(obj)
    if parent is not None:
        # Model and leg assembly empties stay at identity. Preserve each
        # object's local location/rotation/scale directly when grouping it.
        obj.parent = parent
    return obj


def make_empty(name, collection, parent=None):
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def material(name, color, roughness=0.4, metallic=0.0, coat=0.0, coat_roughness=0.25,
             transmission=0.0, alpha=1.0, ior=1.46, subsurface=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, alpha)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["IOR"].default_value = ior
    shader.inputs["Coat Weight"].default_value = coat
    shader.inputs["Coat Roughness"].default_value = coat_roughness
    shader.inputs["Transmission Weight"].default_value = transmission
    shader.inputs["Alpha"].default_value = alpha
    shader.inputs["Subsurface Weight"].default_value = subsurface
    if "Thin Wall" in shader.inputs:
        shader.inputs["Thin Wall"].default_value = transmission > 0.0
    return mat


def add_surface_grain(mat, scale=95.0, detail=3.0, strength=0.12, distance=0.018):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    noise.inputs["Roughness"].default_value = 0.72
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    base_roughness = shader.inputs["Roughness"].default_value
    roughness = nodes.new("ShaderNodeMapRange")
    roughness.inputs["To Min"].default_value = max(0.08, base_roughness - 0.10)
    roughness.inputs["To Max"].default_value = min(0.95, base_roughness + 0.13)
    links.new(noise.outputs["Fac"], roughness.inputs["Value"])
    links.new(roughness.outputs["Result"], shader.inputs["Roughness"])


def abdomen_segment_material(name, front_color, band_color, dark_all=False):
    mat = material(name, front_color, roughness=0.34, coat=0.2, coat_roughness=0.28)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    if dark_all:
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (0.025, 0.009, 0.006, 1.0)
        ramp.color_ramp.elements[1].color = (0.085, 0.025, 0.014, 1.0)
    else:
        coordinates = nodes.new("ShaderNodeTexCoord")
        separate = nodes.new("ShaderNodeSeparateXYZ")
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.0
        ramp.color_ramp.elements[0].color = (*front_color, 1.0)
        ramp.color_ramp.elements[1].position = 0.99
        ramp.color_ramp.elements[1].color = (*band_color, 1.0)
        mid = ramp.color_ramp.elements.new(0.66)
        mid.color = (*front_color, 1.0)
        edge = ramp.color_ramp.elements.new(0.76)
        edge.color = (*band_color, 1.0)
        links.new(coordinates.outputs["Generated"], separate.inputs["Vector"])
        links.new(separate.outputs["X"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    add_surface_grain(mat, scale=110.0, detail=2.0, strength=0.1, distance=0.012)
    return mat


def add_sphere(name, location, scale, mat, collection, parent=None, segments=40, rings=28):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, radius=1.0, location=location
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    if mat is not None:
        obj.data.materials.append(mat)
    return place_object(obj, collection, parent)


def add_link(name, start, end, radius_start, radius_end, mat, collection, parent=None, sides=16):
    start, end = Vector(start), Vector(end)
    delta = end - start
    bpy.ops.mesh.primitive_cone_add(
        vertices=sides,
        radius1=radius_start,
        radius2=radius_end,
        depth=max(delta.length, 0.0001),
        location=(start + end) * 0.5,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = delta.to_track_quat("Z", "Y")
    for polygon in obj.data.polygons:
        polygon.use_smooth = len(polygon.vertices) == 4
    obj.data.materials.append(mat)
    return place_object(obj, collection, parent)


def add_curve_bundle(name, paths, radius, mat, collection, parent=None, resolution=1):
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = radius
    curve.bevel_resolution = 2 if radius >= 0.003 else 1
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


def ellipsoid_surface_point(center, scale, latitude, longitude):
    cx, cy, cz = center
    rx, ry, rz = scale
    c = math.cos(latitude)
    return Vector((
        cx + rx * c * math.cos(longitude),
        cy + ry * c * math.sin(longitude),
        cz + rz * math.sin(latitude),
    ))


def add_ellipsoid_hairs(name, center, scale, count, max_length, radius, mat, collection,
                        parent=None, dorsal=True):
    cx, cy, cz = center
    rx, ry, rz = scale
    paths = []
    for _ in range(count):
        longitude = RNG.uniform(0.0, math.tau)
        latitude = math.asin(RNG.uniform(0.04, 0.98)) if dorsal else RNG.uniform(-1.25, 1.25)
        start = ellipsoid_surface_point(center, scale, latitude, longitude)
        normal = Vector((
            (start.x - cx) / (rx * rx),
            (start.y - cy) / (ry * ry),
            (start.z - cz) / (rz * rz),
        )).normalized()
        length = max_length * RNG.uniform(0.48, 1.18)
        lean = Vector((RNG.uniform(-0.7, 0.7), RNG.uniform(-0.7, 0.7), 0.24))
        direction = (normal * 0.78 + lean.normalized() * 0.22).normalized()
        middle = start + direction * (length * 0.53)
        middle += Vector((0.0, 0.0, length * 0.08))
        paths.append((start, middle, start + direction * length))
    return add_curve_bundle(name, paths, radius, mat, collection, parent)


def make_eye_facets(name, center, scale, collection, parent, palette):
    rx, ry, rz = scale
    vertices = []
    faces = []
    material_indices = []
    latitude = -1.37
    while latitude <= 1.37:
        circumference = max(12, round((math.tau * max(rx, ry) * math.cos(latitude)) / 0.038))
        phase = (round((latitude + 1.37) / 0.085) % 2) * math.pi / circumference
        for index in range(circumference):
            longitude = (math.tau * index / circumference) + phase
            point = ellipsoid_surface_point(center, scale, latitude, longitude)
            normal = Vector((
                (point.x - center[0]) / (rx * rx),
                (point.y - center[1]) / (ry * ry),
                (point.z - center[2]) / (rz * rz),
            )).normalized()
            tangent_a = Vector((0.0, 0.0, 1.0)).cross(normal)
            if tangent_a.length_squared < 1e-8:
                tangent_a = Vector((1.0, 0.0, 0.0)).cross(normal)
            tangent_a.normalize()
            tangent_b = normal.cross(tangent_a).normalized()
            patch_radius = 0.015
            first = len(vertices)
            vertices.append(tuple(point + normal * 0.0045))
            for corner in range(6):
                angle = math.tau * corner / 6.0
                rim = point + tangent_a * (math.cos(angle) * patch_radius)
                rim += tangent_b * (math.sin(angle) * patch_radius)
                rim += normal * 0.002
                vertices.append(tuple(rim))
            palette_index = RNG.randrange(len(palette))
            for corner in range(6):
                faces.append((first, first + 1 + corner, first + 1 + ((corner + 1) % 6)))
                material_indices.append(palette_index)
        latitude += 0.085

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for mat in palette:
        mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    for polygon, material_index in zip(mesh.polygons, material_indices):
        polygon.material_index = material_index
    obj.parent = parent
    return obj


def wing_point(t, across, side):
    center = Vector((-0.08 + 1.38 * t, side * (0.28 + 0.47 * t), 1.07 + 0.11 * math.sin(math.pi * t) - 0.035 * t))
    tangent = Vector((1.38, side * 0.47, 0.0)).normalized()
    width_direction = Vector((-tangent.y, tangent.x, 0.0)).normalized()
    width = 0.018 + 0.34 * (math.sin(math.pi * t) ** 0.72) * (0.88 + 0.12 * t)
    point = center + width_direction * (across * width)
    point.z += 0.035 * (1.0 - across * across) * math.sin(math.pi * t)
    return point


def make_wing(side_label, side, collection, parent, membrane_mat, vein_mat):
    longitudinal_steps = 36
    cross_steps = 12
    vertices = []
    faces = []
    for i in range(longitudinal_steps + 1):
        t = i / longitudinal_steps
        for j in range(cross_steps + 1):
            across = -1.0 + 2.0 * j / cross_steps
            vertices.append(tuple(wing_point(t, across, side)))
    for i in range(longitudinal_steps):
        for j in range(cross_steps):
            a = i * (cross_steps + 1) + j
            b = a + cross_steps + 1
            faces.append((a, b, b + 1, a + 1))
    mesh = bpy.data.meshes.new(f"Wing membrane mesh · {side_label}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    wing = bpy.data.objects.new(f"Wing membrane · {side_label}", mesh)
    collection.objects.link(wing)
    mesh.materials.append(membrane_mat)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    wing.parent = parent

    vein_paths = []
    for index, across_start in enumerate((-0.74, -0.42, -0.05, 0.31, 0.67)):
        path = []
        for step in range(22):
            t = 0.035 + 0.92 * step / 21.0
            across = across_start + 0.05 * math.sin(math.pi * t + index * 0.55)
            path.append(wing_point(t, across, side))
        vein_paths.append(path)
    # A reinforced costa follows the leading edge; two cross-veins close the cells.
    vein_paths.append([wing_point(0.02 + 0.93 * step / 23.0, 0.87, side) for step in range(24)])
    for t in (0.43, 0.67):
        vein_paths.append([
            wing_point(t + 0.04 * math.sin(math.pi * j / 18.0), -0.66 + 1.50 * j / 18.0, side)
            for j in range(19)
        ])
    veins = add_curve_bundle(f"Wing venation · {side_label}", vein_paths, 0.0042, vein_mat, collection, parent)
    return wing, veins


def create_leg(pair, side_label, side_sign, start, knee, ankle, foot, collection, fly_root,
               leg_mat, joint_mat, tarsus_mat, seta_mat, comb_mat):
    root = make_empty(f"Leg assembly · {pair} {side_label}", collection, fly_root)
    start, knee, ankle, foot = map(Vector, (start, knee, ankle, foot))
    coxa_end = start.lerp(knee, 0.22)
    add_link(f"{pair} {side_label} coxa", start, coxa_end, 0.075, 0.057, leg_mat, collection, root)
    add_sphere(f"{pair} {side_label} coxal joint", coxa_end, (0.062, 0.056, 0.058), joint_mat, collection, root, 20, 14)
    femur_start = coxa_end
    add_link(f"{pair} {side_label} femur", femur_start, knee, 0.075, 0.047, leg_mat, collection, root)
    add_sphere(f"{pair} {side_label} knee", knee, (0.055, 0.05, 0.052), joint_mat, collection, root, 20, 14)
    add_link(f"{pair} {side_label} tibia", knee, ankle, 0.043, 0.024, leg_mat, collection, root)
    add_sphere(f"{pair} {side_label} ankle", ankle, (0.034, 0.031, 0.03), joint_mat, collection, root, 16, 12)

    tarsus_points = [ankle]
    for fraction in (0.36, 0.68, 0.88):
        tarsus_points.append(ankle.lerp(foot, fraction))
    tarsus_points.append(foot)
    for index, (a, b) in enumerate(zip(tarsus_points[:-1], tarsus_points[1:]), start=1):
        r0 = 0.021 - 0.0025 * (index - 1)
        r1 = 0.019 - 0.0025 * (index - 1)
        add_link(f"{pair} {side_label} tarsomere {index}", a, b, r0, r1, tarsus_mat, collection, root, sides=12)
        if index < len(tarsus_points) - 1:
            add_sphere(f"{pair} {side_label} tarsal joint {index}", b, (0.022, 0.021, 0.02), joint_mat, collection, root, 16, 12)

    claw_paths = []
    for offset in (-1.0, 1.0):
        claw_paths.append((
            foot,
            foot + Vector((0.025, side_sign * 0.012 * offset, -0.005)),
            foot + Vector((0.045, side_sign * 0.018 * offset, 0.003)),
        ))
    add_curve_bundle(f"{pair} {side_label} pretarsal claws", claw_paths, 0.003, tarsus_mat, collection, root)

    tibia_vector = (ankle - knee).normalized()
    axis = tibia_vector.cross(Vector((0.0, 1.0, 0.0)))
    if axis.length_squared < 1e-6:
        axis = tibia_vector.cross(Vector((1.0, 0.0, 0.0)))
    axis.normalize()
    tibial_paths = []
    for index in range(9):
        t = 0.15 + 0.075 * index
        point = knee.lerp(ankle, t)
        direction = axis * side_sign + Vector((0.0, 0.0, 0.2))
        direction.normalize()
        length = 0.045 * (1.0 - 0.25 * abs(t - 0.5))
        tibial_paths.append((point, point + direction * length * 0.52, point + direction * length))
    add_curve_bundle(f"{pair} {side_label} tibial bristles", tibial_paths, 0.0025, seta_mat, collection, root)

    if pair == "fore":
        comb_paths = []
        first_tarsomere_start, first_tarsomere_end = tarsus_points[0], tarsus_points[1]
        direction = (first_tarsomere_end - first_tarsomere_start).normalized()
        comb_direction = Vector((-direction.z, 0.0, direction.x)).normalized()
        for index in range(10):
            t = 0.18 + 0.065 * index
            base = first_tarsomere_start.lerp(first_tarsomere_end, t)
            comb_paths.append((base, base + comb_direction * 0.025, base + comb_direction * 0.039))
        add_curve_bundle(f"Male sex comb · {side_label} foreleg", comb_paths, 0.004, comb_mat, collection, root)
    return root


def make_cyclorama(collection, mat):
    profile = []
    for step in range(10):
        profile.append((-30.0 + 33.0 * step / 9.0, 0.0))
    radius = 2.2
    for step in range(1, 21):
        angle = -math.pi / 2.0 + (math.pi / 2.0) * step / 20.0
        profile.append((3.0 + radius * math.cos(angle), radius + radius * math.sin(angle)))
    for step in range(1, 10):
        profile.append((5.2, radius + 18.0 * step / 9.0))
    vertices = []
    for y, z in profile:
        vertices.extend(((-35.0, y, z), (35.0, y, z)))
    faces = []
    for index in range(len(profile) - 1):
        first = index * 2
        faces.append((first, first + 1, first + 3, first + 2))
    mesh = bpy.data.meshes.new("Seamless sweep mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Matte seamless macro sweep", mesh)
    collection.objects.link(obj)
    mesh.materials.append(mat)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return obj


def area_light(name, location, target, energy, color, size, collection):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def make_camera(collection):
    data = bpy.data.cameras.new("Macro portrait camera")
    camera = bpy.data.objects.new("Macro portrait camera", data)
    collection.objects.link(camera)
    camera.location = (-3.6, -6.4, 2.55)
    target = Vector((0.02, 0.0, 0.70))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    data.lens = 69.0
    data.dof.use_dof = True
    focus = bpy.data.objects.new("Focus target · compound eye", None)
    collection.objects.link(focus)
    focus.location = (-0.94, -0.13, 0.86)
    data.dof.focus_object = focus
    data.dof.aperture_fstop = 10.0
    data.dof.aperture_blades = 9
    bpy.context.scene.camera = camera
    return camera


def create_fly(fly_collection):
    fly_root = make_empty("Fly model root", fly_collection)

    cuticle = material("Cuticle · amber thorax", (0.24, 0.083, 0.022), roughness=0.5,
                       coat=0.1, coat_roughness=0.34, subsurface=0.025)
    add_surface_grain(cuticle, scale=155.0, detail=3.0, strength=0.15, distance=0.012)
    thorax_side = material("Cuticle · darker pleural plates", (0.105, 0.034, 0.014), roughness=0.52, coat=0.06)
    add_surface_grain(thorax_side, scale=145.0, strength=0.12, distance=0.01)
    scutellum_mat = material("Cuticle · scutellum", (0.17, 0.052, 0.018), roughness=0.51, coat=0.08)
    add_surface_grain(scutellum_mat, scale=150.0, strength=0.14, distance=0.011)
    head_mat = material("Cuticle · head capsule", (0.18, 0.055, 0.016), roughness=0.48, coat=0.1)
    add_surface_grain(head_mat, scale=155.0, strength=0.12, distance=0.011)
    leg_mat = material("Cuticle · leg segments", (0.18, 0.055, 0.013), roughness=0.47, coat=0.09)
    add_surface_grain(leg_mat, scale=140.0, strength=0.14, distance=0.01)
    joint_mat = material("Cuticle · leg joints", (0.12, 0.037, 0.012), roughness=0.5, coat=0.07)
    tarsus_mat = material("Cuticle · distal tarsi", (0.085, 0.026, 0.012), roughness=0.34, coat=0.18)
    setae_mat = material("Setae · warm umber", (0.052, 0.018, 0.009), roughness=0.56)
    comb_mat = material("Sex comb · dark setae", (0.018, 0.007, 0.005), roughness=0.38)
    bristle_mat = material("Macro bristles · chestnut", (0.09, 0.028, 0.012), roughness=0.48)
    palps_mat = material("Mouthparts · tawny", (0.22, 0.09, 0.027), roughness=0.45)
    proboscis_mat = material("Proboscis · brown cuticle", (0.12, 0.036, 0.011), roughness=0.4, coat=0.12)

    eye_shell = material("Compound eyes · carmine base", (0.105, 0.003, 0.012), roughness=0.27,
                          coat=0.28, coat_roughness=0.2, ior=1.48)
    add_surface_grain(eye_shell, scale=190.0, detail=2.0, strength=0.18, distance=0.009)
    eye_palette = [
        material("Ommatidium · oxblood", (0.20, 0.003, 0.012), roughness=0.27, coat=0.20),
        material("Ommatidium · ruby", (0.31, 0.006, 0.021), roughness=0.25, coat=0.22),
        material("Ommatidium · garnet", (0.14, 0.002, 0.010), roughness=0.29, coat=0.17),
        material("Ommatidium · glint red", (0.39, 0.012, 0.031), roughness=0.23, coat=0.25),
    ]

    thorax_center = (-0.25, 0.0, 0.86)
    thorax_scale = (0.58, 0.43, 0.39)
    add_sphere("Thorax shell", thorax_center, thorax_scale, cuticle, fly_collection, fly_root, 64, 40)
    add_sphere("Near pleural plate", (-0.13, -0.34, 0.73), (0.40, 0.15, 0.26), thorax_side, fly_collection, fly_root)
    add_sphere("Far pleural plate", (-0.13, 0.34, 0.73), (0.40, 0.15, 0.26), thorax_side, fly_collection, fly_root)
    add_sphere("Scutellum", (0.235, 0.0, 0.88), (0.20, 0.37, 0.18), scutellum_mat, fly_collection, fly_root)
    add_sphere("Head capsule", (-1.02, 0.0, 0.84), (0.36, 0.34, 0.34), head_mat, fly_collection, fly_root, 56, 36)
    add_sphere("Cervical membrane", (-0.70, 0.0, 0.83), (0.20, 0.245, 0.245), thorax_side, fly_collection, fly_root)

    eye_centers = {
        "near": (-1.115, -0.236, 0.89),
        "far": (-1.115, 0.236, 0.89),
    }
    eye_scale = (0.255, 0.204, 0.278)
    for side_label, center in eye_centers.items():
        add_sphere(f"Compound eye shell · {side_label}", center, eye_scale, eye_shell, fly_collection, fly_root, 48, 32)
        make_eye_facets(f"Compound-eye facets · {side_label}", center, eye_scale, fly_collection, fly_root, eye_palette)

    # D. melanogaster males typically have fully melanized A5-A6 tergites and a rounded terminal abdomen.
    # Morphology references: https://pmc.ncbi.nlm.nih.gov/articles/PMC5608185/
    # and https://academic.oup.com/genetics/article/228/2/iyae129/7750380
    abdomen_specs = [
        ("A1", 0.205, (0.275, 0.325, 0.245), (0.25, 0.095, 0.026), (0.14, 0.045, 0.016), False),
        ("A2", 0.445, (0.282, 0.333, 0.255), (0.34, 0.14, 0.037), (0.16, 0.050, 0.018), False),
        ("A3", 0.675, (0.274, 0.322, 0.248), (0.31, 0.12, 0.031), (0.115, 0.032, 0.012), False),
        ("A4", 0.895, (0.252, 0.294, 0.222), (0.24, 0.080, 0.022), (0.085, 0.022, 0.009), False),
        ("A5", 1.095, (0.205, 0.245, 0.184), (0.035, 0.011, 0.008), (0.035, 0.011, 0.008), True),
        ("A6", 1.245, (0.145, 0.175, 0.143), (0.028, 0.009, 0.007), (0.028, 0.009, 0.007), True),
    ]
    abdomen_mats = {}
    terminal_cuticle = abdomen_segment_material(
        "Male terminal cuticle", (0.035, 0.011, 0.008), (0.035, 0.011, 0.008), dark_all=True
    )
    for name, _, _, front, band, dark in abdomen_specs:
        abdomen_mats[name] = terminal_cuticle if dark else abdomen_segment_material(
            f"Abdominal cuticle · {name}", front, band, dark_all=False
        )
    for name, x, scale, _, _, _ in abdomen_specs:
        z = 0.755 - max(0.0, x - 0.75) * 0.11
        add_sphere(f"Abdominal tergite {name}", (x, 0.0, z), scale, abdomen_mats[name], fly_collection, fly_root, 48, 32)
    add_sphere("Ventral abdomen", (0.72, 0.0, 0.60), (0.70, 0.265, 0.17), thorax_side, fly_collection, fly_root)

    # Paired dark spiracles sit on the lateral abdominal cuticle.
    spiracle_mat = material("Spiracles · dark openings", (0.012, 0.006, 0.004), roughness=0.62)
    for segment_index, x in enumerate((0.43, 0.64, 0.84, 1.02), start=1):
        z = 0.735 - max(0.0, x - 0.75) * 0.11
        for side_sign, side_label in ((-1, "near"), (1, "far")):
            add_sphere(f"Spiracle {segment_index} · {side_label}", (x, side_sign * 0.285, z - 0.015),
                       (0.035, 0.011, 0.017), spiracle_mat, fly_collection, fly_root, 16, 10)

    # Mouthparts: compact, tucked beneath the head rather than a long cartoon proboscis.
    add_link("Proboscis rostrum", (-1.19, 0.0, 0.65), (-1.235, 0.0, 0.49), 0.055, 0.036,
             proboscis_mat, fly_collection, fly_root, sides=20)
    add_sphere("Proboscis labellum", (-1.24, 0.0, 0.46), (0.09, 0.075, 0.045), palps_mat, fly_collection, fly_root)
    for side_sign, label in ((-1, "near"), (1, "far")):
        add_sphere(f"Maxillary palp · {label}", (-1.20, side_sign * 0.105, 0.56),
                   (0.065, 0.04, 0.075), palps_mat, fly_collection, fly_root, 24, 16)

    # Antennal aristae are fine, feathered structures; all branches remain editable curves.
    antenna_paths = []
    for side_sign in (-1, 1):
        base = Vector((-1.285, side_sign * 0.105, 1.105))
        pedicel = base + Vector((-0.035, side_sign * 0.018, 0.055))
        flagellum = pedicel + Vector((-0.055, side_sign * 0.015, 0.02))
        arista_end = flagellum + Vector((-0.105, side_sign * 0.01, 0.21))
        antenna_paths.extend(((base, pedicel, flagellum), (flagellum, flagellum + Vector((-0.02, 0.0, 0.035)), arista_end)))
        arista_axis = (arista_end - flagellum).normalized()
        perpendicular = arista_axis.cross(Vector((0.0, 1.0, 0.0))).normalized()
        for index in range(8):
            t = 0.14 + index * 0.095
            point = flagellum.lerp(arista_end, t)
            branch_length = 0.045 * math.sin(math.pi * t) ** 0.5
            for direction in (-1.0, 1.0):
                antenna_paths.append((point, point + perpendicular * branch_length * direction * 0.65 + Vector((0, 0, 0.009)),
                                      point + perpendicular * branch_length * direction))
    add_curve_bundle("Antennae and plumose aristae", antenna_paths, 0.0028, setae_mat, fly_collection, fly_root)

    # Dense fine cuticular setae plus longer thoracic/scutellar macrochaetae.
    add_ellipsoid_hairs("Thoracic microtrichia", thorax_center, thorax_scale, 690, 0.052, 0.00145,
                        bristle_mat, fly_collection, fly_root)
    add_ellipsoid_hairs("Head capsule microtrichia", (-1.02, 0.0, 0.84), (0.36, 0.34, 0.34),
                        155, 0.035, 0.0012, bristle_mat, fly_collection, fly_root)
    abdomen_hair_paths = []
    for name, x, scale, _, _, _ in abdomen_specs:
        z = 0.755 - max(0.0, x - 0.75) * 0.11
        segment_count = 78 if name not in ("A5", "A6") else 40
        center = (x, 0.0, z)
        _, rx, _ = scale
        # Short hairs on the dorsal tergite; terminal male segments carry darker, stronger setae.
        material_for_segment = setae_mat if name not in ("A5", "A6") else comb_mat
        for _ in range(segment_count):
            longitude = RNG.uniform(0.0, math.tau)
            latitude = math.asin(RNG.uniform(0.18, 0.98))
            point = ellipsoid_surface_point(center, scale, latitude, longitude)
            normal = Vector((point.x - x, point.y / (scale[1] ** 2), (point.z - z) / (scale[2] ** 2))).normalized()
            length = RNG.uniform(0.022, 0.052)
            abdomen_hair_paths.append((point, point + normal * length * 0.52, point + normal * length))
    add_curve_bundle("Abdominal tergite setae", abdomen_hair_paths, 0.00125, setae_mat, fly_collection, fly_root)

    macro_paths = []
    for index in range(64):
        longitude = RNG.uniform(0.0, math.tau)
        latitude = RNG.uniform(0.62, 1.35)
        point = ellipsoid_surface_point(thorax_center, thorax_scale, latitude, longitude)
        normal = Vector(((point.x - thorax_center[0]) / thorax_scale[0] ** 2,
                         point.y / thorax_scale[1] ** 2,
                         (point.z - thorax_center[2]) / thorax_scale[2] ** 2)).normalized()
        length = RNG.uniform(0.085, 0.16)
        lean = Vector((-0.25, RNG.uniform(-0.2, 0.2), 0.28))
        direction = (normal * 0.65 + lean.normalized() * 0.35).normalized()
        macro_paths.append((point, point + direction * length * 0.52, point + direction * length))
    add_curve_bundle("Thoracic macrochaetae", macro_paths, 0.0034, bristle_mat, fly_collection, fly_root)

    # Six separate leg assemblies; the male foreleg sex-combs are modeled on both first tarsomeres.
    leg_specs = [
        ("fore", "left", -1, (-0.48, -0.27, 0.62), (-0.68, -0.68, 0.42), (-1.02, -0.91, 0.105), (-1.20, -1.00, 0.042)),
        ("fore", "right", 1, (-0.48, 0.27, 0.62), (-0.68, 0.68, 0.42), (-1.02, 0.91, 0.105), (-1.20, 1.00, 0.042)),
        ("mid", "left", -1, (-0.15, -0.34, 0.61), (-0.08, -0.76, 0.43), (0.10, -1.00, 0.105), (0.02, -1.10, 0.042)),
        ("mid", "right", 1, (-0.15, 0.34, 0.61), (-0.08, 0.76, 0.43), (0.10, 1.00, 0.105), (0.02, 1.10, 0.042)),
        ("hind", "left", -1, (0.10, -0.30, 0.58), (0.53, -0.75, 0.42), (0.84, -1.00, 0.105), (1.04, -1.09, 0.042)),
        ("hind", "right", 1, (0.10, 0.30, 0.58), (0.53, 0.75, 0.42), (0.84, 1.00, 0.105), (1.04, 1.09, 0.042)),
    ]
    for spec in leg_specs:
        create_leg(*spec, fly_collection, fly_root, leg_mat, joint_mat, tarsus_mat, setae_mat, comb_mat)

    # The small balancing organs (halteres) project behind the wing bases.
    haltere_mat = material("Halteres · pale sensory club", (0.48, 0.25, 0.07), roughness=0.32, coat=0.22)
    for side_sign, label in ((-1, "near"), (1, "far")):
        stalk_start = (0.12, side_sign * 0.34, 0.88)
        club_center = (0.16, side_sign * 0.57, 0.91)
        add_link(f"Haltere stalk · {label}", stalk_start, club_center, 0.018, 0.012, haltere_mat, fly_collection, fly_root)
        add_sphere(f"Haltere knob · {label}", club_center, (0.055, 0.047, 0.052), haltere_mat, fly_collection, fly_root, 24, 16)

    wing_mat = material("Wing membrane · translucent chitin", (0.64, 0.55, 0.41), roughness=0.33,
                        coat=0.1, coat_roughness=0.25, transmission=0.72, alpha=0.36, ior=1.33)
    add_surface_grain(wing_mat, scale=160.0, detail=2.0, strength=0.06, distance=0.004)
    vein_mat = material("Wing veins · amber chitin", (0.17, 0.065, 0.026), roughness=0.34, coat=0.24)
    for side_sign, label in ((-1, "near"), (1, "far")):
        make_wing(label, side_sign, fly_collection, fly_root, wing_mat, vein_mat)

    # Fine sensory bristles around wing roots and along the rear edge of the scutellum.
    thoracic_detail_paths = []
    for side_sign in (-1, 1):
        for index in range(7):
            x = 0.16 + index * 0.025
            base = Vector((x, side_sign * (0.22 + 0.012 * index), 0.98))
            thoracic_detail_paths.append((base, base + Vector((0.012, side_sign * 0.045, 0.028)),
                                          base + Vector((0.025, side_sign * 0.075, 0.045))))
    add_curve_bundle("Scutellar bristles", thoracic_detail_paths, 0.003, bristle_mat, fly_collection, fly_root)

    return fly_root


def build_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)

    scene = bpy.context.scene
    scene.name = "Male Drosophila · macro specimen"
    fly_collection = new_collection("FLY | D. melanogaster · male")
    studio_collection = new_collection("STUDIO | macro photograph")

    floor_mat = material("Studio sweep · graphite", (0.072, 0.079, 0.084), roughness=0.82)
    add_surface_grain(floor_mat, scale=38.0, detail=2.0, strength=0.08, distance=0.012)
    make_cyclorama(studio_collection, floor_mat)

    fly_root = create_fly(fly_collection)
    camera = make_camera(studio_collection)

    area_light("Key · large softbox", (-3.6, -4.2, 5.0), (-0.25, 0.0, 0.65), 430.0, (1.0, 0.82, 0.66), 3.4, studio_collection)
    area_light("Fill · cool card", (0.8, -2.0, 3.0), (-0.25, 0.0, 0.75), 205.0, (0.68, 0.79, 1.0), 2.8, studio_collection)
    area_light("Rim · amber strip", (1.6, 3.0, 4.0), (0.1, 0.0, 0.8), 480.0, (1.0, 0.68, 0.39), 2.5, studio_collection)
    area_light("Eye catchlight", (-3.0, -1.0, 2.2), (-1.0, -0.1, 0.85), 85.0, (1.0, 0.93, 0.82), 0.75, studio_collection)

    world = bpy.data.worlds.new("Macro studio · low ambient") if bpy.data.worlds.get("Macro studio · low ambient") is None else bpy.data.worlds["Macro studio · low ambient"]
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.11, 0.13, 0.15, 1.0)
    background.inputs["Strength"].default_value = 0.22

    scene.render.engine = "CYCLES"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 7
    scene.cycles.transparent_max_bounces = 8
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.filepath = str(RENDER_PATH)
    scene.render.use_file_extension = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -0.35
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.render.threads_mode = "AUTO"
    scene.camera.data.lens = 69.0
    scene.camera.data.dof.aperture_fstop = 10.0
    scene.frame_set(1)

    # Save an inspectable scene note into the .blend itself.
    notes = bpy.data.texts.new("READ ME · realistic fly scene")
    notes.write(
        "Standalone procedural macro scene: adult male Drosophila melanogaster.\n"
        "Anatomy is modeled for a recognizable, realistic close-up, not as a calibrated specimen scan.\n"
        "Editable parts are grouped in the FLY collection; the camera, lights, and sweep are in STUDIO.\n"
        "Build script: artwork/blender/realistic_fly/build_realistic_fly.py\n"
        "Preview: outputs/blender/realistic-fly/realistic_male_fruit_fly.png\n"
        "Male abdominal pigmentation reference: https://pmc.ncbi.nlm.nih.gov/articles/PMC5608185/\n"
        "Wild-type anatomical atlas: https://academic.oup.com/genetics/article/228/2/iyae129/7750380\n"
    )
    RENDER_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCENE_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print(f"Saved Blender scene: {SCENE_PATH}")
    print(f"Saved render preview: {RENDER_PATH}")
    print(f"Fly object count: {len(fly_collection.objects)}")


if __name__ == "__main__":
    build_scene()
