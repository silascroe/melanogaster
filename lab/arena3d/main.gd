extends Node3D

## A standalone world prototype for FlyTest.
##
## Godot owns the visible world. The Python Arena owns the persistent
## connectome-backed controller. Every tick crosses that boundary explicitly.

const WORLD_BOUNDS := Rect2(-4.0, -5.0, 14.0, 13.0)
const TAU_F := 6.283185307179586
const LIVE_STEP_INTERVAL_SECONDS := 0.045

var fly_root: Node3D
var body_cast: ShapeCast3D
var wing_instances: Array[MeshInstance3D] = []
var wing_base_rotations: Array[Vector3] = []
var fly_visual_time := 0.0
var beacon_root: Node3D
var threat_root: Node3D
var obstacle_root: Node3D
var threat_core: MeshInstance3D
var escape_ring: MeshInstance3D
var collision_ring: MeshInstance3D
var camera: Camera3D
var trail_instance: MeshInstance3D
var trail_mesh: ImmediateMesh
var retina_cells: Array[ColorRect] = []
var status_label: Label
var sensor_label: Label
var trace_label: Label
var help_label: Label
var bridge: ArenaBridge

var fly_position := Vector2(0.0, 0.0)
var fly_heading := 0.0
var beacon_position := Vector2(7.0, 4.0)
var threat_position := Vector2(2.0, 1.5)
var live_lights: Array = []
var live_threats: Array = []
var live_obstacles: Array = []
var threat_visible := false
var python_collision_ids: Array = []
var godot_contact_count := 0
var current_world_cause: Dictionary = {}
var current_neural_cause: Dictionary = {}
var sim_time := 0.0
var paused := false
var action_name := "forward"
var action_source := "none"
var action_reason := ""
var active_spike_count := 0
var trail_points := PackedVector3Array()
var session_id := ""
var session_is_ready := false
var step_pending := false
var step_accumulator := 0.0
var replay_status := "CONNECTING TO PYTHON ARENA"

var camera_yaw := 2.35
var camera_pitch := 0.72
var camera_distance := 11.2
var orbiting := false

var palette := {
	"ink": Color("#dce9e4"),
	"muted": Color("#91a39f"),
	"teal": Color("#42d0b1"),
	"blue": Color("#71b8ff"),
	"amber": Color("#f0b84b"),
	"red": Color("#ff6f72"),
	"ground": Color("#0b1b24"),
	"grid": Color("#10252c"),
	"grid_major": Color("#1b3b42"),
	"boundary": Color("#35635e"),
}


func _ready() -> void:
	_setup_environment()
	_build_world()
	_build_fly()
	_build_stimuli()
	_build_camera()
	_build_hud()
	_build_bridge()
	_reset_live_view()
	_request_session()


func _process(delta: float) -> void:
	if not paused and session_is_ready and not step_pending:
		step_accumulator += delta
		if step_accumulator >= LIVE_STEP_INTERVAL_SECONDS:
			step_accumulator = 0.0
			_request_live_step()
	_update_fly_animation(delta)
	_update_camera()
	_update_hud()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			paused = not paused
		elif event.keycode == KEY_R:
			_request_session()
		elif event.keycode == KEY_ESCAPE:
			get_viewport().set_input_as_handled()
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_RIGHT:
			orbiting = event.pressed
		elif event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera_distance = max(5.0, camera_distance - 0.8)
		elif event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera_distance = min(24.0, camera_distance + 0.8)
	if event is InputEventMouseMotion and orbiting:
		camera_yaw -= event.relative.x * 0.008
		camera_pitch = clamp(camera_pitch - event.relative.y * 0.006, 0.25, 1.25)


func _setup_environment() -> void:
	var world_environment := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("#07131b")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("#90aeb6")
	environment.ambient_light_energy = 0.62
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	world_environment.environment = environment
	add_child(world_environment)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-54.0, -32.0, 0.0)
	sun.light_color = Color("#d6e7e4")
	sun.light_energy = 0.8
	sun.shadow_enabled = true
	add_child(sun)


func _build_world() -> void:
	var floor := MeshInstance3D.new()
	var floor_mesh := PlaneMesh.new()
	floor_mesh.size = WORLD_BOUNDS.size
	floor.mesh = floor_mesh
	floor.position = Vector3(WORLD_BOUNDS.position.x + WORLD_BOUNDS.size.x / 2.0, -0.08, WORLD_BOUNDS.position.y + WORLD_BOUNDS.size.y / 2.0)
	floor.material_override = _material(palette["ground"])
	add_child(floor)

	_build_world_grid()
	_build_boundary_visuals()
	_build_boundary_colliders()


