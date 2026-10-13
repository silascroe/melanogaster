"""Build v2 of the fly art from the preserved v1 Blender file.

Usage from the FlyTest root:
  tools/blender/blender-5.2.2-windows-x64/blender.exe -b \
    fly-creature/art/versions/v1-original/male_drosophila_v1.blend \
    --python fly-creature/tools/refine_fly_model.py

v1's legs were straight, untapered tubes with a stub of a tarsus, which made
the fly stand on tiptoe like a mosquito. This script replaces them with legs
made of the real segments (coxa, trochanter, femur, tibia, five tarsomeres,
paired claws and pulvilli), proportioned after Drosophila melanogaster: a
stout tapering femur, a slender tibia, and a tarsus about as long as the tibia
whose distal tarsomeres rest on the ground. It adds rows of leg bristles, the
male foreleg sex comb, and joint markers that export_fly_model.py turns into a
three-joint (hip, knee, ankle) rig for Godot.

Proportions are approximate, taken by eye from published descriptions of
Drosophila legs; this is art, not morphometry. Coordinates follow v1: the head
faces -X, +Z is up, the ground is z = 0, and side -1 / +1 is -Y / +Y.
"""

import math
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

PROJECT = Path(__file__).resolve().parents[1]
DEST = PROJECT / "art" / "male_drosophila_v2.blend"


# --------------------------------------------------------------------------
# Geometry helpers

def profile(points, t):
    """Piecewise-linear lookup in [(t, value), ...], eased between keys."""
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t <= t1:
            u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            u = u * u * (3.0 - 2.0 * u)
            return v0 + (v1 - v0) * u
    return points[-1][1]


def frames(centerline):
    """Parallel-transport frames (tangent, normal, binormal) along a polyline."""
    n = len(centerline)
    tangents = [(centerline[min(i + 1, n - 1)] - centerline[max(i - 1, 0)]).normalized()
                for i in range(n)]
    up = Vector((0.0, 0.0, 1.0))
    normal = tangents[0].cross(up)
    if normal.length < 1e-4:
        normal = tangents[0].cross(Vector((0.0, 1.0, 0.0)))
    normal.normalize()
    out = []
    for tangent in tangents:
        normal = (normal - tangent * normal.dot(tangent)).normalized()
        out.append((tangent, normal, tangent.cross(normal)))
    return out


