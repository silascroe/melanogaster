"""Build a fresh, inspectable macro portrait of a male Drosophila.

Run with the project-local portable Blender, not the existing fly .blend.
All geometry, materials, lighting, and camera are generated here.
"""

import math
import os
import random
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parents[2] / "outputs" / "blender" / "realistic-fly-from-scratch"
OUTPUT.mkdir(parents=True, exist_ok=True)
random.seed(73215)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for block in bpy.data.materials:
    bpy.data.materials.remove(block)


def material(name, color, roughness=0.5, metallic=0.0, subsurface=0.0, texture=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Subsurface Weight"].default_value = subsurface
    if texture:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 80
        noise.inputs["Detail"].default_value = 3.0
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = texture
        bump.inputs["Distance"].default_value = 0.014
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def mottle(mat, low, high, scale):
    """Low-contrast cuticle pigmentation layered over microscopic bump."""
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 4.5
    noise.inputs["Roughness"].default_value = 0.7
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (*low, 1)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (*high, 1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])


amber = material("thorax | amber cuticle", (0.27, 0.125, 0.043), 0.53, texture=0.38)
ochre = material("thorax | ochre highlight", (0.36, 0.20, 0.075), 0.56, texture=0.35)
head_mat = material("head | warm honey", (0.41, 0.235, 0.085), 0.58, subsurface=0.025, texture=0.23)
abdomen = material("abdomen | chestnut", (0.29, 0.13, 0.073), 0.47, texture=0.2)
abdomen_dark = material("abdomen | male dark bands", (0.075, 0.043, 0.033), 0.5, texture=0.23)
abdomen_gold = material("abdomen | tergite gold", (0.46, 0.235, 0.095), 0.49, texture=0.23)
joint_mat = material("joints | dark umber", (0.11, 0.065, 0.042), 0.48)
leg_mat = material("legs | warm brown", (0.28, 0.155, 0.084), 0.46, texture=0.2)
tarsus_mat = material("tarsi | dark brown", (0.13, 0.083, 0.055), 0.54)
eye_base = material("eye | deep garnet base", (0.31, 0.026, 0.012), 0.31, metallic=0.025)
eye_facet_mats = [
    material("eye facet | %02d" % i, (0.30 + i * 0.011, 0.025 + i * 0.003, 0.010), 0.27 + i * 0.008, metallic=0.02)
    for i in range(8)
]
vein_mat = material("wing | brown veins", (0.25, 0.18, 0.11), 0.46)
wing_edge_mat = material("wing | warm leading edge", (0.32, 0.24, 0.16), 0.5)
bristle_mat = material("bristles | sepia", (0.13, 0.082, 0.052), 0.64)
bristle_light = material("bristles | gold", (0.48, 0.29, 0.13), 0.67)
ocellus_mat = material("ocelli | black glass", (0.035, 0.026, 0.020), 0.13)
mottle(amber, (0.19, 0.077, 0.023), (0.34, 0.17, 0.056), 19)
mottle(ochre, (0.26, 0.12, 0.034), (0.45, 0.26, 0.087), 23)
mottle(head_mat, (0.33, 0.16, 0.045), (0.48, 0.28, 0.10), 25)
mottle(abdomen, (0.21, 0.085, 0.040), (0.34, 0.16, 0.070), 17)
mottle(abdomen_gold, (0.33, 0.14, 0.045), (0.50, 0.27, 0.095), 21)

wing_mat = bpy.data.materials.new("wing | translucent membrane")
wing_mat.use_nodes = True
nodes = wing_mat.node_tree.nodes
nodes.clear()
output = nodes.new("ShaderNodeOutputMaterial")
transparent = nodes.new("ShaderNodeBsdfTransparent")
transparent.inputs["Color"].default_value = (0.90, 0.94, 0.92, 1)
principled = nodes.new("ShaderNodeBsdfPrincipled")
principled.inputs["Roughness"].default_value = 0.38
principled.inputs["Metallic"].default_value = 0.09
if "Coat Weight" in principled.inputs:
    principled.inputs["Coat Weight"].default_value = 0.2