func _build_world_grid() -> void:
	var minor_grid_mesh := ImmediateMesh.new()
	minor_grid_mesh.surface_begin(Mesh.PRIMITIVE_LINES, _material(palette["grid"]))
	var major_grid_mesh := ImmediateMesh.new()
	major_grid_mesh.surface_begin(Mesh.PRIMITIVE_LINES, _material(palette["grid_major"]))
	for x in range(int(WORLD_BOUNDS.position.x), int(WORLD_BOUNDS.end.x) + 1):
		var target_mesh := major_grid_mesh if x % 4 == 0 else minor_grid_mesh
		var grid_height := -0.035 if x % 4 == 0 else -0.04
		target_mesh.surface_add_vertex(Vector3(x, grid_height, WORLD_BOUNDS.position.y))
		target_mesh.surface_add_vertex(Vector3(x, grid_height, WORLD_BOUNDS.end.y))
	for z in range(int(WORLD_BOUNDS.position.y), int(WORLD_BOUNDS.end.y) + 1):
		var target_mesh := major_grid_mesh if z % 4 == 0 else minor_grid_mesh
		var grid_height := -0.035 if z % 4 == 0 else -0.04
		target_mesh.surface_add_vertex(Vector3(WORLD_BOUNDS.position.x, grid_height, z))
		target_mesh.surface_add_vertex(Vector3(WORLD_BOUNDS.end.x, grid_height, z))
	minor_grid_mesh.surface_end()
	major_grid_mesh.surface_end()

	for grid_mesh in [minor_grid_mesh, major_grid_mesh]:
		var grid := MeshInstance3D.new()
		grid.mesh = grid_mesh
		grid.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(grid)


func _build_boundary_visuals() -> void:
	# These floor rails and markers are decoration only. The authoritative toy
	# collision boundary remains the StaticBody3D geometry built below.
	var inset := 0.24
	var min_x := WORLD_BOUNDS.position.x + inset
	var max_x := WORLD_BOUNDS.end.x - inset
	var min_z := WORLD_BOUNDS.position.y + inset
	var max_z := WORLD_BOUNDS.end.y - inset
	var rail_material := _material(palette["boundary"])
	var rail_specs := [
		{"size": Vector3(max_x - min_x, 0.035, 0.045), "position": Vector3((min_x + max_x) * 0.5, -0.038, min_z)},
		{"size": Vector3(max_x - min_x, 0.035, 0.045), "position": Vector3((min_x + max_x) * 0.5, -0.038, max_z)},
		{"size": Vector3(0.045, 0.035, max_z - min_z), "position": Vector3(min_x, -0.038, (min_z + max_z) * 0.5)},
		{"size": Vector3(0.045, 0.035, max_z - min_z), "position": Vector3(max_x, -0.038, (min_z + max_z) * 0.5)},
	]
	for rail_spec in rail_specs:
		var rail := MeshInstance3D.new()
		var rail_mesh := BoxMesh.new()
		rail_mesh.size = rail_spec["size"]
		rail.mesh = rail_mesh
		rail.position = rail_spec["position"]
		rail.material_override = rail_material
		rail.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(rail)

	var pylon_material := _material(Color("#20383e"))
	var pylon_accent := _material(Color("#2f876f"))
	pylon_accent.emission_enabled = true
	pylon_accent.emission = Color("#205b4d")
	pylon_accent.emission_energy_multiplier = 0.75
	for point in [Vector2(min_x, min_z), Vector2(max_x, min_z), Vector2(max_x, max_z), Vector2(min_x, max_z)]:
		var pylon := Node3D.new()
		pylon.position = Vector3(point.x, 0.0, point.y)
		var shaft := MeshInstance3D.new()
		var shaft_mesh := CylinderMesh.new()
		shaft_mesh.top_radius = 0.10
		shaft_mesh.bottom_radius = 0.16
		shaft_mesh.height = 0.48
		shaft_mesh.radial_segments = 12
		shaft.mesh = shaft_mesh
		shaft.position.y = 0.24
		shaft.material_override = pylon_material
		shaft.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		pylon.add_child(shaft)
		var cap := MeshInstance3D.new()
		var cap_mesh := CylinderMesh.new()
		cap_mesh.top_radius = 0.085
		cap_mesh.bottom_radius = 0.085
		cap_mesh.height = 0.035
		cap_mesh.radial_segments = 12
		cap.mesh = cap_mesh
		cap.position.y = 0.50
		cap.material_override = pylon_accent
		cap.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		pylon.add_child(cap)
		add_child(pylon)


func _build_boundary_colliders() -> void:
	var thickness := 0.22
	var height := 1.1
	var walls := [
		{"center": Vector2(WORLD_BOUNDS.position.x, WORLD_BOUNDS.position.y + WORLD_BOUNDS.size.y / 2.0), "size": Vector2(thickness, WORLD_BOUNDS.size.y + thickness * 2.0)},
		{"center": Vector2(WORLD_BOUNDS.end.x, WORLD_BOUNDS.position.y + WORLD_BOUNDS.size.y / 2.0), "size": Vector2(thickness, WORLD_BOUNDS.size.y + thickness * 2.0)},
		{"center": Vector2(WORLD_BOUNDS.position.x + WORLD_BOUNDS.size.x / 2.0, WORLD_BOUNDS.position.y), "size": Vector2(WORLD_BOUNDS.size.x + thickness * 2.0, thickness)},
		{"center": Vector2(WORLD_BOUNDS.position.x + WORLD_BOUNDS.size.x / 2.0, WORLD_BOUNDS.end.y), "size": Vector2(WORLD_BOUNDS.size.x + thickness * 2.0, thickness)},
	]
	for index in range(walls.size()):
		var wall: Dictionary = walls[index]
		var body := StaticBody3D.new()
		body.name = "BoundaryWall_%d" % index
		var center: Vector2 = wall["center"]
		var wall_size: Vector2 = wall["size"]
		body.position = _world_position(center, height / 2.0)
		body.collision_layer = 1
		var collision := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = Vector3(wall_size.x, height, wall_size.y)
		collision.shape = shape
		body.add_child(collision)
		add_child(body)