class MeshBuilder:
    """Accumulates tubes, spheres and cones into one bmesh with UVs."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")

    def _face(self, verts, uvs):
        face = self.bm.faces.new(verts)
        for loop, uv in zip(face.loops, uvs):
            loop[self.uv].uv = uv
        return face

    def tube(self, centerline, radii, sides=14, flatten=1.0, caps=True):
        rings = []
        lengths = [0.0]
        for a, b in zip(centerline, centerline[1:]):
            lengths.append(lengths[-1] + (b - a).length)
        total = max(lengths[-1], 1e-6)
        for point, radius, (tangent, normal, binormal) in zip(centerline, radii, frames(centerline)):
            ring = []
            for j in range(sides):
                angle = math.tau * j / sides
                offset = normal * (math.cos(angle) * radius * flatten) + binormal * (math.sin(angle) * radius)
                ring.append(self.bm.verts.new(point + offset))
            rings.append(ring)
        for i in range(len(rings) - 1):
            v0, v1 = lengths[i] / total, lengths[i + 1] / total
            for j in range(sides):
                k = (j + 1) % sides
                u0, u1 = j / sides, (j + 1) / sides
                self._face([rings[i][j], rings[i][k], rings[i + 1][k], rings[i + 1][j]],
                           [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        if caps:
            for ring, point, v, flip in ((rings[0], centerline[0], 0.0, True),
                                         (rings[-1], centerline[-1], 1.0, False)):
                center = self.bm.verts.new(point)
                for j in range(sides):
                    k = (j + 1) % sides
                    tri = [ring[j], ring[k], center]
                    if flip:
                        tri.reverse()
                    self._face(tri, [(0.5, v)] * 3)

    def ellipsoid(self, center, radii, segments=14, rings=8, axis=None):
        """An ellipsoid; with axis given, radii.z lies along that direction."""
        if axis is not None:
            z = axis.normalized()
            x = z.cross(Vector((0.0, 0.0, 1.0)))
            if x.length < 1e-4:
                x = z.cross(Vector((0.0, 1.0, 0.0)))
            x.normalize()
            y = z.cross(x)
        else:
            x, y, z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
        grid = []
        for i in range(rings + 1):
            phi = math.pi * i / rings
            row = []
            for j in range(segments):
                theta = math.tau * j / segments
                p = (x * (math.sin(phi) * math.cos(theta) * radii[0])
                     + y * (math.sin(phi) * math.sin(theta) * radii[1])
                     + z * (math.cos(phi) * radii[2]))
                row.append(self.bm.verts.new(center + p))
            grid.append(row)
        for i in range(rings):
            for j in range(segments):
                k = (j + 1) % segments
                self._face([grid[i][j], grid[i + 1][j], grid[i + 1][k], grid[i][k]],
                           [(j / segments, i / rings), (j / segments, (i + 1) / rings),
                            ((j + 1) / segments, (i + 1) / rings), ((j + 1) / segments, i / rings)])

    def cone(self, base, tip, radius, sides=4):
        axis = (tip - base).normalized()
        side = axis.cross(Vector((0.0, 0.0, 1.0)))
        if side.length < 1e-4:
            side = axis.cross(Vector((1.0, 0.0, 0.0)))
        side.normalize()
        other = axis.cross(side)
        ring = [self.bm.verts.new(base + (side * math.cos(math.tau * j / sides)
                                         + other * math.sin(math.tau * j / sides)) * radius)
                for j in range(sides)]
        apex = self.bm.verts.new(tip)
        for j in range(sides):
            self._face([ring[j], ring[(j + 1) % sides], apex], [(0, 0), (1, 0), (0.5, 1)])

    def build(self, name, material):
        mesh = bpy.data.meshes.new(name)
        self.bm.normal_update()
        self.bm.to_mesh(mesh)
        self.bm.free()
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        mesh.materials.append(bpy.data.materials[material])
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def sample(start, end, count, bow=Vector()):
    """Points from start to end, bowed sideways by `bow` at the middle."""
    return [start.lerp(end, i / (count - 1)) + bow * math.sin(math.pi * i / (count - 1))
            for i in range(count)]


def bow_vector(start, end, toward, amount):
    axis = (end - start).normalized()
    side = toward - axis * toward.dot(axis)
    return side.normalized() * amount if side.length > 1e-6 else Vector()


def empty(name, location):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.05
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    return obj


def horizontal(angle_deg, side):
    """Horizontal unit vector: 0 deg points straight out to the side, + is forward."""
    a = math.radians(angle_deg)
    return Vector((-math.sin(a), side * math.cos(a), 0.0))


def direction(angle_deg, elevation_deg, side):
    e = math.radians(elevation_deg)
    return horizontal(angle_deg, side) * math.cos(e) + Vector((0.0, 0.0, math.sin(e)))


# --------------------------------------------------------------------------
# Leg design (model units; the body is ~3.5 units long, ~2.3 mm in life)

FEMUR_PROFILE = [(0.0, 0.70), (0.22, 1.0), (0.62, 0.92), (0.9, 0.74), (1.0, 0.66)]
TIBIA_PROFILE = [(0.0, 0.82), (0.08, 0.92), (0.5, 0.86), (0.9, 1.0), (1.0, 0.9)]
TARSOMERE_PROFILE = [(0.0, 0.78), (0.14, 1.0), (0.8, 0.94), (1.0, 0.76)]
TARSOMERE_FRACTIONS = (0.38, 0.19, 0.14, 0.11, 0.18)  # basitarsus longest

LEGS = {
    # coxa_top lies inside the thorax; coxa_end is the coxa-trochanter joint,
    # which is also the rig's hip pivot.
    0: dict(name="fore", coxa_top=Vector((-0.30, 0.15, 0.96)), coxa_end=Vector((-0.40, 0.22, 0.78)),
            coxa_radius=0.078, femur=(52.0, 10.0, 0.62), femur_radius=0.074,
            tibia=(50.0, 0.40, 0.56), tibia_radius=0.044, tarsus=(38.0, 0.60), tarsus_radius=0.031),
    1: dict(name="mid", coxa_top=Vector((0.05, 0.17, 0.92)), coxa_end=Vector((0.07, 0.25, 0.79)),
            coxa_radius=0.062, femur=(6.0, 16.0, 0.68), femur_radius=0.062,
            tibia=(10.0, 0.40, 0.68), tibia_radius=0.040, tarsus=(12.0, 0.62), tarsus_radius=0.029),
    2: dict(name="hind", coxa_top=Vector((0.36, 0.16, 0.92)), coxa_end=Vector((0.41, 0.24, 0.80)),
            coxa_radius=0.062, femur=(-40.0, 16.0, 0.74), femur_radius=0.064,
            tibia=(-46.0, 0.44, 0.66), tibia_radius=0.041, tarsus=(-50.0, 0.56), tarsus_radius=0.029),
}
SETAE_RADIUS = 0.0026


def add_setae(builder, centerline, radii, rows, per_row, length, tilt_deg, seed,
              skip_inner=False):
    """Short bristles in longitudinal rows, leaning toward the leg tip."""
    rng = _rng(seed)
    fr = frames(centerline)
    n = len(centerline)
    tilt = math.radians(tilt_deg)
    for row in range(rows):
        base_angle = math.tau * row / rows
        for k in range(per_row):
            t = (k + 0.5 + (rng() - 0.5) * 0.6) / per_row
            t = min(max(t, 0.04), 0.96)
            i = min(int(t * (n - 1)), n - 2)
            u = t * (n - 1) - i
            tangent, normal, binormal = fr[i]
            point = centerline[i].lerp(centerline[i + 1], u)
            radius = radii[i] + (radii[i + 1] - radii[i]) * u
            angle = base_angle + (rng() - 0.5) * 0.5
            radial = normal * math.cos(angle) + binormal * math.sin(angle)
            if skip_inner and radial.z > 0.55:
                continue
            base = point + radial * radius * 0.92
            lean = (tangent * math.cos(tilt) + radial * math.sin(tilt)).normalized()
            builder.cone(base, base + lean * length * (0.75 + 0.5 * rng()), SETAE_RADIUS)


def _rng(seed):
    state = [seed * 2654435761 % 4294967296 or 1]

    def next_value():
        state[0] = (1103515245 * state[0] + 12345) % 2147483648
        return state[0] / 2147483648

    return next_value


def build_leg(index, side):
    spec = LEGS[index]
    prefix = "leg %s.%s " % (float(side), index)
    flip = Vector((1.0, side, 1.0))
    coxa_top = spec["coxa_top"] * flip
    hip = spec["coxa_end"] * flip
    up = Vector((0.0, 0.0, 1.0))

    # Coxa: a short, broad segment hanging from the thorax underside.
    coxa = MeshBuilder()
    line = sample(coxa_top, hip, 8)
    r = spec["coxa_radius"]
    coxa.tube(line, [r * profile([(0, 0.9), (0.4, 1.0), (1, 0.72)], i / 7) for i in range(8)], sides=16)
    coxa.build(prefix + "coxa", "legs | warm brown")

    # Femur (with the small trochanter at its base).
    femur_angle, femur_elev, femur_len = spec["femur"]
    knee = hip + direction(femur_angle, femur_elev, side) * femur_len
    femur_line = sample(hip, knee, 18, bow_vector(hip, knee, up, 0.025))
    femur_radii = [spec["femur_radius"] * profile(FEMUR_PROFILE, i / 17) for i in range(18)]
    femur = MeshBuilder()
    femur.tube(femur_line, femur_radii, sides=16, flatten=0.86)
    trochanter_end = hip + direction(femur_angle, femur_elev, side) * 0.09
    femur.ellipsoid(hip.lerp(trochanter_end, 0.5), (0.05, 0.05, 0.07), axis=trochanter_end - hip)
    femur.build(prefix + "femur", "legs | warm brown")
    femur_setae = MeshBuilder()
    add_setae(femur_setae, femur_line, femur_radii, rows=7, per_row=10, length=0.055, tilt_deg=16,
              seed=index * 10 + side + 3)
    femur_setae.build(prefix + "femur setae", "bristles | sepia")

    # Tibia: knee down and out to the ankle.
    tibia_angle, ankle_height, tibia_len = spec["tibia"]
    drop = knee.z - ankle_height
    reach = math.sqrt(max(tibia_len ** 2 - drop ** 2, 0.0))
    ankle = Vector((knee.x, knee.y, ankle_height)) + horizontal(tibia_angle, side) * reach
    tibia_line = sample(knee, ankle, 16, bow_vector(knee, ankle, horizontal(tibia_angle, side), -0.018))
    tibia_radii = [spec["tibia_radius"] * profile(TIBIA_PROFILE, i / 15) for i in range(16)]
    tibia = MeshBuilder()
    tibia.tube(tibia_line, tibia_radii, sides=14)
    tibia.build(prefix + "tibia", "legs | warm brown")
    setae = MeshBuilder()
    add_setae(setae, tibia_line, tibia_radii, rows=8, per_row=12, length=0.05, tilt_deg=14,
              seed=index * 10 + side + 7)
    if index == 1:
        # The midleg's long apical tibial spur, a reliable fly landmark.
        tip = tibia_line[-2]
        setae.cone(tip, tip + (tibia_line[-1] - tibia_line[-4]).normalized() * 0.11
                   + Vector((0, 0, -0.02)), 0.007)
    setae.build(prefix + "tibia setae", "bristles | sepia")

    knee_cap = MeshBuilder()
    knee_cap.ellipsoid(knee, (0.045, 0.045, 0.05), axis=knee - femur_line[-3])
    knee_cap.build(prefix + "knee", "joints | dark umber")

    # Tarsus: five tarsomeres arcing from the ankle down onto the ground.
    tarsus_angle, tarsus_len = spec["tarsus"]
    out = horizontal(tarsus_angle, side)
    ground_z = spec["tarsus_radius"] * 0.85 + 0.004
    dz = ankle.z - ground_z
    span = math.sqrt(max((tarsus_len * 0.96) ** 2 - dz ** 2, 0.05))
    p0 = ankle
    p2 = Vector((ankle.x, ankle.y, ground_z)) + out * span
    p1 = Vector((ankle.x, ankle.y, ground_z)) + out * (span * 0.42)  # bend toward the ground

    def bezier(t):
        return p0 * ((1 - t) ** 2) + p1 * (2 * (1 - t) * t) + p2 * (t * t)

    tarsus = MeshBuilder()
    tarsal_setae = MeshBuilder()
    t0 = 0.0
    for k, fraction in enumerate(TARSOMERE_FRACTIONS):
        t1 = t0 + fraction
        line = [bezier(t0 + (t1 - t0) * i / 7) for i in range(8)]
        scale = spec["tarsus_radius"] * (1.0 - 0.07 * k)
        radii = [scale * profile(TARSOMERE_PROFILE, i / 7) for i in range(8)]
        tarsus.tube(line, radii, sides=12)
        add_setae(tarsal_setae, line, radii, rows=5, per_row=max(2, int(9 * fraction)),
                  length=0.032, tilt_deg=20, seed=index * 100 + k * 7 + side, skip_inner=True)
        if k == 0 and index == 0:
            # Male sex comb: a row of dark, blunt teeth on the foreleg basitarsus.
            comb = MeshBuilder()
            fr = frames(line)
            for tooth in range(11):
                u = 0.35 + 0.6 * tooth / 10
                i = min(int(u * 7), 6)
                tangent, normal, binormal = fr[i]
                point = line[i].lerp(line[i + 1], u * 7 - i)
                ventral = Vector((0.0, 0.0, -1.0))
                front = Vector((-1.0, 0.0, 0.0))
                radial = (ventral * 0.5 + front * 0.85)
                radial = (radial - tangent * radial.dot(tangent)).normalized()
                base = point + radial * scale * 0.85
                comb.cone(base, base + (radial * 0.85 + tangent * 0.5).normalized() * 0.036, 0.0075)
            comb.build(prefix + "sex comb", "abdomen | male dark bands")
        t0 = t1
    tarsus.build(prefix + "tarsus", "tarsi | dark brown")
    tarsal_setae.build(prefix + "tarsal setae", "bristles | sepia")

    # Paired claws and pale pulvilli at the tip.
    tip = bezier(1.0)
    forward = (bezier(1.0) - bezier(0.94)).normalized()
    lateral = forward.cross(Vector((0.0, 0.0, 1.0))).normalized()
    claws = MeshBuilder()
    pads = MeshBuilder()
    for splay in (-1.0, 1.0):
        heading = (forward + lateral * splay * 0.45).normalized()
        hook = [tip + heading * (0.05 * s) + Vector((0, 0, 0.012 - 0.035 * s * s)) for s in
                (i / 7 for i in range(8))]
        claws.tube(hook, [0.009 * (1.0 - 0.8 * i / 7) for i in range(8)], sides=6)
        pads.ellipsoid(tip + heading * 0.025 + Vector((0, 0, -0.012)), (0.022, 0.014, 0.012),
                       segments=10, rings=6, axis=Vector((0, 0, 1)))
    claw_obj = claws.build(prefix + "claws", "joints | dark umber")
    pads.build(prefix + "pulvilli", "pulvilli | pale pad")

    lowest = min((claw_obj.matrix_world @ v.co).z for v in claw_obj.data.vertices)
    empty(prefix + "| hip joint", hip)
    empty(prefix + "| knee joint", knee)
    empty(prefix + "| ankle joint", ankle)
    empty(prefix + "| claw tip", Vector((tip.x, tip.y, lowest)) + forward * 0.03)


# --------------------------------------------------------------------------

def remove_v1_legs():
    doomed = [obj for obj in bpy.data.objects
              if obj.name.startswith("leg ") or obj.name.startswith("claw")
              or obj.name.startswith("tibial setae") or obj.name.startswith("male foreleg | sex comb")]
    for obj in doomed:
        bpy.data.objects.remove(obj, do_unlink=True)
    return len(doomed)


def ensure_pad_material():
    if "pulvilli | pale pad" in bpy.data.materials:
        return
    mat = bpy.data.materials.new("pulvilli | pale pad")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.78, 0.66, 0.44, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Specular IOR Level"].default_value = 0.3


def new_material(name, color, roughness):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    # Match the exporter's low specular; the default sheen washes dark parts grey.
    bsdf.inputs["Specular IOR Level"].default_value = 0.2
    return mat


def rebuild_face():
    """Replace v1's ball-shaped antennae, palps and clypeus with fly-shaped parts.

    Drosophila's antenna is a short pedicel from which the velvety third segment
    hangs down over the face; the feathery arista (kept from v1) rises from its
    upper base. The maxillary palps are small forward-pointing clubs. v1's
    clypeus knob is dropped: on the reshaped head it read as a cartoon nose.
    """
    for name in ("antenna pedicel", "antenna flagellum", "maxillary palp", "face | clypeus"):
        for obj in [o for o in bpy.data.objects if o.name.startswith(name)]:
            bpy.data.objects.remove(obj, do_unlink=True)
    # Linear color values (Blender stores linear; these display as a dusky tan-grey).
    new_material("antenna | velvet funiculus", (0.15, 0.08, 0.035), 0.95)
    for side in (-1, 1):
        pedicel = MeshBuilder()
        pedicel.ellipsoid(Vector((-1.375, 0.16 * side, 1.465)), (0.045, 0.045, 0.042),
                          axis=Vector((-1.0, 0.25 * side, -0.4)))
        pedicel.build("antenna pedicel" + ("" if side < 0 else ".001"), "head | warm honey")
        third = MeshBuilder()
        third.ellipsoid(Vector((-1.42, 0.165 * side, 1.37)), (0.042, 0.035, 0.078),
                        axis=Vector((-0.32, 0.14 * side, 1.0)))
        third.build("antenna flagellum" + ("" if side < 0 else ".001"), "antenna | velvet funiculus")
        # Palps flank the mouth on the underside of the head (v2 head shape).
        palp = MeshBuilder()
        center = Vector((-1.215, 0.125 * side, 1.0))
        axis = Vector((-1.0, 0.2 * side, 0.15)).normalized()
        palp.ellipsoid(center, (0.026, 0.024, 0.058), axis=axis)
        palp_setae = [center + axis * (0.058 * f) for f in (-0.4, 0.2, 0.7, 0.95)]
        rng = _rng(91 + side)
        for point in palp_setae:
            for k in range(2):
                spread = Vector(((rng() - 0.5) * 0.6, side * (0.3 + rng() * 0.5), -0.2 + rng() * 0.5))
                palp.cone(point, point + (axis * 0.7 + spread).normalized() * 0.035, SETAE_RADIUS)
        palp.build("maxillary palp" + ("" if side < 0 else ".001"), "legs | warm brown")


def slim_neck():
    """v1's neck collar is nearly as tall as the head; a fly's neck is a narrow,
    dark membrane, so shrink it around its own center and darken it."""
    neck = bpy.data.objects["neck collar"]
    center = world_center(neck)
    neck.matrix_world = (Matrix.Translation(center) @ Matrix.Diagonal((1.0, 0.62, 0.62, 1.0))
                         @ Matrix.Translation(-center) @ neck.matrix_world)
    neck.data.materials.clear()
    neck.data.materials.append(new_material("neck | dark membrane", (0.03, 0.017, 0.009), 0.75))


def matte_eyes():
    """Compound eyes scatter light from thousands of facets; v1's read as glass."""
    for mat in bpy.data.materials:
        if mat.name.startswith("eye") and mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    node.inputs["Roughness"].default_value = 0.48
                    if "Coat Weight" in node.inputs:
                        node.inputs["Coat Weight"].default_value = 0.0