layer_weight = nodes.new("ShaderNodeLayerWeight")
wing_tint = nodes.new("ShaderNodeValToRGB")
wing_tint.color_ramp.elements[0].color = (0.64, 0.73, 0.76, 1)
wing_tint.color_ramp.elements[1].color = (0.84, 0.79, 0.66, 1)
wing_mat.node_tree.links.new(layer_weight.outputs["Facing"], wing_tint.inputs["Fac"])
wing_mat.node_tree.links.new(wing_tint.outputs["Color"], principled.inputs["Base Color"])
mix = nodes.new("ShaderNodeMixShader")
mix.inputs[0].default_value = 0.14
wing_mat.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
wing_mat.node_tree.links.new(principled.outputs[0], mix.inputs[2])
wing_mat.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
wing_mat.use_nodes = True


def smooth(obj):
    if obj.type == "MESH":
        for poly in obj.data.polygons:
            poly.use_smooth = True
    return obj


def sphere(name, center, scale, mat, segments=32, rings=20):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    return smooth(obj)


def curve_paths(name, paths, mat, bevel=0.008, resolution=2, taper=False):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 10
    cu.bevel_depth = bevel
    cu.resolution_u = 10
    cu.bevel_resolution = resolution
    for pts in paths:
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for index, (p, coord) in enumerate(zip(sp.points, pts)):
            p.co = (*coord, 1)
            if taper:
                p.radius = 1.0 - 0.85 * index / max(1, len(pts) - 1)
    obj = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def segment(name, start, end, r0, r1, mat, vertices=10):
    a, b = Vector(start), Vector(end)
    axis = b - a
    if axis.length < 0.0001:
        return None
    mid = (a + b) / 2
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r0, radius2=r1, depth=axis.length, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = axis.to_track_quat("Z", "Y").to_euler()
    obj.data.materials.append(mat)
    return smooth(obj)