func _build_fly() -> void:
	fly_root = Node3D.new()
	fly_root.name = "Fly"
	add_child(fly_root)

	body_cast = ShapeCast3D.new()
	body_cast.name = "BodyCollisionCast"
	var body_shape := SphereShape3D.new()
	body_shape.radius = 0.35
	body_cast.shape = body_shape
	body_cast.position = Vector3(0.0, 0.42, 0.0)
	body_cast.collision_mask = 1
	body_cast.enabled = true
	fly_root.add_child(body_cast)

	# The visible fly is deliberately separate from the spherical collision body.
	# It is a stylized low-poly shell: clear insect proportions matter more here
	# than anatomical detail or extra physics surfaces.
	var abdomen := _capsule(Color("#263840"), 0.32, 1.35, Vector3(0.0, 0.43, -0.2), Vector3(0.92, 0.86, 1.0))
	fly_root.add_child(abdomen)
	var abdomen_band_material := _material(Color("#617873"))
	for band_z in [-0.61, -0.31, -0.01]:
		var band := _torus(Color("#617873"), 0.275, 0.31, Vector3(0.0, 0.43, band_z), Vector3(0.92, 0.82, 1.0))
		band.material_override = abdomen_band_material
		fly_root.add_child(band)
	var thorax := _sphere(Color("#4c6b68"), 0.37, Vector3(0.0, 0.49, 0.35), Vector3(1.08, 0.9, 1.04))
	fly_root.add_child(thorax)
	var thorax_plate := _sphere(Color("#78928b"), 0.20, Vector3(0.0, 0.69, 0.35), Vector3(1.15, 0.18, 0.88))
	fly_root.add_child(thorax_plate)
	var head := _sphere(Color("#1d2b31"), 0.30, Vector3(0.0, 0.51, 0.88), Vector3(0.96, 0.92, 0.88))
	fly_root.add_child(head)

	for side in [-1.0, 1.0]:
		var eye := _sphere(Color("#6f283b"), 0.17, Vector3(side * 0.21, 0.56, 1.02), Vector3(0.9, 0.92, 0.68), true)
		fly_root.add_child(eye)
		var eye_glint := _sphere(Color("#d5fff0"), 0.035, Vector3(side * 0.25, 0.64, 1.13), Vector3.ONE, true)
		fly_root.add_child(eye_glint)

		var wing := _sphere(Color(0.42, 0.82, 0.84, 0.34), 0.42, Vector3(side * 0.49, 0.75, 0.18), Vector3(1.22, 0.055, 2.05))
		wing.rotation = Vector3(deg_to_rad(-9.0), deg_to_rad(side * 10.0), deg_to_rad(side * 7.0))
		wing.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		fly_root.add_child(wing)
		wing_instances.append(wing)
		wing_base_rotations.append(wing.rotation)

		var wing_root := _sphere(Color(0.67, 0.95, 0.91, 0.22), 0.22, Vector3(side * 0.37, 0.72, 0.35), Vector3(1.0, 0.045, 1.15))
		wing_root.rotation = Vector3(deg_to_rad(-6.0), deg_to_rad(side * 8.0), deg_to_rad(side * 5.0))
		wing_root.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		fly_root.add_child(wing_root)

		var front_leg_joint := Vector3(side * 0.22, 0.37, 0.56)
		var front_leg_knee := Vector3(side * 0.52, 0.16, 0.78)
		var front_leg_foot := Vector3(side * 0.72, 0.07, 0.98)
		_add_leg(front_leg_joint, front_leg_knee, front_leg_foot)
		var mid_leg_joint := Vector3(side * 0.27, 0.34, 0.22)
		var mid_leg_knee := Vector3(side * 0.62, 0.14, 0.16)
		var mid_leg_foot := Vector3(side * 0.85, 0.06, 0.02)
		_add_leg(mid_leg_joint, mid_leg_knee, mid_leg_foot)
		var rear_leg_joint := Vector3(side * 0.22, 0.34, -0.20)
		var rear_leg_knee := Vector3(side * 0.56, 0.14, -0.43)
		var rear_leg_foot := Vector3(side * 0.75, 0.06, -0.68)
		_add_leg(rear_leg_joint, rear_leg_knee, rear_leg_foot)

		var antenna_base := Vector3(side * 0.12, 0.65, 1.10)
		var antenna_mid := Vector3(side * 0.20, 0.80, 1.34)
		var antenna_tip := Vector3(side * 0.28, 0.85, 1.52)
		fly_root.add_child(_cylinder_between(Color("#91a39f"), 0.018, antenna_base, antenna_mid))
		fly_root.add_child(_cylinder_between(Color("#91a39f"), 0.014, antenna_mid, antenna_tip))
		fly_root.add_child(_sphere(Color("#f0b84b"), 0.025, antenna_tip, Vector3.ONE, true))

	var nose := _sphere(palette["amber"], 0.045, Vector3(0.0, 0.49, 1.36), Vector3.ONE, true)
	fly_root.add_child(nose)

	trail_mesh = ImmediateMesh.new()
	trail_instance = MeshInstance3D.new()
	trail_instance.mesh = trail_mesh
	trail_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(trail_instance)

	var ring_mesh := TorusMesh.new()
	ring_mesh.inner_radius = 0.52
	ring_mesh.outer_radius = 0.6
	ring_mesh.rings = 24
	ring_mesh.ring_segments = 10
	escape_ring = MeshInstance3D.new()
	escape_ring.mesh = ring_mesh
	escape_ring.position = Vector3(0.0, 0.06, 0.0)
	escape_ring.material_override = _material(palette["red"], true)
	escape_ring.visible = false
	fly_root.add_child(escape_ring)

	var collision_mesh := TorusMesh.new()
	collision_mesh.inner_radius = 0.66
	collision_mesh.outer_radius = 0.73
	collision_mesh.rings = 24
	collision_mesh.ring_segments = 10
	collision_ring = MeshInstance3D.new()
	collision_ring.mesh = collision_mesh
	collision_ring.position = Vector3(0.0, 0.08, 0.0)
	collision_ring.material_override = _material(palette["amber"], true)
	collision_ring.visible = false
	fly_root.add_child(collision_ring)


