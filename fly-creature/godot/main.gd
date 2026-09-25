extends Node3D

# The world and walking controls are Godot code. Only the jump trigger comes
# from the Python circuit: LC4/LPLC2 activity -> DNp01 spike -> jump request.

const ROOM_HALF_SIZE := 8.0
const WALK_SPEED := 2.6
const BALL_SPEED := 4.0
const BALL_RADIUS := 0.45
const NEURAL_STEP_S := 0.05

@onready var bridge: NeuralBridge = $NeuralBridge

var fly_root: Node3D
var ball_root: Node3D
var status_label: Label
var detail_label: Label
var fly_position := Vector3.ZERO
var heading_rad := 0.0
var jump_height := 0.0
var jump_velocity := 0.0
var ball_position := Vector3(0.0, 0.55, -7.0)
var ball_velocity := Vector3.ZERO
var ball_active := false
var session_id := ""
var condition := "intact"
var step_clock := 0.0
var last_trace: Dictionary = {}
var service_message := "Connecting to neural service..."


func _ready() -> void:
	_build_world()
	_build_fly()
	_build_ball()
	_build_hud()
	bridge.session_ready.connect(_on_session_ready)
	bridge.step_ready.connect(_on_step_ready)
	bridge.bridge_failed.connect(_on_bridge_failed)
	_start_session()


func _process(delta: float) -> void:
	_move_fly(delta)
	_move_ball(delta)
	_animate_jump(delta)
	fly_root.position = fly_position + Vector3(0.0, jump_height, 0.0)
	fly_root.rotation.y = heading_rad
	ball_root.position = ball_position
	ball_root.visible = ball_active
	if not session_id.is_empty():
		step_clock += delta
		if step_clock >= NEURAL_STEP_S:
			step_clock = 0.0
			bridge.step(session_id,
				{"x": fly_position.x, "z": fly_position.z, "heading_rad": heading_rad},
				{"x": ball_position.x, "z": ball_position.z, "radius": BALL_RADIUS, "active": ball_active})
	_update_hud()


func _unhandled_key_input(event: InputEvent) -> void:
	var key_event := event as InputEventKey
	if key_event == null or not key_event.pressed or key_event.echo:
		return
	match key_event.keycode:
		KEY_SPACE:
			_launch_ball()
		KEY_R:
			_start_session()
		KEY_C:
			condition = "disconnected" if condition == "intact" else "intact"
			_start_session()


func _move_fly(delta: float) -> void:
	var movement := Vector2.ZERO
	if Input.is_key_pressed(KEY_W):
		movement.y -= 1.0
	if Input.is_key_pressed(KEY_S):
		movement.y += 1.0
	if Input.is_key_pressed(KEY_A):
		movement.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		movement.x += 1.0
	if movement.length_squared() > 0.0:
		movement = movement.normalized()
		fly_position.x = clampf(fly_position.x + movement.x * WALK_SPEED * delta, -ROOM_HALF_SIZE, ROOM_HALF_SIZE)
		fly_position.z = clampf(fly_position.z + movement.y * WALK_SPEED * delta, -ROOM_HALF_SIZE, ROOM_HALF_SIZE)
		heading_rad = atan2(movement.x, -movement.y)


func _move_ball(delta: float) -> void:
	if not ball_active:
		return
	ball_position += ball_velocity * delta
	if ball_position.distance_to(fly_position + Vector3(0.0, 0.55, 0.0)) < 0.25:
		ball_active = false
	elif ball_position.length() > 20.0:
		ball_active = false


func _animate_jump(delta: float) -> void:
	if jump_height <= 0.0 and jump_velocity <= 0.0:
		return
	jump_height += jump_velocity * delta
	jump_velocity -= 10.0 * delta
	if jump_height <= 0.0:
		jump_height = 0.0
		jump_velocity = 0.0


func _launch_ball() -> void:
	var forward := Vector3(sin(heading_rad), 0.0, -cos(heading_rad))
	ball_position = fly_position + forward * 7.0 + Vector3(0.0, 0.55, 0.0)
	ball_velocity = -forward * BALL_SPEED
	ball_active = true
	service_message = "Approaching object launched"


func _start_session() -> void:
	session_id = ""
	last_trace = {}
	step_clock = 0.0
	fly_position = Vector3.ZERO
	heading_rad = 0.0
	jump_height = 0.0
	jump_velocity = 0.0
	ball_active = false
	service_message = "Starting %s neural session..." % condition
	bridge.start_session(condition)


func _on_session_ready(payload: Dictionary) -> void:
	session_id = str(payload.get("session_id", ""))
	service_message = "Neural session ready: %s" % condition


func _on_step_ready(payload: Dictionary) -> void:
	last_trace = payload
	if bool(payload.get("jump", false)) and jump_height == 0.0:
		jump_velocity = 5.2
		service_message = "DNp01 spike triggered jump"


func _on_bridge_failed(message: String) -> void:
	session_id = ""
	service_message = message + " | start Python service, then press R"