def lathe(name, x_profile, y_center, z_center, material_slots, band_by_ring=None, side_count=40):
    """Smooth asymmetric abdomen made of specified longitudinal cross sections."""
    verts, faces = [], []
    for x, ry, rz in x_profile:
        for j in range(side_count):
            theta = 2 * math.pi * j / side_count
            verts.append((x, y_center + ry * math.cos(theta), z_center + rz * math.sin(theta)))
    for i in range(len(x_profile) - 1):
        for j in range(side_count):
            a = i * side_count + j
            b = i * side_count + (j + 1) % side_count
            faces.append((a, b, b + side_count, a + side_count))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for mat in material_slots:
        mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = True
        if band_by_ring:
            poly.material_index = band_by_ring[poly.index // side_count]
    return obj


# The Drosophila is roughly 3 mm long in life. Here one Blender unit is visual
# scale only; all features are built proportionally and kept editable.
thorax = sphere("01 thorax | mesonotum", (0.0, 0.0, 1.32), (0.69, 0.49, 0.49), amber, 64, 40)
sphere("thorax dorsal warm scutum", (-0.01, 0, 1.56), (0.59, 0.43, 0.28), ochre, 48, 28)
sphere("thorax posterior scutellum", (0.53, 0, 1.48), (0.22, 0.35, 0.18), abdomen_gold)
sphere("neck collar", (-0.59, 0, 1.30), (0.16, 0.30, 0.28), joint_mat)
for side in (-1, 1):
    sphere("thorax pleural sclerite %s" % side, (0.07, side * 0.425, 1.16),
           (0.27, 0.048, 0.18), amber, 32, 20)
    sphere("wing hinge %s" % side, (0.06, side * 0.43, 1.59),
           (0.087, 0.070, 0.059), joint_mat, 24, 16)
    sphere("tegula | wing base cover %s" % side, (0.045, side * 0.51, 1.62),
           (0.078, 0.052, 0.042), ochre, 24, 16)
# The first raised seam arc did not conform to the thorax and floated visibly
# above its surface. Keep the scutellum geometry without that decorative curve.

abd_profile = [
    (0.47, 0.31, 0.27), (0.64, 0.39, 0.35), (0.84, 0.45, 0.39),
    (1.04, 0.49, 0.43), (1.23, 0.49, 0.43), (1.43, 0.46, 0.40),
    (1.62, 0.40, 0.35), (1.80, 0.31, 0.29), (1.98, 0.16, 0.17),
    (2.04, 0.018, 0.03),
]
lathe("02 abdomen | male tergites", abd_profile, 0, 1.15,
      [abdomen, abdomen_gold, abdomen_dark], [0, 1, 1, 2, 1, 2, 2, 2, 2])
# Dark membranes between the golden tergites, bending around the shell.
seam_paths = []
for x, ry, rz in [(0.78, 0.43, 0.37), (1.10, 0.49, 0.43), (1.40, 0.46, 0.40), (1.67, 0.37, 0.33)]:
    seam_paths.append([(x, ry * math.cos(t), 1.15 + rz * math.sin(t))
                       for t in [2 * math.pi * i / 64 for i in range(65)]])
curve_paths("abdomen | dark segment seams", seam_paths, joint_mat, 0.009)
sphere("abdomen | dark terminalia", (1.92, 0, 1.05), (0.18, 0.19, 0.15), abdomen_dark)
for side in (-1, 1):
    for x, ry in [(0.80, 0.42), (1.10, 0.48), (1.40, 0.45), (1.65, 0.35)]:
        sphere("abdomen | lateral spiracle", (x, side * (ry + 0.004), 1.09),
               (0.026, 0.008, 0.018), joint_mat, 12, 8)

sphere("03 head | face", (-0.91, 0, 1.31), (0.48, 0.41, 0.43), head_mat, 48, 32)
sphere("face | clypeus", (-1.265, 0, 1.12), (0.10, 0.13, 0.12), ochre)
for side in (-1, 1):
    sphere("mouth | paired labella", (-1.325, side * 0.053, 0.97), (0.065, 0.056, 0.043), joint_mat)
segment("proboscis", (-1.27, 0, 1.06), (-1.37, 0, 0.94), 0.045, 0.024, joint_mat)


def make_eye(side):
    center = Vector((-1.02, side * 0.332, 1.41))
    radii = Vector((0.33, 0.215, 0.335))
    sphere("eye | %s base" % side, center, radii, eye_base, 48, 32)
    # The ellipsoid intersects the head. Roughly half of these 1450 samples
    # remain visible, close to the ~700 ommatidia of a male Drosophila eye.
    # Keep the lenses in one mesh to make the scene practical to inspect.
    verts, faces, indices, eye_hairs = [], [], [], []
    golden_angle = math.pi * (3 - math.sqrt(5))
    facet_count = 1450
    for i in range(facet_count):
        z = 1 - 2 * (i + 0.5) / facet_count
        r = math.sqrt(max(0, 1 - z * z))
        theta = i * golden_angle
        unit = Vector((r * math.cos(theta), r * math.sin(theta), z))
        # A fly eye is not a perfect globe: small facets follow the ellipsoid.
        normal = Vector((unit.x / radii.x, unit.y / radii.y, unit.z / radii.z)).normalized()
        tangent = normal.cross(Vector((0, 0, 1)))
        if tangent.length < 0.1:
            tangent = normal.cross(Vector((1, 0, 0)))
        tangent.normalize()
        bitangent = normal.cross(tangent).normalized()
        point = center + Vector((unit.x * radii.x, unit.y * radii.y, unit.z * radii.z)) + normal * 0.001
        base_index = len(verts)
        verts.append(point + normal * 0.0015)
        facet_size = 0.0145 + random.uniform(-0.0004, 0.0004)
        for k in range(6):
            angle = 2 * math.pi * k / 6 + theta * 0.08
            verts.append(point + normal * 0.0004 + facet_size * (math.cos(angle) * tangent + math.sin(angle) * bitangent))
        for k in range(6):
            faces.append((base_index, base_index + 1 + k, base_index + 1 + (k + 1) % 6))
            indices.append(random.randrange(len(eye_facet_mats)))
        if i % 4 == 0 and unit.y * side > 0.23:
            hair_base = point + normal * 0.004 + 0.7 * facet_size * tangent
            eye_hairs.append([hair_base, hair_base + normal * 0.014 + tangent * 0.003])
    mesh = bpy.data.meshes.new("compound eye facets %s" % side)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("eye | %s individual ommatidia" % side, mesh)
    bpy.context.collection.objects.link(obj)
    for mat in eye_facet_mats:
        mesh.materials.append(mat)
    for poly, idx in zip(mesh.polygons, indices):
        poly.material_index = idx
        poly.use_smooth = True
    curve_paths("eye | %s interommatidial microbristles" % side,
                eye_hairs, bristle_mat, 0.0006, 1, taper=True)


for side in (-1, 1):
    make_eye(side)

# Dark simple eyes on top of the head and branched aristae on the antennae.
for x, y in [(-1.21, 0), (-1.11, -0.105), (-1.11, 0.105)]:
    sphere("ocellus", (x, y, 1.695), (0.025, 0.023, 0.015), ocellus_mat, 16, 10)
for side in (-1, 1):
    sphere("antenna pedicel", (-1.345, side * 0.16, 1.43), (0.050, 0.043, 0.056), leg_mat)
    sphere("antenna flagellum", (-1.405, side * 0.16, 1.375), (0.044, 0.044, 0.052), joint_mat)
    arista_root = Vector((-1.43, side * 0.17, 1.425))
    arista_tip = Vector((-1.78, side * 0.32, 1.59))
    curve_paths("arista shaft", [[arista_root, arista_tip]], bristle_mat, 0.003, taper=True)
    branches = []
    for j in range(5):
        p = arista_root.lerp(arista_tip, (j + 1) / 7)
        branches.append([p, p + Vector((-0.065, side * 0.075, 0.07))])
        branches.append([p, p + Vector((-0.035, -side * 0.035, -0.075))])
    curve_paths("arista branches", branches, bristle_mat, 0.0018, taper=True)
    sphere("maxillary palp", (-1.30, side * 0.14, 1.075), (0.048, 0.031, 0.027), leg_mat)

face_hairs = []
head_center = Vector((-0.91, 0.0, 1.31))
for i in range(140):
    y = random.uniform(-0.145, 0.145)
    z = random.uniform(1.14, 1.61)
    relative_y = y / 0.41
    relative_z = (z - head_center.z) / 0.43
    coverage = 1.0 - relative_y * relative_y - relative_z * relative_z
    if coverage <= 0.02:
        continue
    x = head_center.x - 0.48 * math.sqrt(coverage)
    p = Vector((x - 0.002, y, z))
    normal = Vector(((x - head_center.x) / (0.48 * 0.48),
                     y / (0.41 * 0.41),
                     (z - head_center.z) / (0.43 * 0.43))).normalized()
    face_hairs.append([p, p + normal * random.uniform(0.012, 0.027) + Vector((0, 0, 0.004))])
curve_paths("head | facial microsetae", face_hairs, bristle_mat, 0.0009, 1, taper=True)

# Six jointed legs: coxa -> femur -> tibia -> five tarsal subdivisions.
for side in (-1, 1):
    for leg_index, x in enumerate((-0.34, 0.05, 0.42)):
        y = side * 0.31
        hip = Vector((x, y, 0.99))
        knee = Vector((x + (-0.77, 0.42, 0.66)[leg_index],
                       side * (0.77, 0.91, 0.83)[leg_index],
                       (0.64, 0.66, 0.58)[leg_index]))
        ankle = Vector((x + (-0.62, -0.15, 1.03)[leg_index],
                        side * (1.07, 1.18, 1.22)[leg_index], 0.16))
        toe = Vector((ankle.x + (-0.24, 0.11, 0.18)[leg_index],
                      ankle.y + side * 0.10, 0.055))
        sphere("leg %s.%s coxa" % (side, leg_index), hip, (0.070, 0.061, 0.071), leg_mat)
        segment("leg %s.%s femur" % (side, leg_index), hip, knee, 0.047, 0.033, leg_mat)
        sphere("leg %s.%s knee" % (side, leg_index), knee, (0.029, 0.029, 0.029), joint_mat)
        segment("leg %s.%s tibia" % (side, leg_index), knee, ankle, 0.025, 0.014, leg_mat)
        for step in range(5):
            start = ankle.lerp(toe, step / 5)
            end = ankle.lerp(toe, (step + 1) / 5)
            segment("leg %s.%s tarsus %s" % (side, leg_index, step), start, end,
                    0.014 - step * 0.0012, 0.012 - step * 0.0012, tarsus_mat, 8)
        for toe_side in (-1, 1):
            segment("claw", toe, toe + Vector((-0.036, toe_side * 0.035, -0.015)),
                    0.009, 0.002, joint_mat, 8)
        if leg_index == 0:
            # A male-specific comb of stout dark bristles on the foreleg's
            # first tarsal segment. Each tooth is its own tapered shaft.
            comb = []
            for tooth in range(11):
                p = ankle.lerp(toe, 0.055 + tooth * 0.012)
                p += Vector((0, -side * 0.008, 0.009))
                comb.append([p, p + Vector((0.005, -side * 0.040, 0.014))])
            curve_paths("male foreleg | sex comb", comb, abdomen_dark, 0.003, 1, taper=True)
        # Tiny tactile leg hairs emphasize taper without making the leg furry.
        leg_hairs = []
        for j in range(26):
            p = knee.lerp(ankle, (j + 0.4) / 27)
            leg_hairs.append([p, p + Vector((0.014 * (-1) ** j, side * 0.026, 0.012))])
        curve_paths("tibial setae", leg_hairs, bristle_mat, 0.0014, taper=True)


def wing_point(side, u, v):
    """A veined, slightly cambered wing, widening from a narrow root."""
    # u is root to tip; v is trailing edge (-1) to leading edge (+1).
    width = (math.sin(math.pi * u) ** 0.65) * (0.46 + 0.13 * u)
    center = Vector((0.10 + 2.40 * u,
                     side * (0.42 + 0.67 * u),
                     1.60 + 0.18 * u + 0.045 * math.sin(math.pi * u)))
    chord = Vector((0.31, side * -0.78, 0.07 * math.sin(math.pi * u)))
    return center + chord * (v * width) + Vector((0, 0, 0.028 * math.sin(math.pi * u) * (1 - v * v)))


for side in (-1, 1):
    along, across = 26, 12
    verts, faces = [], []
    for i in range(along + 1):
        u = i / along
        for j in range(across + 1):
            v = -1 + 2 * j / across
            verts.append(wing_point(side, u, v))
    for i in range(along):
        for j in range(across):
            a = i * (across + 1) + j
            faces.append((a, a + 1, a + across + 2, a + across + 1))
    mesh = bpy.data.meshes.new("wing membrane")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("wing | %s thin membrane" % side, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(wing_mat)
    for poly in mesh.polygons:
        poly.use_smooth = True
    # Longitudinal vein paths approximate the dipteran radial, medial, and
    # cubital branches. The r-m and dm-cu crossveins are sparse and distinct.
    veins = []
    vein_defs = [
        # (root u, root v, end u, end v)
        (0.01, 0.86, 0.99, 0.99),  # costa
        (0.04, 0.50, 0.46, 1.00),  # R1
        (0.07, 0.35, 0.81, 1.00),  # R2+3
        (0.08, 0.18, 0.98, 0.62),  # R4+5
        (0.09, -0.10, 0.98, -0.09),  # M1
        (0.13, -0.36, 0.77, -1.00),  # CuA1
        (0.15, -0.58, 0.49, -1.00),  # A1
    ]
    for u0, v0, u1, v1 in vein_defs:
        veins.append([wing_point(side, u0 + (u1 - u0) * k / 26,
                                 v0 + (v1 - v0) * (k / 26) ** 1.65)
                      for k in range(27)])
    for u, v0, v1 in [(0.38, -0.11, 0.18), (0.62, -0.58, -0.09)]:
        veins.append([wing_point(side, u, v0 + (v1 - v0) * k / 8)
                      for k in range(9)])
    curve_paths("wing | %s longitudinal and cross veins" % side, veins, vein_mat, 0.0034)
    margin = [[wing_point(side, i / 40, edge) for i in range(41)] for edge in (-1, 1)]
    curve_paths("wing | %s margins" % side, margin, wing_edge_mat, 0.003)
    fringe = []
    for edge in (-1, 1):
        for k in range(1, 45):
            u = k / 46
            p = wing_point(side, u, edge)
            q = p + Vector((0.019, side * edge * 0.035, 0.008))
            fringe.append([p, q])
    curve_paths("wing | %s marginal microtrichia" % side, fringe, bristle_light, 0.0012, taper=True)
    # The small rear flight-balance organ is distinct from the wing.
    haltere_base = Vector((0.54, side * 0.38, 1.20))
    haltere_tip = Vector((0.79, side * 0.74, 1.26))
    segment("haltere stalk", haltere_base, haltere_tip, 0.016, 0.010, leg_mat)
    sphere("haltere club", haltere_tip, (0.052, 0.045, 0.040), ochre)


# Small cuticular bristles. Rather than random points in a volume, place them
# on the true ellipsoid surface, angled backwards like the specimen's setae.
hairs_dark, hairs_gold = [], []
for i in range(1400):
    phi = random.uniform(0.0, 2 * math.pi)
    costheta = random.uniform(-0.78, 0.97)
    sintheta = math.sqrt(1 - costheta * costheta)
    unit = Vector((sintheta * math.cos(phi), sintheta * math.sin(phi), costheta))
    point = Vector((0.0, 0.0, 1.32)) + Vector((unit.x * 0.696, unit.y * 0.496, unit.z * 0.497))
    if point.z < 1.03:
        continue
    normal = Vector((unit.x / 0.69, unit.y / 0.49, unit.z / 0.49)).normalized()
    length = random.uniform(0.032, 0.072)
    end = point + normal * length + Vector((0.035, 0, 0.016))
    (hairs_gold if i % 5 == 0 else hairs_dark).append([point, end])
curve_paths("thorax | fine dark setae", hairs_dark, bristle_mat, 0.0012, 1, taper=True)
curve_paths("thorax | fine gold setae", hairs_gold, bristle_light, 0.0013, 1, taper=True)
large_bristles = []
for side in (-1, 1):
    for x in (-0.45, -0.23, 0.05, 0.36):
        large_bristles.append([(x, side * 0.29, 1.72),
                               (x + 0.035, side * 0.34, 1.82),
                               (x + 0.095, side * 0.38, 1.91)])
    for x in (0.55, 0.66):
        large_bristles.append([(x, side * 0.25, 1.57),
                               (x + 0.08, side * 0.34, 1.69)])
curve_paths("thorax | long macrochaetae", large_bristles, bristle_mat, 0.0028, taper=True)

# Abdomen hairs follow the posterior taper and are shorter than thorax hairs.
abd_hairs = []
for i in range(430):
    x = random.uniform(0.64, 1.89)
    profile_idx = min(range(len(abd_profile)), key=lambda k: abs(abd_profile[k][0] - x))
    _, ry, rz = abd_profile[profile_idx]
    angle = random.uniform(0, 2 * math.pi)
    p = Vector((x, ry * math.cos(angle), 1.15 + rz * math.sin(angle)))
    normal = Vector((0.3, math.cos(angle), math.sin(angle))).normalized()
    abd_hairs.append([p, p + normal * random.uniform(0.023, 0.06) + Vector((0.025, 0, 0))])
curve_paths("abdomen | fine setae", abd_hairs, bristle_mat, 0.0014, 1, taper=True)


# A restrained photographic set: matte green-grey perch, cool backdrop, warm
# key light, cool rim, and a camera close enough to show eye facets and veins.
perch = material("perch | muted olive stone", (0.11, 0.15, 0.12), 0.9, texture=0.3)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0.10, 0.0, -0.125))
ground = bpy.context.object
ground.name = "studio macro surface"
ground.scale = (2000, 2000, 0.35)
ground.data.materials.append(perch)
bevel = ground.modifiers.new("soft floor edge", "BEVEL")
bevel.width = 0.1
bevel.segments = 3