func _add_leg(joint: Vector3, knee: Vector3, foot: Vector3) -> void:
	var leg_material := _material(Color("#78928b"))
	var upper := _cylinder_between(Color("#78928b"), 0.035, joint, knee)
	upper.material_override = leg_material
	fly_root.add_child(upper)
	var lower := _cylinder_between(Color("#526a67"), 0.025, knee, foot)
	lower.material_override = leg_material
	fly_root.add_child(lower)
	fly_root.add_child(_sphere(Color("#a5bdb4"), 0.045, knee, Vector3.ONE))


func _update_fly_animation(delta: float) -> void:
	fly_visual_time += delta
	for index in range(wing_instances.size()):
		var wing := wing_instances[index]
		var flap := sin(fly_visual_time * 13.0 + float(index) * PI) * 0.10
		if action_name == "stop":
			flap *= 0.28
		wing.rotation = wing_base_rotations[index] + Vector3(flap, 0.0, 0.0)


func _cylinder_between(color: Color, radius: float, from_point: Vector3, to_point: Vector3, emission: bool = false) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius * 0.82
	mesh.bottom_radius = radius
	mesh.height = from_point.distance_to(to_point)
	mesh.radial_segments = 8
	mesh.rings = 2
	instance.mesh = mesh
	instance.position = (from_point + to_point) * 0.5
	instance.quaternion = Quaternion(Vector3.UP, (to_point - from_point).normalized())
	instance.material_override = _material(color, emission)
	return instance


func _capsule(color: Color, radius: float, height: float, position: Vector3, scale: Vector3, emission: bool = false) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	var mesh := CapsuleMesh.new()
	mesh.radius = radius
	mesh.height = height
	mesh.radial_segments = 16
	mesh.rings = 6
	instance.mesh = mesh
	instance.position = position
	instance.rotation_degrees = Vector3(90.0, 0.0, 0.0)
	instance.scale = scale
	instance.material_override = _material(color, emission)
	return instance


func _torus(color: Color, inner_radius: float, outer_radius: float, position: Vector3, scale: Vector3, emission: bool = false) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	var mesh := TorusMesh.new()
	mesh.inner_radius = inner_radius
	mesh.outer_radius = outer_radius
	mesh.rings = 20
	mesh.ring_segments = 8
	instance.mesh = mesh
	instance.position = position
	instance.scale = scale
	instance.material_override = _material(color, emission)
	return instance


func _build_stimuli() -> void:
	beacon_root = Node3D.new()
	beacon_root.name = "Beacon"
	beacon_root.position = _world_position(beacon_position, 0.5)
	add_child(beacon_root)
	var beacon_pedestal := MeshInstance3D.new()
	var pedestal_mesh := CylinderMesh.new()
	pedestal_mesh.top_radius = 0.12
	pedestal_mesh.bottom_radius = 0.16
	pedestal_mesh.height = 0.24
	pedestal_mesh.radial_segments = 12
	beacon_pedestal.mesh = pedestal_mesh
	beacon_pedestal.position.y = -0.22
	beacon_pedestal.material_override = _material(Color("#273a3e"))
	beacon_pedestal.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	beacon_root.add_child(beacon_pedestal)
	var beacon_halo := _torus(Color("#96723a"), 0.38, 0.42, Vector3(0.0, -0.53, 0.0), Vector3.ONE)
	beacon_halo.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	beacon_root.add_child(beacon_halo)
	var beacon_material := _material(palette["amber"], true)
	beacon_material.emission_energy_multiplier = 0.7
	var beacon_mesh := _sphere(palette["amber"], 0.34, Vector3.ZERO, Vector3.ONE)
	beacon_mesh.material_override = beacon_material
	beacon_root.add_child(beacon_mesh)
	var beacon_light := OmniLight3D.new()
	beacon_light.light_color = palette["amber"]
	beacon_light.light_energy = 1.4
	beacon_light.omni_range = 4.5
	beacon_root.add_child(beacon_light)

	threat_root = Node3D.new()
	threat_root.name = "Threat"
	threat_root.position = _world_position(threat_position, 0.85)
	add_child(threat_root)
	var threat_mesh := _sphere(Color(0.95, 0.17, 0.27, 0.28), 1.0, Vector3.ZERO, Vector3.ONE)
	threat_root.add_child(threat_mesh)
	threat_core = _sphere(palette["red"], 0.12, Vector3.ZERO, Vector3.ONE, true)
	threat_root.add_child(threat_core)
	var threat_light := OmniLight3D.new()
	threat_light.light_color = palette["red"]
	threat_light.light_energy = 2.4
	threat_light.omni_range = 3.0
	threat_root.add_child(threat_light)

	obstacle_root = Node3D.new()
	obstacle_root.name = "Obstacles"
	add_child(obstacle_root)


