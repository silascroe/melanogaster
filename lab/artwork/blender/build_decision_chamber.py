"""Build the FlyTest Decision Chamber diorama and export its fly as GLB.

Run from the repository root with:
    tools/blender/blender-5.2.2-windows-x64/blender.exe --background --python artwork/blender/build_decision_chamber.py

The scene is a visual study, not a biologically calibrated model. Geometry and
materials are generated procedurally so the .blend has no external assets.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[2]
BLEND_PATH = ROOT / "artwork" / "blender" / "decision_chamber.blend"
GLB_PATH = ROOT / "arena3d" / "assets" / "decision_chamber_fly.glb"
RENDER_PATH = ROOT / "outputs" / "blender" / "decision-chamber" / "decision_chamber.png"

COLLECTIONS: dict[str, bpy.types.Collection] = {}
FLY_ROOT: bpy.types.Object | None = None
FLY_OBJECTS: list[bpy.types.Object] = []


def collection(name: str) -> bpy.types.Collection:
    existing = COLLECTIONS.get(name)
    if existing is not None:
        return existing
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    COLLECTIONS[name] = result
    return result


def link_object(
    obj: bpy.types.Object,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    export_with_fly: bool = False,
) -> bpy.types.Object:
    for previous in list(obj.users_collection):
        if previous != target:
            previous.objects.unlink(obj)
    if target not in obj.users_collection:
        target.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    if export_with_fly:
        FLY_OBJECTS.append(obj)
    return obj


def set_socket(node: bpy.types.Node, names: tuple[str, ...], value: object) -> None:
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.4,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
    alpha: float = 1.0,
    transmission: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    if shader is None:
        raise RuntimeError(f"Principled BSDF missing for {name}")
    set_socket(shader, ("Base Color",), color)
    set_socket(shader, ("Metallic",), metallic)
    set_socket(shader, ("Roughness",), roughness)
    set_socket(shader, ("Alpha",), alpha)
    set_socket(shader, ("Transmission Weight", "Transmission"), transmission)
    if emission is not None:
        set_socket(shader, ("Emission Color", "Emission"), emission)
        set_socket(shader, ("Emission Strength",), emission_strength)
    return mat


def assign(obj: bpy.types.Object, mat: bpy.types.Material) -> bpy.types.Object:
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def smooth(obj: bpy.types.Object) -> bpy.types.Object:
    if obj.type == "MESH":
        for face in obj.data.polygons:
            face.use_smooth = True
    return obj


def add_sphere(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    *,
    parent: bpy.types.Object | None = None,
    segments: int = 32,
    rings: int = 20,
    export_with_fly: bool = False,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, radius=1.0, location=location
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    smooth(obj)
    assign(obj, mat)
    return link_object(obj, target, parent, export_with_fly)


def add_cube(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    *,
    bevel: float = 0.0,
    rotation_z: float = 0.0,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    obj.rotation_euler.z = rotation_z
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0.0:
        mod = obj.modifiers.new("Machined edge highlights", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        mod.limit_method = "ANGLE"
        obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
    assign(obj, mat)
    return link_object(obj, target, parent)


def add_cylinder(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    *,
    vertices: int = 64,
    bevel: float = 0.0,
    rotation_z: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=location
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler.z = rotation_z
    smooth(obj)
    if bevel > 0.0:
        mod = obj.modifiers.new("Soft machined rim", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
    assign(obj, mat)
    return link_object(obj, target)


def add_rod(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius_start: float,
    radius_end: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    *,
    parent: bpy.types.Object | None = None,
    vertices: int = 12,
    export_with_fly: bool = False,
) -> bpy.types.Object:
    a = Vector(start)
    b = Vector(end)
    direction = b - a
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius_start,
        radius2=radius_end,
        depth=direction.length,
        location=(a + b) * 0.5,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    smooth(obj)
    assign(obj, mat)
    return link_object(obj, target, parent, export_with_fly)


def add_curve(
    name: str,
    points: list[tuple[float, float, float]],
    radius: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    *,
    parent: bpy.types.Object | None = None,
    cyclic: bool = False,
    export_with_fly: bool = False,
) -> bpy.types.Object:
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 16
    data.bevel_depth = radius
    data.bevel_resolution = 3
    spline = data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, coordinate in zip(spline.points, points):
        point.co = (*coordinate, 1.0)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, data)
    target.objects.link(obj)
    assign(obj, mat)
    if parent is not None:
        obj.parent = parent
    if export_with_fly:
        FLY_OBJECTS.append(obj)
    return obj


def add_torus(
    name: str,
    major_radius: float,
    minor_radius: float,
    location: tuple[float, float, float],
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    *,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    parent: bpy.types.Object | None = None,
    export_with_fly: bool = False,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_segments=72,
        minor_segments=12,
        major_radius=major_radius,
        minor_radius=minor_radius,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    smooth(obj)
    assign(obj, mat)
    return link_object(obj, target, parent, export_with_fly)


def add_text(
    name: str,
    body: str,
    location: tuple[float, float, float],
    size: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    *,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    align_x: str = "CENTER",
) -> bpy.types.Object:
    data = bpy.data.curves.new(name, "FONT")
    data.body = body
    data.size = size
    data.align_x = align_x
    data.align_y = "CENTER"
    data.extrude = 0.001
    data.bevel_depth = 0.0005
    obj = bpy.data.objects.new(name, data)
    target.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    obj.data.materials.append(mat)
    return obj


def point_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area_light(
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    power: float,
    color: tuple[float, float, float],
    size: float,
    light_shape: str = "DISK",
) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.color = color
    data.shape = light_shape
    data.size = size
    obj = bpy.data.objects.new(name, data)
    collection("03 | Camera and lighting").objects.link(obj)
    obj.location = location
    point_at(obj, target)
    return obj


def create_wing(side: int, wing_mat: bpy.types.Material, vein_mat: bpy.types.Material) -> None:
    rows = 28
    columns = 8
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []

    def center(t: float) -> Vector:
        return Vector((-0.08 - 0.38 * t, side * (0.19 + 0.94 * t), 0.17 + 0.25 * t))

    def width(t: float) -> float:
        return 0.255 * max(0.0, math.sin(math.pi * t)) ** 0.72

    def wing_point(t: float, across: float) -> tuple[float, float, float]:
        spine = center(t)
        half_width = width(t)
        x = spine.x + across * half_width * 0.86
        y = spine.y - side * across * half_width * 0.50
        z = spine.z + 0.035 * (1.0 - across * across) * math.sin(math.pi * t)
        return (x, y, z)

    for row in range(rows + 1):
        t = row / rows
        for column in range(columns + 1):
            across = -1.0 + 2.0 * column / columns
            vertices.append(wing_point(t, across))
    for row in range(rows):
        for column in range(columns):
            a = row * (columns + 1) + column
            b = a + columns + 1
            faces.append((a, a + 1, b + 1, b))

    mesh = bpy.data.meshes.new(f"Wing membrane mesh {side:+d}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    wing = bpy.data.objects.new(f"Fly | translucent veined wing {side:+d}", mesh)
    collection("01 | Fly asset").objects.link(wing)
    smooth(wing)
    assign(wing, wing_mat)
    link_object(wing, collection("01 | Fly asset"), FLY_ROOT, True)

    # Leading, trailing and radial veins are deliberately fine, not wire-frame.
    for edge, label in ((-0.78, "trailing"), (0.78, "leading")):
        edge_points = [wing_point(i / 32, edge) for i in range(1, 32)]
        add_curve(
            f"Fly | {label} wing vein {side:+d}",
            edge_points,
            0.006,
            vein_mat,
            collection("01 | Fly asset"),
            parent=FLY_ROOT,
            export_with_fly=True,
        )
    add_curve(
        f"Fly | radial wing vein {side:+d}",
        [wing_point(i / 24, 0.0) for i in range(1, 24)],
        0.007,
        vein_mat,
        collection("01 | Fly asset"),
        parent=FLY_ROOT,
        export_with_fly=True,
    )
    for t in (0.26, 0.43, 0.59, 0.73, 0.84):
        add_curve(
            f"Fly | cross vein {side:+d} {t:.2f}",
            [wing_point(t + delta, across) for delta, across in ((-0.055, -0.72), (-0.02, -0.15), (0.02, 0.38), (0.055, 0.72))],
            0.0038,
            vein_mat,
            collection("01 | Fly asset"),
            parent=FLY_ROOT,
            export_with_fly=True,
        )


def create_fly() -> bpy.types.Object:
    global FLY_ROOT
    fly_coll = collection("01 | Fly asset")
    FLY_ROOT = bpy.data.objects.new("Fly | reusable asset root", None)
    fly_coll.objects.link(FLY_ROOT)
    FLY_ROOT.empty_display_type = "SPHERE"
    FLY_ROOT.empty_display_size = 0.12
    FLY_OBJECTS.append(FLY_ROOT)

    shell = material("Fly | petrol-black chitin", (0.045, 0.105, 0.12, 1), metallic=0.38, roughness=0.25)
    thorax = material("Fly | blue-green thorax", (0.105, 0.31, 0.30, 1), metallic=0.26, roughness=0.28)
    thorax_plate = material("Fly | dorsal shield", (0.28, 0.48, 0.40, 1), metallic=0.22, roughness=0.29)
    abdomen = material("Fly | segmented abdomen", (0.17, 0.22, 0.18, 1), metallic=0.2, roughness=0.31)
    amber = material("Fly | amber abdominal bands", (0.67, 0.34, 0.10, 1), metallic=0.42, roughness=0.27)
    eye = material("Fly | garnet compound eyes", (0.24, 0.035, 0.075, 1), metallic=0.12, roughness=0.18)
    facet = material("Fly | eye facets", (0.075, 0.012, 0.035, 1), metallic=0.18, roughness=0.23)
    glint = material("Fly | eye glints", (0.78, 0.93, 0.86, 1), metallic=0.12, roughness=0.12, emission=(0.28, 0.60, 0.52, 1), emission_strength=0.2)
    leg_mat = material("Fly | articulated limbs", (0.07, 0.14, 0.14, 1), metallic=0.52, roughness=0.29)
    hair_mat = material("Fly | fine setae", (0.43, 0.56, 0.46, 1), metallic=0.28, roughness=0.35)
    wing_mat = material("Fly | smoky translucent wing membrane", (0.18, 0.62, 0.61, 1), metallic=0.06, roughness=0.2, alpha=0.43, transmission=0.35)
    vein_mat = material("Fly | pale cyan wing veins", (0.32, 0.88, 0.78, 1), metallic=0.16, roughness=0.26, emission=(0.04, 0.28, 0.24, 1), emission_strength=0.28)

    add_sphere("Fly | thorax", (0.0, 0.0, 0.0), (0.47, 0.36, 0.34), thorax, fly_coll, parent=FLY_ROOT, export_with_fly=True)
    add_sphere("Fly | dorsal thorax shield", (-0.01, 0.0, 0.245), (0.32, 0.29, 0.095), thorax_plate, fly_coll, parent=FLY_ROOT, export_with_fly=True)
    add_sphere("Fly | head capsule", (0.51, 0.0, 0.07), (0.35, 0.34, 0.31), shell, fly_coll, parent=FLY_ROOT, export_with_fly=True)

    # Four overlapping body segments and thin amber seams give the fly a real
    # tapered abdomen rather than the old single capsule silhouette.
    segment_specs = [
        (-0.30, 0.31, 0.29, -0.015),
        (-0.55, 0.30, 0.265, -0.035),
        (-0.79, 0.27, 0.225, -0.06),
        (-1.00, 0.22, 0.175, -0.075),
        (-1.16, 0.14, 0.12, -0.08),
    ]
    for index, (x, sx, sy, z) in enumerate(segment_specs):
        band_mat = amber if index in (1, 3) else abdomen
        add_sphere(
            f"Fly | abdomen segment {index + 1}",
            (x, 0.0, z),
            (sx, sy, 0.20 if index < 3 else 0.15),
            band_mat,
            fly_coll,
            parent=FLY_ROOT,
            export_with_fly=True,
        )
    add_sphere("Fly | abdominal tip", (-1.30, 0.0, -0.08), (0.12, 0.09, 0.085), shell, fly_coll, parent=FLY_ROOT, export_with_fly=True)

    # Two domed compound eyes, with visible ommatidia on the side facing camera.
    for side in (-1, 1):
        eye_center = (0.53, side * 0.255, 0.115)
        add_sphere(f"Fly | compound eye {side:+d}", eye_center, (0.205, 0.19, 0.24), eye, fly_coll, parent=FLY_ROOT, export_with_fly=True)
        for ix in range(5):
            u = -0.70 + ix * 0.35
            for iz in range(5):
                v = -0.68 + iz * 0.34
                if u * u + v * v > 0.92:
                    continue
                surface_y = side * (0.255 + 0.19 * math.sqrt(max(0.05, 1.0 - u * u - v * v)))
                add_sphere(
                    f"Fly | ommatidium {side:+d} {ix}-{iz}",
                    (0.53 + u * 0.185, surface_y, 0.115 + v * 0.215),
                    (0.027, 0.014, 0.027),
                    facet,
                    fly_coll,
                    parent=FLY_ROOT,
                    segments=10,
                    rings=8,
                    export_with_fly=True,
                )
        add_sphere(f"Fly | eye catchlight {side:+d}", (0.64, side * 0.365, 0.235), (0.035, 0.016, 0.047), glint, fly_coll, parent=FLY_ROOT, segments=16, rings=10, export_with_fly=True)

    # Short proboscis and two arista-bearing antennae.
    mouth_start = (0.76, 0.0, -0.06)
    mouth_tip = (0.91, 0.0, -0.28)
    add_rod("Fly | proboscis", mouth_start, mouth_tip, 0.045, 0.018, amber, fly_coll, parent=FLY_ROOT, export_with_fly=True)
    for side in (-1, 1):
        base = (0.69, side * 0.10, 0.28)
        mid = (0.84, side * 0.18, 0.43)
        tip = (1.04, side * 0.25, 0.47)
        add_rod(f"Fly | antenna {side:+d}", base, mid, 0.026, 0.018, shell, fly_coll, parent=FLY_ROOT, export_with_fly=True)
        add_curve(f"Fly | arista {side:+d}", [mid, (0.91, side * 0.21, 0.48), tip], 0.008, hair_mat, fly_coll, parent=FLY_ROOT, export_with_fly=True)
        for feather_index in range(4):
            t = 0.28 + feather_index * 0.16
            p = Vector(mid).lerp(Vector(tip), t)
            add_curve(
                f"Fly | arista hair {side:+d} {feather_index}",
                [tuple(p), (p.x - 0.045, p.y, p.z + 0.035)],
                0.0035,
                hair_mat,
                fly_coll,
                parent=FLY_ROOT,
                export_with_fly=True,
            )

    # Two veined wings with softly tinted membranes.
    create_wing(-1, wing_mat, vein_mat)
    create_wing(1, wing_mat, vein_mat)

    # Halteres: the small balancing organs behind the wing roots.
    for side in (-1, 1):
        add_rod("Fly | haltere stem", (-0.28, side * 0.23, 0.12), (-0.52, side * 0.42, 0.26), 0.026, 0.018, thorax_plate, fly_coll, parent=FLY_ROOT, export_with_fly=True)
        add_sphere("Fly | haltere knob", (-0.54, side * 0.44, 0.275), (0.075, 0.055, 0.067), amber, fly_coll, parent=FLY_ROOT, segments=16, rings=10, export_with_fly=True)

    # Six jointed legs: femur, tibia and a two-piece foot on every side.
    for side in (-1, 1):
        leg_specs = [
            ("fore", (0.22, side * 0.24, -0.12), (0.38, side * 0.44, -0.26), (0.48, side * 0.55, -0.48), (0.70, side * 0.60, -0.50)),
            ("mid", (0.00, side * 0.29, -0.14), (-0.04, side * 0.55, -0.29), (0.04, side * 0.70, -0.48), (0.25, side * 0.73, -0.50)),
            ("hind", (-0.25, side * 0.23, -0.12), (-0.46, side * 0.43, -0.26), (-0.60, side * 0.58, -0.47), (-0.81, side * 0.61, -0.49)),
        ]
        for label, hip, knee, ankle, toe in leg_specs:
            add_sphere(f"Fly | {label} coxa joint {side:+d}", hip, (0.075, 0.07, 0.075), thorax_plate, fly_coll, parent=FLY_ROOT, segments=14, rings=10, export_with_fly=True)
            add_rod(f"Fly | {label} femur {side:+d}", hip, knee, 0.050, 0.037, leg_mat, fly_coll, parent=FLY_ROOT, export_with_fly=True)
            add_sphere(f"Fly | {label} knee {side:+d}", knee, (0.045, 0.045, 0.045), amber, fly_coll, parent=FLY_ROOT, segments=12, rings=8, export_with_fly=True)
            add_rod(f"Fly | {label} tibia {side:+d}", knee, ankle, 0.034, 0.022, leg_mat, fly_coll, parent=FLY_ROOT, export_with_fly=True)
            add_rod(f"Fly | {label} tarsus {side:+d}", ankle, toe, 0.021, 0.012, thorax_plate, fly_coll, parent=FLY_ROOT, export_with_fly=True)
            toe_tip = (toe[0] + 0.07, toe[1], toe[2] - 0.018)
            add_rod(f"Fly | {label} foot tip {side:+d}", toe, toe_tip, 0.012, 0.006, amber, fly_coll, parent=FLY_ROOT, export_with_fly=True)

    # A few fine thoracic bristles break up the shell highlights without turning
    # the model into a porcupine.
    for index in range(7):
        x = -0.27 + index * 0.075
        add_curve(
            f"Fly | thoracic bristle {index + 1}",
            [(x, -0.05, 0.26), (x + 0.025, -0.08, 0.37), (x + 0.06, -0.10, 0.41)],
            0.0045,
            hair_mat,
            fly_coll,
            parent=FLY_ROOT,
            export_with_fly=True,
        )

    # The visual model is not the simulation collider. Its hovering pose is a
    # compositional choice, not a claim about the controller's physical state.
    FLY_ROOT.location = (-1.20, -0.12, 0.79)
    return FLY_ROOT


def create_stage() -> None:
    stage = collection("02 | Chamber and stimulus")
    steel = material("Stage | graphite ceramic", (0.018, 0.037, 0.052, 1), metallic=0.72, roughness=0.3)
    deck = material("Stage | blue-black glass composite", (0.024, 0.069, 0.088, 1), metallic=0.28, roughness=0.31)
    trim = material("Stage | brushed titanium", (0.11, 0.22, 0.25, 1), metallic=0.82, roughness=0.25)
    dark = material("Stage | inset panels", (0.012, 0.025, 0.034, 1), metallic=0.46, roughness=0.36)
    cyan = material("Stage | ion-cyan light strips", (0.12, 0.84, 0.76, 1), metallic=0.16, roughness=0.24, emission=(0.025, 0.55, 0.48, 1), emission_strength=0.62)
    cyan_dim = material("Stage | etched teal guides", (0.06, 0.31, 0.34, 1), metallic=0.35, roughness=0.34, emission=(0.01, 0.10, 0.12, 1), emission_strength=0.26)
    amber = material("Beacon | warm gold", (1.0, 0.45, 0.08, 1), metallic=0.2, roughness=0.25, emission=(1.0, 0.25, 0.025, 1), emission_strength=2.2)
    amber_dim = material("Beacon | amber guide", (0.71, 0.28, 0.055, 1), metallic=0.25, roughness=0.33, emission=(0.58, 0.12, 0.015, 1), emission_strength=0.34)
    white = material("Stage | cool white lettering", (0.62, 0.85, 0.81, 1), metallic=0.15, roughness=0.3, emission=(0.25, 0.53, 0.47, 1), emission_strength=0.22)

    # Stacked octagonal plinth, with a wide flat top for an easy-to-read model.
    add_cylinder("Chamber | lower octagonal plinth", (0, 0, -0.015), 4.72, 0.56, steel, stage, vertices=8, bevel=0.12, rotation_z=math.radians(22.5))
    add_cylinder("Chamber | upper titanium reveal", (0, 0, 0.245), 4.64, 0.105, trim, stage, vertices=8, bevel=0.035, rotation_z=math.radians(22.5))
    add_cylinder("Chamber | instrument deck", (0, 0, 0.31), 4.53, 0.10, deck, stage, vertices=8, bevel=0.035, rotation_z=math.radians(22.5))
    add_torus("Chamber | perimeter cyan light", 4.38, 0.026, (0, 0, 0.367), cyan, stage)
    add_torus("Chamber | inset titanium ring", 4.12, 0.018, (0, 0, 0.366), trim, stage)

    # Concentric sensing bands and radial etched guides.
    for radius, mat, thickness in ((3.75, cyan_dim, 0.010), (2.90, trim, 0.012), (1.65, cyan_dim, 0.012), (0.62, cyan_dim, 0.010)):
        add_torus(f"Deck | calibration ring {radius:.2f}", radius, thickness, (0, 0, 0.372), mat, stage)
    for angle_deg in range(0, 360, 30):
        angle = math.radians(angle_deg)
        inner = 3.72
        outer = 4.06
        add_curve(
            f"Deck | radial tick {angle_deg:03d}",
            [(inner * math.cos(angle), inner * math.sin(angle), 0.374), (outer * math.cos(angle), outer * math.sin(angle), 0.374)],
            0.008,
            cyan_dim,
            stage,
        )

    # Outer bollards mark the chamber boundary; their light is intentionally
    # cooler and dimmer than the single target beacon.
    for index, angle_deg in enumerate((22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5)):
        angle = math.radians(angle_deg)
        x, y = 4.00 * math.cos(angle), 4.00 * math.sin(angle)
        add_cylinder(f"Boundary | pylon {index + 1}", (x, y, 0.70), 0.105, 0.70, steel, stage, vertices=20, bevel=0.025)
        add_cylinder(f"Boundary | pylon cap {index + 1}", (x, y, 1.075), 0.093, 0.06, cyan, stage, vertices=20, bevel=0.018)
        add_torus(f"Boundary | cap ring {index + 1}", 0.102, 0.012, (x, y, 0.94), cyan_dim, stage)

    # Sensor gate: a simple, readable obstacle between fly and target.
    gate_x = 0.73
    for side in (-1, 1):
        y = side * 0.92
        add_cylinder(f"Gate | upright {side:+d}", (gate_x, y, 0.87), 0.073, 1.03, trim, stage, vertices=24, bevel=0.016)
        add_cylinder(f"Gate | sensor node {side:+d}", (gate_x, y, 1.43), 0.095, 0.09, cyan, stage, vertices=24, bevel=0.025)
    add_rod("Gate | upper crossbar", (gate_x, -0.92, 1.36), (gate_x, 0.92, 1.36), 0.035, 0.035, trim, stage, vertices=16)
    add_curve("Gate | luminous scan line", [(gate_x, -0.88, 0.57), (gate_x, -0.55, 0.62), (gate_x, 0.0, 0.64), (gate_x, 0.55, 0.62), (gate_x, 0.88, 0.57)], 0.013, cyan, stage)
    for y in (-0.62, 0.0, 0.62):
        add_sphere("Gate | scan point", (gate_x, y, 0.64), (0.035, 0.035, 0.035), white, stage, segments=14, rings=10)

    # Target beacon on a circular, amber-lit landing pad.
    beacon_x, beacon_y = 2.45, 0.70
    add_cylinder("Beacon | landing pad", (beacon_x, beacon_y, 0.405), 0.47, 0.09, steel, stage, vertices=64, bevel=0.025)
    add_torus("Beacon | illuminated pad ring", 0.39, 0.022, (beacon_x, beacon_y, 0.46), amber_dim, stage)
    add_cylinder("Beacon | pedestal", (beacon_x, beacon_y, 0.65), 0.145, 0.39, trim, stage, vertices=32, bevel=0.035)
    add_cylinder("Beacon | collar", (beacon_x, beacon_y, 0.83), 0.20, 0.055, amber, stage, vertices=40, bevel=0.015)
    add_sphere("Beacon | luminous target", (beacon_x, beacon_y, 1.13), (0.265, 0.265, 0.265), amber, stage, segments=40, rings=28)
    add_torus("Beacon | floating halo", 0.36, 0.018, (beacon_x, beacon_y, 0.97), amber, stage, rotation=(math.radians(74), math.radians(8), math.radians(12)))
    add_torus("Beacon | lower halo", 0.27, 0.012, (beacon_x, beacon_y, 1.13), amber_dim, stage, rotation=(math.radians(82), 0, math.radians(-18)))

    # A floor-level cue visually links the fly, gate and target without implying
    # that the current controller is following this path.
    add_curve("Deck | approach cue cyan", [(-1.02, -0.12, 0.382), (-0.52, -0.08, 0.382), (0.10, 0.02, 0.382), (0.66, 0.08, 0.382)], 0.014, cyan, stage)
    add_curve("Deck | approach cue amber", [(0.80, 0.10, 0.382), (1.28, 0.22, 0.382), (1.87, 0.48, 0.382), (2.10, 0.63, 0.382)], 0.012, amber_dim, stage)
    for index, x in enumerate((-0.82, -0.40, 0.04, 0.44, 1.06, 1.48, 1.82)):
        dot_mat = cyan if index < 4 else amber_dim
        add_sphere(f"Deck | route marker {index + 1}", (x, -0.08 + 0.2 * (x + 1.0) / 3.0, 0.397), (0.035, 0.035, 0.012), dot_mat, stage, segments=12, rings=8)

    # Captions are physical in-scene labels, not a fake simulator HUD.
    label_plate = add_cube("Chamber | front nameplate", (0.0, -4.37, -0.035), (3.35, 0.12, 0.38), dark, stage, bevel=0.045)
    label_plate.rotation_euler.x = 0
    add_text("Chamber | title lettering", "DECISION CHAMBER", (0.0, -4.438, -0.025), 0.205, white, stage, rotation=(math.radians(90), 0, 0))
    add_text("Chamber | deck identifier", "ARENA 01   /   STIMULUS LUX-01", (0.0, -3.74, 0.378), 0.105, cyan, stage)
    add_text("Beacon | identifier", "LUX-01", (beacon_x, beacon_y - 0.55, 0.384), 0.105, amber, stage)

    # Ground backdrop catches shadows but stays almost black.
    floor_mat = material("Studio | midnight floor", (0.0015, 0.003, 0.006, 1), metallic=0.03, roughness=0.68)
    add_cube("Studio | shadow floor", (0, 0, -0.42), (200, 200, 0.12), floor_mat, stage, bevel=0.0)


def create_lighting_and_camera() -> None:
    lights = collection("03 | Camera and lighting")
    add_area_light("Light | broad cool key", (-4.5, -5.2, 8.8), (0, 0, 0.4), 600, (0.55, 0.80, 0.88), 7.0)
    add_area_light("Light | warm softbox", (4.0, 2.2, 6.2), (0.7, 0.2, 0.6), 350, (1.0, 0.53, 0.27), 5.0)
    add_area_light("Light | cyan rim", (-1.5, 4.2, 5.8), (-0.3, 0.0, 0.8), 500, (0.10, 0.76, 0.72), 4.0)
    add_area_light("Light | fly eye card", (2.8, -3.2, 3.4), (-0.6, -0.1, 0.8), 120, (0.90, 0.72, 0.52), 2.2)

    point_data = bpy.data.lights.new("Light | beacon spill", "POINT")
    point_data.energy = 38
    point_data.color = (1.0, 0.27, 0.045)
    point_data.shadow_soft_size = 0.8
    point_obj = bpy.data.objects.new("Light | beacon spill", point_data)
    lights.objects.link(point_obj)
    point_obj.location = (2.45, 0.70, 1.20)

    camera_data = bpy.data.cameras.new("Camera | hero orthographic")
    camera = bpy.data.objects.new("Camera | hero orthographic", camera_data)
    lights.objects.link(camera)
    camera.location = (8.8, -11.8, 9.3)
    point_at(camera, (0.0, -0.05, 0.47))
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 11.8
    camera_data.lens = 50
    bpy.context.scene.camera = camera


def configure_render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 56
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1680
    scene.render.resolution_y = 1120
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 12
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.render.image_settings.file_format = "PNG"

    world = bpy.data.worlds.new("Decision Chamber | dark studio") if bpy.data.worlds.get("Decision Chamber | dark studio") is None else bpy.data.worlds["Decision Chamber | dark studio"]
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.004, 0.009, 0.015, 1)
        background.inputs["Strength"].default_value = 0.12

    # Blender 5.2 stores the compositor tree directly on the scene instead of
    # exposing the old Scene.node_tree property. Keep the older path as a
    # fallback for Blender releases that still use it.
    if hasattr(scene, "compositing_node_group"):
        node_tree = bpy.data.node_groups.new(
            "Decision Chamber | compositor", "CompositorNodeTree"
        )
        scene.compositing_node_group = node_tree
        node_tree.interface.new_socket(
            name="Image", in_out="OUTPUT", socket_type="NodeSocketColor"
        )
    else:
        scene.use_nodes = True
        node_tree = scene.node_tree

    nodes = node_tree.nodes
    nodes.clear()
    render_layers = nodes.new("CompositorNodeRLayers")
    glow = nodes.new("CompositorNodeGlare")
    if glow.inputs.get("Type") is not None:
        glow.inputs["Type"].default_value = "Fog Glow"
    if glow.inputs.get("Quality") is not None:
        glow.inputs["Quality"].default_value = "High"
    if glow.inputs.get("Threshold") is not None:
        glow.inputs["Threshold"].default_value = 1.25
    if glow.inputs.get("Size") is not None:
        glow.inputs["Size"].default_value = 0.72
    if hasattr(scene, "compositing_node_group"):
        output = nodes.new("NodeGroupOutput")
        node_tree.links.new(output.inputs["Image"], glow.outputs["Image"])
        scene.render.use_compositing = True
    else:
        output = nodes.new("CompositorNodeComposite")
        node_tree.links.new(render_layers.outputs["Image"], glow.inputs["Image"])
        node_tree.links.new(glow.outputs["Image"], output.inputs["Image"])
        scene.render.use_compositing = True
    if hasattr(scene, "compositing_node_group"):
        node_tree.links.new(glow.inputs["Image"], render_layers.outputs["Image"])


def export_fly() -> None:
    if FLY_ROOT is None:
        raise RuntimeError("Fly root was not created")
    root_location = FLY_ROOT.location.copy()
    root_rotation = FLY_ROOT.rotation_euler.copy()
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for obj in FLY_OBJECTS:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = FLY_ROOT

    # The hero render points the fly toward +X. Rotate it to Blender -Y before
    # export so the GLB's head points along Godot +Z after axis conversion.
    FLY_ROOT.location = (0.0, 0.0, 0.0)
    FLY_ROOT.rotation_euler = (0.0, 0.0, math.radians(-90.0))
    bpy.ops.export_scene.gltf(
        filepath=str(GLB_PATH),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_animations=False,
    )
    FLY_ROOT.location = root_location
    FLY_ROOT.rotation_euler = root_rotation
    for obj in FLY_OBJECTS:
        obj.select_set(False)


def build() -> None:
    BLEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    GLB_PATH.parent.mkdir(parents=True, exist_ok=True)
    RENDER_PATH.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    COLLECTIONS.clear()
    FLY_OBJECTS.clear()

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.unit_settings.system = "METRIC"
    scene.render.filepath = str(RENDER_PATH)

    create_stage()
    create_fly()
    create_lighting_and_camera()
    configure_render()
    scene.render.filepath = str(RENDER_PATH)
    scene.camera.data.lens = 50
    bpy.context.view_layer.objects.active = FLY_ROOT

    export_fly()
    save_version = bpy.context.preferences.filepaths.save_version
    bpy.context.preferences.filepaths.save_version = 0
    try:
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    finally:
        bpy.context.preferences.filepaths.save_version = save_version
    bpy.ops.render.render(write_still=True)

    print(f"BLEND={BLEND_PATH}")
    print(f"GLB={GLB_PATH}")
    print(f"RENDER={RENDER_PATH}")
    print(f"FLY_OBJECTS={len(FLY_OBJECTS)}")
    print(f"SCENE_OBJECTS={len(bpy.context.scene.objects)}")


if __name__ == "__main__":
    build()