world = bpy.context.scene.world
world.color = (0.12, 0.12, 0.12)
world.use_nodes = True
world_nodes = world.node_tree.nodes
world_nodes.clear()
world_links = world.node_tree.links
world_output = world_nodes.new("ShaderNodeOutputWorld")
ambient = world_nodes.new("ShaderNodeBackground")
ambient.inputs["Color"].default_value = (0.18, 0.21, 0.20, 1)
ambient.inputs["Strength"].default_value = 0.5
camera_background = world_nodes.new("ShaderNodeBackground")
camera_background.inputs["Color"].default_value = (0.013, 0.018, 0.016, 1)
camera_background.inputs["Strength"].default_value = 0.5
light_path = world_nodes.new("ShaderNodeLightPath")
background_mix = world_nodes.new("ShaderNodeMixShader")
world_links.new(light_path.outputs["Is Camera Ray"], background_mix.inputs[0])
world_links.new(ambient.outputs[0], background_mix.inputs[1])
world_links.new(camera_background.outputs[0], background_mix.inputs[2])
world_links.new(background_mix.outputs[0], world_output.inputs["Surface"])


def area_light(name, location, power, color, size, target=(0, 0, 1.2)):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


area_light("large warm softbox", (-3.3, -4.1, 6.0), 260, (1.0, 0.83, 0.64), 4.4)
area_light("cool rim through wings", (1.6, 3.2, 4.2), 340, (0.73, 0.84, 1.0), 2.5)
area_light("front eye catchlight", (-4.5, 0.5, 2.9), 90, (1.0, 0.95, 0.82), 1.6)