func _render_obstacles(obstacles: Array) -> void:
	if not is_instance_valid(obstacle_root):
		return
	for child in obstacle_root.get_children():
		child.queue_free()
	for value in obstacles:
		if typeof(value) != TYPE_DICTIONARY:
			continue
		var obstacle: Dictionary = value
		var obstacle_id := str(obstacle.get("id", "obstacle"))
		var width := maxf(float(obstacle.get("width", 1.0)), 0.1)
		var depth := maxf(float(obstacle.get("height", 1.0)), 0.1)
		var center := Vector2(float(obstacle.get("x", 0.0)), float(obstacle.get("y", 0.0)))
		var body := StaticBody3D.new()
		body.name = "Obstacle_%s" % obstacle_id
		body.position = _world_position(center, 0.55)
		body.collision_layer = 1
		body.collision_mask = 1

		var mesh_instance := MeshInstance3D.new()
		var box_mesh := BoxMesh.new()
		box_mesh.size = Vector3(width, 1.1, depth)
		mesh_instance.mesh = box_mesh
		mesh_instance.material_override = _material(Color("#6a5960"))
		body.add_child(mesh_instance)

		var collision := CollisionShape3D.new()
		var box_shape := BoxShape3D.new()
		box_shape.size = Vector3(width, 1.1, depth)
		collision.shape = box_shape
		body.add_child(collision)
		obstacle_root.add_child(body)


func _probe_godot_motion(from_position: Vector2, to_position: Vector2) -> void:
	if not is_instance_valid(body_cast):
		return
	var delta := to_position - from_position
	body_cast.target_position = Vector3(delta.x, 0.0, delta.y)
	body_cast.force_shapecast_update()
	godot_contact_count = body_cast.get_collision_count()
	body_cast.target_position = Vector3.ZERO


func _build_camera() -> void:
	camera = Camera3D.new()
	camera.current = true
	camera.fov = 52.0
	add_child(camera)


func _build_hud() -> void:
	var canvas := CanvasLayer.new()
	canvas.name = "HUD"
	add_child(canvas)

	var panel := ColorRect.new()
	panel.position = Vector2(24.0, 24.0)
	panel.size = Vector2(420.0, 270.0)
	panel.color = Color(0.025, 0.07, 0.09, 0.91)
	canvas.add_child(panel)

	status_label = _label(canvas, "FLYTEST ARENA 3D", Vector2(42.0, 38.0), 22, palette["ink"])
	sensor_label = _label(canvas, "", Vector2(42.0, 108.0), 14, palette["teal"])
	var trace_panel := ColorRect.new()
	trace_panel.position = Vector2(24.0, 310.0)
	trace_panel.size = Vector2(420.0, 252.0)
	trace_panel.color = Color(0.025, 0.07, 0.09, 0.91)
	canvas.add_child(trace_panel)
	trace_label = _label(canvas, "", Vector2(42.0, 326.0), 12, palette["ink"])
	trace_label.size = Vector2(385.0, 220.0)
	help_label = _label(canvas, "", Vector2(42.0, 585.0), 13, palette["muted"])

	var retina_title := _label(canvas, "RETINA / 9 × 5", Vector2(1040.0, 34.0), 14, palette["ink"])
	retina_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	var retina_panel := ColorRect.new()
	retina_panel.position = Vector2(1024.0, 58.0)
	retina_panel.size = Vector2(216.0, 126.0)
	retina_panel.color = Color(0.025, 0.07, 0.09, 0.91)
	canvas.add_child(retina_panel)
	for row in range(5):
		for column in range(9):
			var cell := ColorRect.new()
			cell.position = Vector2(12.0 + column * 21.0, 12.0 + row * 21.0)
			cell.size = Vector2(15.0, 15.0)
			cell.color = Color("#102b31")
			retina_panel.add_child(cell)
			retina_cells.append(cell)


func _build_bridge() -> void:
	bridge = preload("res://arena_bridge.gd").new()
	add_child(bridge)
	bridge.session_ready.connect(_on_session_ready)
	bridge.step_ready.connect(_on_step_ready)
	bridge.bridge_failed.connect(_on_bridge_failed)


func _request_session() -> void:
	session_id = ""
	session_is_ready = false
	step_pending = false
	step_accumulator = 0.0
	replay_status = "REQUESTING LIVE STAGE 1024 SESSION"
	paused = true
	_reset_live_view()
	if bridge != null:
		bridge.request_session()