# --------------------------------------------------------------------------
# Head capsule
#
# v1's head is a sphere scaled to (0.48, 0.41, 0.43) with two eye spheres
# pushed into its sides, which reads as a ball wearing headphones. A
# Drosophila head is short front-to-back (about 60% of its height) with a
# flattened back, its sides mostly compound eye set into the capsule, a broad
# flat frons between the eyes, a shallow recess on the face where the
# antennae hang, and narrow cheeks below the eyes. reshape_head() remaps the
# v1 face mesh onto that shape point by point (keeping its UVs and textures),
# re-seats the eyes with one affine transform each (keeping every facet), and
# carries everything attached to the head along with the surface.

OLD_HEAD_CENTER = Vector((-0.91, 0.0, 1.31))
OLD_HEAD_RADII = Vector((0.48, 0.41, 0.43))
HEAD_CENTER = Vector((-0.97, 0.0, 1.31))
OLD_EYE = dict(center=Vector((-1.02, 0.332, 1.41)), radii=Vector((0.33, 0.215, 0.335)))
MOUTH_SHIFT = Vector((0.14, 0.0, 0.0))
ANTENNA_INSET = 0.04      # antennae sit close together either side of the facial carina
NEW_EYE = dict(center=Vector((-1.005, 0.295, 1.37)), radii=Vector((0.265, 0.24, 0.375)))