bpy.ops.object.camera_add(location=(-4.7, -5.3, 3.20))
camera = bpy.context.object
camera.name = "macro three-quarter camera"
target = Vector((0.20, 0.0, 1.22))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "PERSP"
camera.data.lens = 49
camera.data.dof.use_dof = True
camera.data.dof.focus_distance = (target - camera.location).length
camera.data.dof.aperture_fstop = 18
bpy.context.scene.camera = camera

bpy.ops.object.camera_add(location=(-2.85, -2.58, 2.26))
detail_camera = bpy.context.object
detail_camera.name = "compound eye and thorax detail camera"
detail_target = Vector((-0.92, -0.06, 1.37))
detail_camera.rotation_euler = (detail_target - detail_camera.location).to_track_quat("-Z", "Y").to_euler()
detail_camera.data.type = "PERSP"
detail_camera.data.lens = 60
detail_camera.data.dof.use_dof = True
detail_camera.data.dof.focus_distance = (detail_target - detail_camera.location).length
detail_camera.data.dof.aperture_fstop = 16
bpy.context.scene.camera = camera

scene = bpy.context.scene
scene.render.engine = "CYCLES"
preview = os.environ.get("FLY_RENDER_PREVIEW") == "1"
scene.cycles.samples = 56 if preview else 160
scene.cycles.use_denoising = True
scene.render.resolution_x = 1200 if preview else 2400
scene.render.resolution_y = 900 if preview else 1800
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX"
scene.render.filepath = str(OUTPUT / ("male_drosophila_preview.png" if preview else "male_drosophila_macro.png"))