func _on_session_ready(payload: Dictionary) -> void:
	session_id = str(payload.get("session_id", ""))
	if session_id.is_empty():
		_on_bridge_failed("Python Arena returned an empty session ID")
		return
	var network_value: Variant = payload.get("network", {})
	var stage := "1024"
	if typeof(network_value) == TYPE_DICTIONARY:
		stage = str(network_value.get("stage", 1024))
	replay_status = "LIVE CLOSED LOOP · STAGE %s" % stage
	_load_session_world(payload)
	session_is_ready = true
	paused = false


func _on_bridge_failed(message: String) -> void:
	replay_status = message
	step_pending = false
	paused = true


func _request_live_step() -> void:
	if bridge == null or session_id.is_empty() or step_pending:
		return
	step_pending = true
	var body := {
		"x": fly_position.x,
		"y": fly_position.y,
		"heading_degrees": rad_to_deg(fly_heading),
	}
	bridge.request_step(session_id, sim_time, body, live_lights, live_threats)


func _on_step_ready(payload: Dictionary) -> void:
	step_pending = false
	var frame_value: Variant = payload.get("frame", {})
	if typeof(frame_value) != TYPE_DICTIONARY:
		_on_bridge_failed("Python Arena returned an invalid live frame")
		return
	var frame: Dictionary = frame_value
	var previous_position := fly_position
	var next_body_value: Variant = payload.get("next_body", {})
	if typeof(next_body_value) == TYPE_DICTIONARY:
		var next_position := Vector2(float(next_body_value.get("x", previous_position.x)), float(next_body_value.get("y", previous_position.y)))
		# Probe while the ShapeCast3D is still rooted at the pre-step body.
		_probe_godot_motion(previous_position, next_position)
	_apply_live_frame(frame)
	if typeof(next_body_value) == TYPE_DICTIONARY:
		var next_position := Vector2(float(next_body_value.get("x", fly_position.x)), float(next_body_value.get("y", fly_position.y)))
		fly_position = next_position
		fly_heading = deg_to_rad(float(next_body_value.get("heading_degrees", rad_to_deg(fly_heading))))
		fly_root.position = _world_position(fly_position, 0.0)
		fly_root.rotation.y = -fly_heading + PI / 2.0
	var next_lights_value: Variant = payload.get("next_lights", [])
	var next_threats_value: Variant = payload.get("next_threats", [])
	if typeof(next_lights_value) == TYPE_ARRAY:
		live_lights = _duplicate_dictionary_array(next_lights_value)
	if typeof(next_threats_value) == TYPE_ARRAY:
		live_threats = _duplicate_dictionary_array(next_threats_value)
	var obstacles_value: Variant = frame.get("obstacles", live_obstacles)
	if typeof(obstacles_value) == TYPE_ARRAY:
		var next_obstacles := _duplicate_dictionary_array(obstacles_value)
		if next_obstacles != live_obstacles:
			live_obstacles = next_obstacles
			_render_obstacles(live_obstacles)
	_render_live_objects()
	sim_time = float(payload.get("next_time_ms", sim_time + 1.0))
	_update_trail()


func _load_session_world(payload: Dictionary) -> void:
	var body_value: Variant = payload.get("body", {})
	if typeof(body_value) == TYPE_DICTIONARY:
		fly_position = Vector2(float(body_value.get("x", 0.0)), float(body_value.get("y", 0.0)))
		fly_heading = deg_to_rad(float(body_value.get("heading_degrees", 0.0)))
	var environment_value: Variant = payload.get("environment", {})
	if typeof(environment_value) == TYPE_DICTIONARY:
		var lights_value: Variant = environment_value.get("lights", [])
		var threats_value: Variant = environment_value.get("threats", [])
		var obstacles_value: Variant = environment_value.get("obstacles", [])
		if typeof(lights_value) == TYPE_ARRAY:
			live_lights = _duplicate_dictionary_array(lights_value)
		if typeof(threats_value) == TYPE_ARRAY:
			live_threats = _duplicate_dictionary_array(threats_value)
		if typeof(obstacles_value) == TYPE_ARRAY:
			live_obstacles = _duplicate_dictionary_array(obstacles_value)
	_render_obstacles(live_obstacles)
	_render_live_objects()
	fly_root.position = _world_position(fly_position, 0.0)
	fly_root.rotation.y = -fly_heading + PI / 2.0


func _duplicate_dictionary_array(value: Array) -> Array:
	var result: Array = []
	for item in value:
		if typeof(item) == TYPE_DICTIONARY:
			result.append((item as Dictionary).duplicate(true))
	return result