def smoothstep(edge0, edge1, x):
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def head_field(q):
    """< 0 inside the new head capsule; q is relative to HEAD_CENTER."""
    front = q.x < 0.0
    ax, ex = (0.33, 2.4) if front else (0.34, 2.8)    # flat frons, flatter occiput
    z = HEAD_CENTER.z + q.z
    lateral = 0.50 * (1.0 - 0.30 * smoothstep(1.16, 0.90, z))  # narrow cheeks
    vertical = 0.42 if q.z > 0.0 else 0.40
    value = (abs(q.x) / ax) ** ex + (abs(q.y) / lateral) ** 2 + (abs(q.z) / vertical) ** 2 - 1.0
    if front:
        # Shallow facial recess under the antennae.
        recess = (1.0 - smoothstep(0.10, 0.21, abs(q.y))) * smoothstep(0.92, 1.06, z)
        recess *= 1.0 - smoothstep(1.36, 1.46, z)
        value += 0.42 * recess * smoothstep(0.0, -0.25, q.x)
    return value


def new_head_radius(direction):
    lo, hi = 0.0, 1.5
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if head_field(direction * mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return lo


def warp_head_point(p):
    """Map a point on or near the v1 head onto the same place on the new head."""
    offset = p - OLD_HEAD_CENTER
    distance = offset.length
    if distance < 1e-6:
        return HEAD_CENTER.copy()
    direction = offset / distance
    scaled = Vector((direction.x / OLD_HEAD_RADII.x, direction.y / OLD_HEAD_RADII.y,
                     direction.z / OLD_HEAD_RADII.z))
    old_radius = 1.0 / scaled.length
    return HEAD_CENTER + direction * (distance * new_head_radius(direction) / old_radius)


def eye_matrix(side):
    flip = Vector((1.0, side, 1.0))
    old_center = OLD_EYE["center"] * flip
    new_center = NEW_EYE["center"] * flip
    scale = Vector(n / o for n, o in zip(NEW_EYE["radii"], OLD_EYE["radii"]))
    return (Matrix.Translation(new_center) @ Matrix.Diagonal((*scale, 1.0))
            @ Matrix.Translation(-old_center))


def world_center(obj):
    if obj.type == "MESH" and obj.data.vertices:
        points = [obj.matrix_world @ v.co for v in obj.data.vertices]
    elif obj.type == "CURVE":
        points = [obj.matrix_world @ pt.co.to_3d() for sp in obj.data.splines for pt in sp.points]
    else:
        points = [obj.matrix_world.translation]
    return sum(points, Vector()) / len(points)


def project_to_head(p):
    direction = (p - HEAD_CENTER).normalized()
    return HEAD_CENTER + direction * new_head_radius(direction)


def relax_face(face, iterations=40, strength=0.5):
    """Even out the vertex spacing on the new face, keeping its shape.

    Pulling every point straight toward the center onto a flatter face crowds
    vertices in the middle and spreads them at the edges and around the facial
    recess, which smears the cuticle texture (it rides on the vertices). Here
    each front vertex slides toward the average of its neighbours and is
    snapped back onto the head surface, so the surface stays put while the
    texture spreads evenly. The v1 mesh is a UV sphere with poles at top and
    bottom, so the face lies in its regular quad band; the poles stay fixed.
    """
    neighbours = [[] for _ in face.data.vertices]
    for edge in face.data.edges:
        a, b = edge.vertices
        neighbours[a].append(b)
        neighbours[b].append(a)
    points = [face.matrix_world @ v.co for v in face.data.vertices]
    weights = []
    for point in points:
        q = point - HEAD_CENTER
        weights.append(strength * smoothstep(0.12, -0.08, q.x) * (1.0 - smoothstep(0.28, 0.38, abs(q.z))))
    for _ in range(iterations):
        updated = list(points)
        for i, point in enumerate(points):
            if weights[i] <= 0.0 or not neighbours[i]:
                continue
            average = sum((points[j] for j in neighbours[i]), Vector()) / len(neighbours[i])
            updated[i] = project_to_head(point + (average - point) * weights[i])
        points = updated
    inverse = face.matrix_world.inverted()
    for vertex, point in zip(face.data.vertices, points):
        vertex.co = inverse @ point


def even_head_grain():
    """Repeat the head's cuticle maps twice around the head.

    The head is a UV sphere wrapped in one square image: 360 degrees across,
    180 down, so every grain of the cuticle is twice as wide as it is tall. On
    v1's round face that hid in the curvature; on the flat v2 face under
    grazing light the bump map read as horizontal wrinkles. The maps are
    generic noise that tiles left to right, so doubling them across restores
    round grains without a seam. Maps that do not tile are left alone.
    """
    for name in ("head_microheight", "head_color", "head_roughness"):
        image = bpy.data.images[name]
        width, height = image.size
        pixels = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        pixels = pixels.reshape((height, width, 4))
        neighbour = np.abs(np.diff(pixels[:, :, :3], axis=1)).mean()
        wrap = np.abs(pixels[:, 0, :3] - pixels[:, -1, :3]).mean()
        if wrap > 2.0 * neighbour:
            print("GRAIN %s does not tile; left as is" % name)
            continue
        columns = np.arange(width) * 2
        doubled = 0.5 * (pixels[:, columns % width] + pixels[:, (columns + 1) % width])
        image.pixels.foreach_set(doubled.ravel())
        image.pack()
        print("GRAIN %s doubled" % name)


def reshape_head():
    face = bpy.data.objects["03 head | face"]
    inverse = face.matrix_world.inverted()
    for vertex in face.data.vertices:
        vertex.co = inverse @ warp_head_point(face.matrix_world @ vertex.co)
    relax_face(face)
    even_head_grain()
    for side in (-1, 1):
        matrix = eye_matrix(side)
        for stem in ("base", "individual ommatidia", "interommatidial microbristles"):
            obj = bpy.data.objects["eye | %d %s" % (side, stem)]
            obj.matrix_world = matrix @ obj.matrix_world
    # Small parts move rigidly with the head surface under them.
    moved = {}
    for name in ("ocellus", "ocellus.001", "ocellus.002", "antenna pedicel", "antenna pedicel.001",
                 "antenna flagellum", "antenna flagellum.001"):
        obj = bpy.data.objects[name]
        center = world_center(obj)
        delta = warp_head_point(center) - center
        if name.startswith("antenna"):
            delta.y -= ANTENNA_INSET * (1.0 if center.y > 0.0 else -1.0)
        obj.matrix_world = Matrix.Translation(delta) @ obj.matrix_world
        moved[name] = delta
    # The mouth opens on the underside of the head: shift the proboscis and
    # labella back under the new, shorter face (palps and clypeus are built
    # there by rebuild_face).
    for name in ("proboscis", "mouth | paired labella", "mouth | paired labella.001"):
        obj = bpy.data.objects[name]
        obj.matrix_world = Matrix.Translation(MOUTH_SHIFT) @ obj.matrix_world
        moved[name] = MOUTH_SHIFT
    # Each arista rides on its antenna's third segment (side -1 has no suffix).
    for arista_suffix, antenna in (("", "antenna flagellum"), (".001", "antenna flagellum.001")):
        for stem in ("arista shaft", "arista branches"):
            obj = bpy.data.objects[stem + arista_suffix]
            obj.matrix_world = Matrix.Translation(moved[antenna]) @ obj.matrix_world
    # Facial bristles follow the surface point by point.
    hairs = bpy.data.objects["head | facial microsetae"]
    inverse = hairs.matrix_world.inverted()
    for spline in hairs.data.splines:
        for point in spline.points:
            world = hairs.matrix_world @ point.co.to_3d()
            point.co = (*(inverse @ warp_head_point(world)), point.co.w)
    return moved


removed = remove_v1_legs()
ensure_pad_material()
rebuild_face()
matte_eyes()
head_moves = reshape_head()
slim_neck()
for leg_index in LEGS:
    for leg_side in (-1, 1):
        build_leg(leg_index, leg_side)
bpy.ops.wm.save_as_mainfile(filepath=str(DEST), compress=True)
print("REFINED removed=%d saved=%s" % (removed, DEST))
print("HEAD proboscis moved by", tuple(round(v, 3) for v in head_moves["proboscis"]))