# Use the local GTX 1070 when Cycles exposes it, without saving any global
# Blender preferences. The scene still renders on CPU when CUDA is unavailable.
cycles_prefs = bpy.context.preferences.addons["cycles"].preferences
try:
    cycles_prefs.compute_device_type = "CUDA"
    cycles_prefs.get_devices()
    cuda_devices = [device for device in cycles_prefs.devices if device.type == "CUDA"]
    if cuda_devices:
        for device in cycles_prefs.devices:
            device.use = device.type == "CUDA"
        scene.cycles.device = "GPU"
        print("CYCLES_DEVICE", [device.name for device in cuda_devices])
except Exception as exc:
    scene.cycles.device = "CPU"
    print("CYCLES_CPU_FALLBACK", exc)

# Save a normal editable .blend alongside the generator script. The output PNG
# is deliberately outside Git by default, but is convenient to inspect/share.
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "male_drosophila_macro.blend"))
bpy.ops.render.render(write_still=True)
print("ARTIFACT", scene.render.filepath)

scene.camera = detail_camera
scene.render.filepath = str(OUTPUT / ("male_drosophila_detail_preview.png" if preview else "male_drosophila_detail.png"))
if not preview:
    scene.render.resolution_x = 2000
    scene.render.resolution_y = 1500
    scene.cycles.samples = 128
bpy.ops.render.render(write_still=True)
print("ARTIFACT", scene.render.filepath)

scene.camera = camera
scene.render.resolution_x = 1200 if preview else 2400
scene.render.resolution_y = 900 if preview else 1800
scene.cycles.samples = 56 if preview else 160
scene.render.filepath = str(OUTPUT / ("male_drosophila_preview.png" if preview else "male_drosophila_macro.png"))
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "male_drosophila_macro.blend"))