func _reset_live_view() -> void:
	sim_time = 0.0
	fly_position = Vector2(0.0, 0.0)
	fly_heading = 0.0
	action_name = "stop"
	action_source = "none"
	action_reason = "waiting for neural session"
	active_spike_count = 0
	threat_visible = false
	trail_points = PackedVector3Array([_world_position(fly_position, 0.18)])
	live_lights = [{"id": "beacon", "x": 7.0, "y": 4.0, "intensity": 1.0, "vx": -0.012, "vy": 0.004}]
	live_threats = [{"id": "scripted-threat", "x": 2.0, "y": 1.5, "radius": 1.1, "trigger": "timed", "active_start_ms": 80.0, "active_end_ms": 96.0, "vx": 0.018, "vy": -0.006}]
	live_obstacles = []
	python_collision_ids = []
	godot_contact_count = 0
	current_world_cause = {}
	current_neural_cause = {}
	if is_instance_valid(fly_root):
		fly_root.position = _world_position(fly_position, 0.0)
	if is_instance_valid(threat_root):
		threat_root.visible = false
	if is_instance_valid(threat_core):
		threat_core.visible = false
	if is_instance_valid(escape_ring):
		escape_ring.visible = false
	if is_instance_valid(collision_ring):
		collision_ring.visible = false
	_render_obstacles(live_obstacles)
	_update_trail()
	_apply_retina_values([])


func _apply_live_frame(frame: Dictionary) -> void:
	sim_time = float(frame.get("time_ms", 0.0))
	fly_position = Vector2(float(frame.get("position_x", fly_position.x)), float(frame.get("position_y", fly_position.y)))
	fly_heading = deg_to_rad(float(frame.get("heading_degrees", 0.0)))
	action_name = str(frame.get("action", "stop"))
	action_source = str(frame.get("action_source", "none"))
	action_reason = str(frame.get("action_reason", ""))
	var world_cause_value: Variant = frame.get("world_cause", {})
	current_world_cause = world_cause_value if typeof(world_cause_value) == TYPE_DICTIONARY else {}
	var neural_cause_value: Variant = frame.get("neural_cause", {})
	current_neural_cause = neural_cause_value if typeof(neural_cause_value) == TYPE_DICTIONARY else {}
	var collision_value: Variant = current_world_cause.get("collision_ids", [])
	python_collision_ids = collision_value if typeof(collision_value) == TYPE_ARRAY else []
	var spikes_value: Variant = frame.get("active_spikes", [])
	active_spike_count = spikes_value.size() if typeof(spikes_value) == TYPE_ARRAY else 0
	fly_root.position = _world_position(fly_position, 0.0)
	fly_root.rotation.y = -fly_heading + PI / 2.0

	var lights_value: Variant = frame.get("lights", [])
	var lights: Array = []
	if typeof(lights_value) == TYPE_ARRAY:
		lights = lights_value
	if not lights.is_empty():
		var light: Dictionary = lights[0]
		beacon_position = Vector2(float(light.get("x", beacon_position.x)), float(light.get("y", beacon_position.y)))
		beacon_root.position = _world_position(beacon_position, 0.5)
		var intensity := maxf(float(light.get("intensity", 1.0)), 0.1)
		beacon_root.scale = Vector3.ONE * clampf(0.8 + intensity * 0.18, 0.8, 1.4)

	var threats_value: Variant = frame.get("threats", [])
	var threats: Array = []
	if typeof(threats_value) == TYPE_ARRAY:
		threats = threats_value
	if not threats.is_empty():
		var threat: Dictionary = threats[0]
		threat_position = Vector2(float(threat.get("x", threat_position.x)), float(threat.get("y", threat_position.y)))
		threat_root.position = _world_position(threat_position, 0.85)
		var radius := maxf(float(threat.get("radius", 1.0)), 0.25)
		threat_root.scale = Vector3.ONE * radius
		threat_root.visible = true
	var threat_id: Variant = frame.get("threat_id", null)
	threat_visible = threat_id != null or bool(frame.get("touch_stimulus_active", false))
	if is_instance_valid(threat_core):
		threat_core.visible = threat_visible
	if is_instance_valid(threat_root):
		threat_root.visible = not threats.is_empty()
	if is_instance_valid(escape_ring):
		escape_ring.visible = bool(frame.get("escape_marker", false))
	if is_instance_valid(collision_ring):
		collision_ring.visible = bool(current_world_cause.get("blocked", false)) or godot_contact_count > 0

	trail_points.append(fly_root.position + Vector3(0.0, 0.18, 0.0))
	if trail_points.size() > 460:
		trail_points.remove_at(0)
	var retina_value: Variant = frame.get("retina", [])
	_apply_retina_values(retina_value)


func _render_live_objects() -> void:
	if not live_lights.is_empty():
		var light: Dictionary = live_lights[0]
		beacon_position = Vector2(float(light.get("x", beacon_position.x)), float(light.get("y", beacon_position.y)))
		beacon_root.position = _world_position(beacon_position, 0.5)
		var intensity := maxf(float(light.get("intensity", 1.0)), 0.1)
		beacon_root.scale = Vector3.ONE * clampf(0.8 + intensity * 0.18, 0.8, 1.4)
	if not live_threats.is_empty():
		var threat: Dictionary = live_threats[0]
		threat_position = Vector2(float(threat.get("x", threat_position.x)), float(threat.get("y", threat_position.y)))
		threat_root.position = _world_position(threat_position, 0.85)
		var radius := maxf(float(threat.get("radius", 1.0)), 0.25)
		threat_root.scale = Vector3.ONE * radius
		threat_root.visible = true