func _update_hud() -> void:
	status_label.text = "FLY CREATURE  /  %s\n%s" % [condition.to_upper(), service_message]
	var visual: Dictionary = last_trace.get("visual", {})
	var spikes: Dictionary = last_trace.get("spikes", {})
	detail_label.text = "WASD move  |  SPACE approach  |  C disconnect circuit  |  R reset\n" \
		+ "Object angle: %s deg   expansion: %s deg/s\n" % [visual.get("angle_deg", "--"), visual.get("expansion_deg_s", "--")] \
		+ "LC4 spikes: %s   LPLC2 spikes: %s   giant fiber spikes: %s\n" % [spikes.get("LC4", "--"), spikes.get("LPLC2", "--"), spikes.get("DNp01", "--")] \
		+ "Walking, visual features, and jump animation are engineered. The selected connections are MaleCNS data."


func _build_world() -> void:
	var floor_mesh := BoxMesh.new()
	floor_mesh.size = Vector3(18.0, 0.2, 18.0)
	var floor_body := MeshInstance3D.new()
	floor_body.mesh = floor_mesh
	floor_body.position.y = -0.15
	floor_body.material_override = _material(Color(0.16, 0.21, 0.25))
	add_child(floor_body)
	for index in range(-8, 9):
		_add_rail(Vector3(index, -0.045, -8.5), Vector3(index, -0.045, 8.5), Color(0.24, 0.31, 0.35))
		_add_rail(Vector3(-8.5, -0.045, index), Vector3(8.5, -0.045, index), Color(0.24, 0.31, 0.35))
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-55.0, -30.0, 0.0)
	light.light_energy = 1.6
	add_child(light)
	var camera := Camera3D.new()
	camera.position = Vector3(0.0, 10.0, 12.0)
	add_child(camera)
	camera.look_at(Vector3(0.0, 0.0, -2.0), Vector3.UP)
	camera.current = true


func _add_rail(start: Vector3, finish: Vector3, color: Color) -> void:
	var length := start.distance_to(finish)
	var rail := MeshInstance3D.new()
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.008
	mesh.bottom_radius = 0.008
	mesh.height = length
	rail.mesh = mesh
	rail.position = (start + finish) * 0.5
	rail.quaternion = Quaternion(Vector3.UP, (finish - start).normalized())
	rail.material_override = _material(color)
	add_child(rail)


func _build_fly() -> void:
	fly_root = Node3D.new()
	add_child(fly_root)
	_sphere(fly_root, Vector3(0.0, 0.28, 0.2), Vector3(0.38, 0.26, 0.52), Color(0.48, 0.31, 0.20))
	_sphere(fly_root, Vector3(0.0, 0.33, -0.35), Vector3(0.28, 0.27, 0.28), Color(0.62, 0.43, 0.25))
	_sphere(fly_root, Vector3(-0.19, 0.38, -0.51), Vector3(0.14, 0.17, 0.13), Color(0.85, 0.20, 0.21))
	_sphere(fly_root, Vector3(0.19, 0.38, -0.51), Vector3(0.14, 0.17, 0.13), Color(0.85, 0.20, 0.21))
	_sphere(fly_root, Vector3(-0.42, 0.58, 0.05), Vector3(0.55, 0.045, 0.25), Color(0.70, 0.86, 0.93, 0.7))
	_sphere(fly_root, Vector3(0.42, 0.58, 0.05), Vector3(0.55, 0.045, 0.25), Color(0.70, 0.86, 0.93, 0.7))
	for side in [-1.0, 1.0]:
		for z_offset in [-0.2, 0.1, 0.37]:
			_add_leg(fly_root, Vector3(side * 0.2, 0.22, z_offset), Vector3(side * 0.52, 0.01, z_offset + 0.15))


func _add_leg(parent: Node3D, start: Vector3, finish: Vector3) -> void:
	var leg := MeshInstance3D.new()
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.018
	mesh.bottom_radius = 0.018
	mesh.height = start.distance_to(finish)
	leg.mesh = mesh
	leg.position = (start + finish) * 0.5
	leg.quaternion = Quaternion(Vector3.UP, (finish - start).normalized())
	leg.material_override = _material(Color(0.19, 0.14, 0.12))
	parent.add_child(leg)


func _build_ball() -> void:
	ball_root = Node3D.new()
	add_child(ball_root)
	_sphere(ball_root, Vector3.ZERO, Vector3.ONE * BALL_RADIUS, Color(0.95, 0.30, 0.23))
	ball_root.visible = false


func _sphere(parent: Node3D, position: Vector3, size: Vector3, color: Color) -> void:
	var mesh := SphereMesh.new()
	mesh.radius = 1.0
	mesh.height = 2.0
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = position
	instance.scale = size
	instance.material_override = _material(color)
	parent.add_child(instance)


func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.7
	if color.a < 1.0:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return material


func _build_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var panel := PanelContainer.new()
	panel.position = Vector2(22.0, 20.0)
	panel.custom_minimum_size = Vector2(630.0, 88.0)
	layer.add_child(panel)
	status_label = Label.new()
	status_label.add_theme_font_size_override("font_size", 20)
	panel.add_child(status_label)
	var detail_panel := PanelContainer.new()
	detail_panel.position = Vector2(22.0, 555.0)
	detail_panel.custom_minimum_size = Vector2(1110.0, 124.0)
	layer.add_child(detail_panel)
	detail_label = Label.new()
	detail_label.add_theme_font_size_override("font_size", 16)
	detail_panel.add_child(detail_label)