func _update_camera() -> void:
	if not is_instance_valid(camera) or not is_instance_valid(fly_root):
		return
	var focus := fly_root.position + Vector3(0.0, 0.35, 0.0)
	var offset := Vector3(cos(camera_yaw) * camera_distance, camera_distance * sin(camera_pitch), sin(camera_yaw) * camera_distance)
	camera.position = focus + offset
	camera.look_at(focus, Vector3.UP)


func _update_hud() -> void:
	if not is_instance_valid(status_label):
		return
	var mode := "PAUSED" if paused else "LIVE"
	status_label.text = "FLYTEST ARENA 3D\n%s  ·  %05.1f ms" % [mode, sim_time]
	var transport := "tick pending" if step_pending else "tick ready"
	sensor_label.text = "%s\nACTION  %s  ·  %s\nCAUSE   %s\nSPIKES  %d   BEACON  %.2f m\nTHREAT  %s  ·  %s" % [replay_status, action_name.to_upper(), action_source, action_reason, active_spike_count, fly_position.distance_to(beacon_position), "ACTIVE" if threat_visible else "WAITING", transport]
	var input_groups: Dictionary = {}
	var output_votes: Dictionary = {}
	var visual_features: Dictionary = {}
	var winning_nodes: Array = []
	var input_value: Variant = current_neural_cause.get("input_groups", {})
	var vote_value: Variant = current_neural_cause.get("output_votes", {})
	var visual_value: Variant = current_neural_cause.get("visual_features", {})
	var winning_value: Variant = current_neural_cause.get("winning_output_nodes", [])
	if typeof(input_value) == TYPE_DICTIONARY:
		input_groups = input_value
	if typeof(vote_value) == TYPE_DICTIONARY:
		output_votes = vote_value
	if typeof(visual_value) == TYPE_DICTIONARY:
		visual_features = visual_value
	if typeof(winning_value) == TYPE_ARRAY:
		winning_nodes = winning_value
	var nearby_value: Variant = current_world_cause.get("nearby_obstacle_ids", [])
	var nearby_text := "none"
	if typeof(nearby_value) == TYPE_ARRAY and not nearby_value.is_empty():
		nearby_text = ", ".join(nearby_value)
	var collision_text := "none"
	if not python_collision_ids.is_empty():
		collision_text = ", ".join(python_collision_ids)
	trace_label.text = "CAUSAL TRACE\nWORLD   touch %s/%s  ·  nearby %s\nCONTACT python %s  ·  Godot shapes %d\nSENSE   L %.2f  C %.2f  R %.2f  motion %.2f\nINPUT   touch L %.1f  R %.1f  urgency %.1f\nSPIKES  %d active  ·  %d winning descending nodes\nVOTE    left %.0f  right %.0f  forward %.0f  escape L %.0f/R %.0f\nACTION  %s  ·  %s" % [str(current_world_cause.get("touch_source", "none")), str(current_world_cause.get("touch_id", "none")), nearby_text, collision_text, godot_contact_count, float(visual_features.get("left", 0.0)), float(visual_features.get("center", 0.0)), float(visual_features.get("right", 0.0)), float(visual_features.get("motion", 0.0)), active_spike_count, winning_nodes.size(), float(input_groups.get("touch_left", 0.0)), float(input_groups.get("touch_right", 0.0)), float(input_groups.get("threat_urgency", 0.0)), float(output_votes.get("turn_left", 0.0)), float(output_votes.get("turn_right", 0.0)), float(output_votes.get("forward", 0.0)), float(output_votes.get("escape_left", 0.0)), float(output_votes.get("escape_right", 0.0)), action_name.to_upper(), action_source]
	help_label.text = "Right-drag orbit  ·  wheel zoom  ·  SPACE pause  ·  R new neural session"


func _apply_retina_values(retina_value: Variant) -> void:
	if retina_cells.is_empty():
		return
	for index in range(retina_cells.size()):
		var value: float = 0.0
		if typeof(retina_value) == TYPE_ARRAY and index < retina_value.size():
			value = clampf(float(retina_value[index]) * 4.0, 0.0, 1.0)
		retina_cells[index].color = Color(0.05 + value * 0.18, 0.22 + value * 0.68, 0.25 + value * 0.55, 1.0)


func _update_trail() -> void:
	if not is_instance_valid(trail_mesh):
		return
	trail_mesh.clear_surfaces()
	trail_mesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP, _material(palette["teal"]))
	for point in trail_points:
		trail_mesh.surface_add_vertex(point)
	trail_mesh.surface_end()


func _world_position(point: Vector2, height: float) -> Vector3:
	return Vector3(point.x, height, point.y)


func _material(color: Color, emission: bool = false) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.72
	if color.a < 1.0:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	if emission:
		material.emission_enabled = true
		material.emission = Color(color.r, color.g, color.b, 1.0)
		material.emission_energy_multiplier = 2.8
	return material


func _sphere(color: Color, radius: float, position: Vector3, scale: Vector3, emission: bool = false) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2.0
	mesh.radial_segments = 16
	mesh.rings = 8
	instance.mesh = mesh
	instance.position = position
	instance.scale = scale
	instance.material_override = _material(color, emission)
	return instance


func _label(parent: Node, text: String, position: Vector2, font_size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.position = position
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	parent.add_child(label)
	return label
