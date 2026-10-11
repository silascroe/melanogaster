extends Node3D

# World motion, object sensing, and motor readouts are engineered. Recorded
# connections contribute to the jump trigger and optional pursuit steering.

const ROOM_HALF_SIZE := 8.0
const WALK_SPEED := 1.45
const ROAM_SPEED := 1.05
const WALKING_DEMO_SPEED := 0.62
const FLIGHT_ROAM_SPEED := 1.9
const BALL_SPEED := 4.0
const BALL_RADIUS := 0.45
const NEURAL_STEP_S := 0.05
const PURSUIT_WALK_SPEED := 0.55
const BEACON_WALK_SPEED := 0.9
const BEACON_REACHED_M := 0.55
const SEARCH_TURN_RATE := 1.6
const SUGAR_RADIUS := 0.22
const SUGAR_EAT_S := 4.0
const TASTE_WAIT_S := 1.2

@onready var bridge: NeuralBridge = $NeuralBridge
@onready var fly_actor: FlyActor = $Fly

var walking_now := false
var move_speed := 0.0
var camera: Camera3D
var close_camera := true
var ball_root: Node3D
var target_root: Node3D
var status_label: Label
var detail_label: Label
var fly_position := Vector3.ZERO
var heading_rad := 0.0
var ball_position := Vector3(0.0, 0.55, -7.0)
var ball_velocity := Vector3.ZERO
var ball_active := false
var session_id := ""
var condition := "intact"
var step_clock := 0.0
var last_trace: Dictionary = {}
var service_message := "Connecting to neural service..."
var animation_demo := false
var walking_demo := false
var demo_elapsed := 0.0
var demo_takeoff_started := false
var demo_landing_started := false
var roam_enabled := false
var roam_goal := Vector3(4.0, 0.0, -4.0)
var roam_rng := RandomNumberGenerator.new()
var pursuit_enabled := false
var pursuit_demo := false
const BrainViewScript := preload("res://brain_view.gd")
const KitchenWorldScript := preload("res://kitchen_world.gd")
var brain_view: Control
# Click-placed target: the fly approaches it on its own, steering by DNa02.
var beacon_mode := false
# Sugar drop (right-click). Tasting and the decision to feed come from the brain;
# pausing at the drop and the drop shrinking while fed on are engineered.
var sugar_root: Node3D
var sugar_active := false
var sugar_position := Vector3.ZERO
var sugar_eaten_s := 0.0
var taste_wait_s := 0.0
var feeding_now := false
var pursuit_time := 0.0
var target_position := Vector3(-2.9, 0.45, -6.5)
var steering_turn_rate := 0.0
var steering_model := "brain"
var pursuit_path := "crossing"
var pursuit_seconds := 0.0
var record_ticks := false


func _ready() -> void:
	if OS.get_cmdline_user_args().has("--capture-hd"):
		get_window().content_scale_size = Vector2i(1920, 1080)
		get_window().size = Vector2i(1920, 1080)
	animation_demo = OS.get_cmdline_user_args().has("--animation-demo")
	walking_demo = OS.get_cmdline_user_args().has("--walking-demo")
	pursuit_demo = OS.get_cmdline_user_args().has("--pursuit-demo")
	pursuit_enabled = pursuit_demo
	if OS.get_cmdline_user_args().has("--pursuit-experimental"):
		steering_model = "activity_v1"
		pursuit_path = "harmonic"
		pursuit_demo = true
		pursuit_enabled = true
	record_ticks = OS.get_cmdline_user_args().has("--pursuit-trace")
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--pursuit-path="):
			pursuit_path = argument.trim_prefix("--pursuit-path=")
		if argument.begins_with("--pursuit-seconds="):
			pursuit_seconds = float(argument.trim_prefix("--pursuit-seconds="))
	if OS.get_cmdline_user_args().has("--pursuit-control"):
		pursuit_demo = true
		pursuit_enabled = true
		condition = "disconnected"
	if pursuit_demo:
		close_camera = false
		if steering_model == "brain":
			steering_model = "lif"  # recorded pursuit demos use the original circuit
	# The fly lives on its own by default; WASD takes over while held.
	roam_enabled = not (pursuit_demo or walking_demo)
	if animation_demo:
		roam_rng.seed = 340617
	else:
		roam_rng.randomize()
	if walking_demo:
		fly_position.z = 1.8
		fly_actor.position = fly_position
		fly_actor.reset_actor()
	_build_world()
	_build_ball()
	_build_target()
	_build_sugar()
	if animation_demo or walking_demo:
		# A presentation clip: the route and flight are authored, not neural outputs.
		return
	_build_hud()
	bridge.session_ready.connect(_on_session_ready)
	bridge.step_ready.connect(_on_step_ready)
	bridge.bridge_failed.connect(_on_bridge_failed)
	_start_session()


func _process(delta: float) -> void:
	var previous_position := fly_position
	var advanced_delta := delta
	if steering_model == "activity_v1" and pursuit_enabled:
		advanced_delta = _advance_experimental(delta)
	else:
		_move_fly(delta)
		_move_ball(delta)
		_move_target(delta)
	move_speed = fly_position.distance_to(previous_position) / maxf(advanced_delta, 0.0001)
	fly_actor.position = fly_position
	fly_actor.rotation.y = -heading_rad
	fly_actor.advance(advanced_delta, walking_now, move_speed)
	_update_camera(delta)
	ball_root.position = ball_position
	ball_root.visible = ball_active
	target_root.position = target_position
	target_root.visible = pursuit_enabled
	fly_actor.set_feeding(feeding_now)
	if sugar_active and feeding_now:
		sugar_eaten_s += delta
		if sugar_eaten_s >= SUGAR_EAT_S:
			sugar_active = false
			service_message = "Sugar drop finished"
	sugar_root.visible = sugar_active
	sugar_root.position = sugar_position
	sugar_root.scale = Vector3.ONE * maxf(0.25, 1.0 - sugar_eaten_s / SUGAR_EAT_S)
	if not session_id.is_empty() and not (steering_model == "activity_v1" and pursuit_enabled):
		if steering_model == "activity_v1":
			# No experimental ticks during manual walking.
			_update_hud()
			return
		step_clock += delta
		if step_clock >= NEURAL_STEP_S:
			step_clock = 0.0
			bridge.step(session_id,
				{"x": fly_position.x, "z": fly_position.z, "heading_rad": heading_rad},
				{"x": ball_position.x, "z": ball_position.z, "radius": BALL_RADIUS, "active": ball_active},
				{"x": target_position.x, "z": target_position.z, "active": pursuit_enabled},
				{"x": sugar_position.x, "z": sugar_position.z, "radius": SUGAR_RADIUS, "active": sugar_active})
	if not animation_demo and not walking_demo:
		_update_hud()
	if pursuit_demo and Engine.get_process_frames() % 60 == 0:
		print("PURSUIT_TELEMETRY ", JSON.stringify({
			"model": steering_model,
			"condition": condition, "time_s": snappedf(pursuit_time, 0.01),
			"fly_x": snappedf(fly_position.x, 0.001),
			"fly_z": snappedf(fly_position.z, 0.001),
			"heading_deg": snappedf(rad_to_deg(heading_rad), 0.1),
			"bearing_deg": last_trace.get("steering", {}).get("bearing_deg", "--"),
			"turn_rate": steering_turn_rate,
		}))


func _unhandled_input(event: InputEvent) -> void:
	var click := event as InputEventMouseButton
	if click == null or not click.pressed:
		return
	if click.button_index != MOUSE_BUTTON_LEFT and click.button_index != MOUSE_BUTTON_RIGHT:
		return
	if animation_demo or walking_demo or pursuit_demo or session_id.is_empty():
		return
	if steering_model == "activity_v1":
		return
	var ray_origin := camera.project_ray_origin(click.position)
	var ray_direction := camera.project_ray_normal(click.position)
	var hit: Variant = Plane(Vector3.UP, 0.0).intersects_ray(ray_origin, ray_direction)
	if hit == null:
		return
	if click.button_index == MOUSE_BUTTON_RIGHT:
		place_sugar(hit)
	place_beacon(hit)


func place_sugar(floor_point: Vector3) -> void:
	sugar_position = Vector3(clampf(floor_point.x, -ROOM_HALF_SIZE + 1.0, ROOM_HALF_SIZE - 1.0), 0.0,
		clampf(floor_point.z, -ROOM_HALF_SIZE + 1.0, ROOM_HALF_SIZE - 1.0))
	sugar_active = true
	sugar_eaten_s = 0.0


func place_beacon(floor_point: Vector3) -> void:
	var point := floor_point
	point.x = clampf(point.x, -ROOM_HALF_SIZE + 1.0, ROOM_HALF_SIZE - 1.0)
	point.z = clampf(point.z, -ROOM_HALF_SIZE + 1.0, ROOM_HALF_SIZE - 1.0)
	beacon_mode = true
	pursuit_enabled = true
	roam_enabled = false
	target_position = Vector3(point.x, 0.45, point.z)
	service_message = "Target placed: the fly decides how to reach it"


func _end_beacon() -> void:
	beacon_mode = false
	pursuit_enabled = false
	steering_turn_rate = 0.0
	roam_enabled = true
	roam_goal = fly_position
	service_message = "Reached the target; roaming again"


func _unhandled_key_input(event: InputEvent) -> void:
	var key_event := event as InputEventKey
	if key_event == null or not key_event.pressed or key_event.echo:
		return
	match key_event.keycode:
		KEY_P:
			get_tree().change_scene_to_file("res://playground.tscn")
		KEY_SPACE:
			_launch_ball()
		KEY_R:
			_start_session()
		KEY_C:
			condition = "disconnected" if condition == "intact" else "intact"
			_start_session()
		KEY_F:
			close_camera = not close_camera
		KEY_G:
			if pursuit_enabled:
				return
			roam_enabled = not roam_enabled
			roam_goal = Vector3(4.0, 0.0, -4.0) if roam_enabled else fly_position
			service_message = "Roaming on (engineered controller)" if roam_enabled else "Manual walking"
		KEY_V:
			pursuit_enabled = not pursuit_enabled
			if not pursuit_enabled and steering_model == "activity_v1":
				steering_model = "lif"
			roam_enabled = not pursuit_enabled
			_start_session()
			service_message = "Neural pursuit: moving target" if pursuit_enabled else "Manual walking"
		KEY_B:
			# brain (whole-brain subset) -> lif (original circuit) -> activity_v1 -> brain
			steering_model = {"brain": "lif", "lif": "activity_v1", "activity_v1": "brain"}[steering_model]
			pursuit_path = "harmonic" if steering_model == "activity_v1" else "crossing"
			pursuit_enabled = steering_model != "brain"
			roam_enabled = steering_model == "brain"
			_start_session()
		KEY_T:
			if fly_actor.is_flying():
				if fly_actor.request_landing():
					service_message = "Landing (engineered animation)"
			elif fly_actor.request_takeoff():
				service_message = "Flight (engineered animation)"


func _move_fly(delta: float) -> void:
	if walking_demo:
		demo_elapsed += delta
		walking_now = demo_elapsed >= 0.65 and demo_elapsed < 7.5
		if walking_now:
			fly_position.z -= WALKING_DEMO_SPEED * delta
		return
	if animation_demo:
		demo_elapsed += delta
		if demo_elapsed >= 6.2 and not demo_takeoff_started:
			demo_takeoff_started = true
			fly_actor.request_takeoff()
		if demo_elapsed >= 8.5 and not demo_landing_started:
			demo_landing_started = true
			fly_actor.request_landing()
		if demo_elapsed < 0.7 or demo_elapsed >= 9.5:
			walking_now = false
			return
	if fly_actor.is_recovering():
		walking_now = false
		return
	if feeding_now:
		walking_now = false
		return
	if taste_wait_s > 0.0:
		taste_wait_s -= delta
		walking_now = false
		if taste_wait_s <= 0.0:
			roam_enabled = true
			roam_goal = fly_position
			service_message = "No feeding response; roaming again"
		return
	if pursuit_enabled:
		var walk_speed := PURSUIT_WALK_SPEED
		if beacon_mode:
			var to_target := target_position - fly_position
			to_target.y = 0.0
			if to_target.length() < BEACON_REACHED_M:
				_end_beacon()
				if sugar_active and fly_position.distance_to(sugar_position) < 1.0:
					# Engineered pause at the drop so taste input can reach the brain;
					# whether the fly then feeds is decided by MN9.
					roam_enabled = false
					taste_wait_s = TASTE_WAIT_S
					service_message = "Tasting..."
				walking_now = false
				return
			var bearing := wrapf(atan2(to_target.x, -to_target.z) - heading_rad, -PI, PI)
			if absf(bearing) > deg_to_rad(65.0):
				# Outside the 65-degree view the neural input is silent, so an
				# engineered search turn brings the target into view first.
				heading_rad = wrapf(heading_rad + signf(bearing) * SEARCH_TURN_RATE * delta, -PI, PI)
				walking_now = false
				return
			walk_speed = BEACON_WALK_SPEED
		heading_rad = wrapf(heading_rad + steering_turn_rate * delta, -PI, PI)
		var forward := Vector3(sin(heading_rad), 0.0, -cos(heading_rad))
		fly_position.x = clampf(fly_position.x + forward.x * walk_speed * delta,
			-ROOM_HALF_SIZE, ROOM_HALF_SIZE)
		fly_position.z = clampf(fly_position.z + forward.z * walk_speed * delta,
			-ROOM_HALF_SIZE, ROOM_HALF_SIZE)
		walking_now = true
		return
	if roam_enabled and not _manual_keys_pressed():
		_move_fly_autonomously(delta)
		return
	var movement := Vector2.ZERO
	if Input.is_key_pressed(KEY_W):
		movement.y -= 1.0
	if Input.is_key_pressed(KEY_S):
		movement.y += 1.0
	if Input.is_key_pressed(KEY_A):
		movement.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		movement.x += 1.0
	walking_now = movement.length_squared() > 0.0
	if walking_now:
		movement = movement.normalized()
		fly_position.x = clampf(fly_position.x + movement.x * WALK_SPEED * delta, -ROOM_HALF_SIZE, ROOM_HALF_SIZE)
		fly_position.z = clampf(fly_position.z + movement.y * WALK_SPEED * delta, -ROOM_HALF_SIZE, ROOM_HALF_SIZE)
		heading_rad = atan2(movement.x, -movement.y)


func _manual_keys_pressed() -> bool:
	return Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_A) \
		or Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_D)


func _move_fly_autonomously(delta: float) -> void:
	var to_goal := roam_goal - fly_position
	if to_goal.length() < 0.7 or absf(fly_position.x) > 7.0 or absf(fly_position.z) > 7.0:
		roam_goal = Vector3(roam_rng.randf_range(-5.5, 5.5), 0.0,
			roam_rng.randf_range(-5.5, 5.5))
		to_goal = roam_goal - fly_position
	var desired_heading := atan2(to_goal.x, -to_goal.z)
	heading_rad = lerp_angle(heading_rad, desired_heading, clampf(delta * 2.8, 0.0, 1.0))
	var forward := Vector3(sin(heading_rad), 0.0, -cos(heading_rad))
	var speed := FLIGHT_ROAM_SPEED if fly_actor.is_flying() else ROAM_SPEED
	fly_position.x = clampf(fly_position.x + forward.x * speed * delta,
		-ROOM_HALF_SIZE, ROOM_HALF_SIZE)
	fly_position.z = clampf(fly_position.z + forward.z * speed * delta,
		-ROOM_HALF_SIZE, ROOM_HALF_SIZE)
	walking_now = true


func _move_ball(delta: float) -> void:
	if not ball_active:
		return
	if roam_enabled or beacon_mode:
		# A roaming fly keeps moving, so the thrown object homes in on it;
		# otherwise a straight throw would usually miss and never loom.
		var toward := fly_position + Vector3(0.0, 0.55, 0.0) - ball_position
		if toward.length() > 0.001:
			ball_velocity = toward.normalized() * BALL_SPEED
	ball_position += ball_velocity * delta
	if ball_position.distance_to(fly_position + Vector3(0.0, 0.55, 0.0)) < 0.25:
		ball_active = false
	elif ball_position.length() > 20.0:
		ball_active = false


func _move_target(delta: float) -> void:
	if not pursuit_enabled or beacon_mode:
		return
	pursuit_time += delta
	if steering_model == "activity_v1":
		if pursuit_path == "step_hold":
			target_position.x = -1.8 if pursuit_time < 2.0 else 1.8
		else:
			target_position.x = 1.8 * sin(0.8 * pursuit_time + 0.3) + 0.6 * sin(2.2 * pursuit_time - 0.7)
		target_position.z = -7.0
	else:
		target_position.x = 3.2 * sin(pursuit_time * 0.62 - 1.2)
		target_position.z = -6.5


func _advance_experimental(delta: float) -> float:
	if session_id.is_empty():
		walking_now = false
		return 0.0
	# Rendering may slow under load; preserve 10 ms simulation ticks and the
	# command queue rather than enlarge neural timesteps or drop HTTP requests.
	step_clock += minf(delta, 0.1)
	var advanced := 0.0
	while step_clock >= 0.01 and not session_id.is_empty():
		_move_fly(0.01)
		_move_ball(0.01)
		_move_target(0.01)
		var response := bridge.step_fixed(session_id,
			{"x": fly_position.x, "z": fly_position.z, "heading_rad": heading_rad},
			{"x": ball_position.x, "z": ball_position.z, "radius": BALL_RADIUS, "active": ball_active},
			{"x": target_position.x, "z": target_position.z, "active": true})
		if response.is_empty():
			break
		_on_step_ready(response)
		fly_actor.rotation.y = -heading_rad
		step_clock -= 0.01
		advanced += 0.01
		if record_ticks:
			print("PURSUIT_TICK ", JSON.stringify({"model": steering_model,
				"condition": condition, "time_s": pursuit_time, "fly_x": fly_position.x,
				"fly_z": fly_position.z, "heading_rad": heading_rad,
				"target_x": target_position.x,
				"facing_travel_dot": (-fly_actor.global_transform.basis.z).normalized().dot(Vector3(sin(heading_rad), 0.0, -cos(heading_rad))),
				"steering": response.get("steering", {})}))
		if pursuit_seconds > 0.0 and pursuit_time >= pursuit_seconds - 0.000001:
			get_tree().quit()
			break
	return advanced


func _request_jump(source: String) -> void:
	if fly_actor.request_jump():
		service_message = source


func _launch_ball() -> void:
	var forward := Vector3(sin(heading_rad), 0.0, -cos(heading_rad))
	ball_position = fly_position + forward * 7.0 + Vector3(0.0, 0.55, 0.0)
	ball_velocity = -forward * BALL_SPEED
	ball_active = true
	service_message = "Approaching object launched"


func _start_session() -> void:
	if beacon_mode:
		beacon_mode = false
		pursuit_enabled = false
		roam_enabled = true
	session_id = ""
	last_trace = {}
	step_clock = 0.0
	steering_turn_rate = 0.0
	pursuit_time = 0.0
	target_position = Vector3(-2.9, 0.45, -6.5)
	fly_position = Vector3.ZERO
	heading_rad = 0.0
	fly_actor.position = Vector3.ZERO
	fly_actor.rotation.y = 0.0
	fly_actor.reset_actor()
	ball_active = false
	sugar_active = false
	sugar_eaten_s = 0.0
	taste_wait_s = 0.0
	feeding_now = false
	service_message = "Starting %s neural session..." % condition
	bridge.start_session(condition, steering_model)


func _on_session_ready(payload: Dictionary) -> void:
	session_id = str(payload.get("session_id", ""))
	service_message = "Neural session ready: %s" % condition


func _on_step_ready(payload: Dictionary) -> void:
	last_trace = payload
	if brain_view != null:
		brain_view.update_trace(payload)
	var steering: Dictionary = payload.get("steering", {})
	steering_turn_rate = float(steering.get("turn_rate_rad_s", 0.0)) if pursuit_enabled else 0.0
	if bool(payload.get("jump", false)):
		_request_jump("DNp01 spike triggered jump")
	var was_feeding := feeding_now
	feeding_now = bool(payload.get("feeding", false))
	if feeding_now and not was_feeding:
		taste_wait_s = 0.0
		service_message = "MN9 firing: feeding"
	elif was_feeding and not feeding_now:
		roam_enabled = true
		roam_goal = fly_position
		service_message = "Stopped feeding; roaming again"


func _on_bridge_failed(message: String) -> void:
	session_id = ""
	service_message = message + " | start Python service, then press R"


func _update_hud() -> void:
	status_label.text = "FLY CREATURE  /  %s  /  %s\n%s" % [condition.to_upper(), steering_model.to_upper(), service_message]
	var steering: Dictionary = last_trace.get("steering", {})
	var bearing_text := "%.1f" % float(steering["bearing_deg"]) if steering.has("bearing_deg") else "--"
	var turn_text := "%.2f" % float(steering["turn_rate_rad_s"]) if steering.has("turn_rate_rad_s") else "--"
	var line := "Target bearing %s deg   neural turn %s rad/s" % [bearing_text, turn_text]
	if last_trace.has("brain_neurons"):
		line += "   |   brain step %s ms per 50 ms" % last_trace.get("compute_ms", "--")
	detail_label.text = "Fly roams on its own  |  LEFT-CLICK: target  |  RIGHT-CLICK: sugar drop  |  SPACE: throw object  |  C: cut wiring\n" \
		+ "WASD take over  |  V moving target  |  B brain model  |  G roam  |  T fly  |  F camera  |  R reset  |  P playground\n" \
		+ line + "\n" \
		+ "Senses, action rules, walking and animation are engineered; wiring is MaleCNS data."


func _build_world() -> void:
	# Kitchen-table set dressing; presentation only (see kitchen_world.gd).
	add_child(KitchenWorldScript.new())
	camera = Camera3D.new()
	camera.position = Vector3(2.8, 2.2, 3.5)
	camera.fov = 47.0
	add_child(camera)
	camera.look_at(Vector3(0.0, 0.25, -1.0), Vector3.UP)
	camera.current = true


func _update_camera(delta: float) -> void:
	if walking_demo:
		# Partial tracking lets the fly travel across the shot head-first.
		var track_z := fly_position.z * 0.6
		var desired := Vector3(2.6, 1.05, track_z + 0.85)
		camera.position = camera.position.lerp(desired, clampf(delta * 4.0, 0.0, 1.0))
		camera.look_at(Vector3(0.0, 0.26, track_z - 0.20), Vector3.UP)
		return
	if pursuit_enabled and not close_camera:
		var desired := fly_position + Vector3(0.0, 5.2, 5.6)
		camera.position = camera.position.lerp(desired, clampf(delta * 3.5, 0.0, 1.0))
		camera.look_at(fly_position + Vector3(0.0, 0.0, -2.8), Vector3.UP)
		return
	if close_camera:
		var forward := Vector3(sin(heading_rad), 0.0, -cos(heading_rad))
		var right := Vector3(-forward.z, 0.0, forward.x)
		var back_distance := 2.3 if animation_demo else 3.5
		var side_distance := 1.7 if animation_demo else 2.8
		var camera_height := 1.45 if animation_demo else 2.2
		var desired := fly_position - forward * back_distance + right * side_distance \
			+ Vector3(0.0, camera_height, 0.0)
		camera.position = camera.position.lerp(desired, clampf(delta * 5.0, 0.0, 1.0))
		var look_ahead := 0.45 if animation_demo else 1.0
		camera.look_at(fly_position + forward * look_ahead + Vector3(0.0, 0.25, 0.0), Vector3.UP)
	else:
		var desired := fly_position + Vector3(0.0, 10.0, 12.0)
		camera.position = camera.position.lerp(desired, clampf(delta * 3.0, 0.0, 1.0))
		camera.look_at(fly_position + Vector3(0.0, 0.0, -2.0), Vector3.UP)


func _build_ball() -> void:
	ball_root = Node3D.new()
	add_child(ball_root)
	_sphere(ball_root, Vector3.ZERO, Vector3.ONE * BALL_RADIUS, Color(0.95, 0.30, 0.23))
	ball_root.visible = false


func _build_sugar() -> void:
	sugar_root = Node3D.new()
	add_child(sugar_root)
	var mesh := SphereMesh.new()
	mesh.radius = SUGAR_RADIUS
	mesh.height = SUGAR_RADIUS * 1.1
	var drop := MeshInstance3D.new()
	drop.mesh = mesh
	drop.position.y = SUGAR_RADIUS * 0.3
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(1.0, 0.86, 0.55, 0.78)
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.roughness = 0.08
	drop.material_override = material
	sugar_root.add_child(drop)
	sugar_root.visible = false


func _build_target() -> void:
	target_root = Node3D.new()
	add_child(target_root)
	_sphere(target_root, Vector3.ZERO, Vector3.ONE * 0.19, Color(0.20, 0.96, 0.72))
	target_root.visible = false


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
	detail_panel.position = Vector2(22.0, get_viewport().get_visible_rect().size.y - 122.0)
	detail_panel.custom_minimum_size = Vector2(880.0, 100.0)
	layer.add_child(detail_panel)
	detail_label = Label.new()
	detail_label.add_theme_font_size_override("font_size", 16)
	detail_panel.add_child(detail_label)
	brain_view = BrainViewScript.new()
	layer.add_child(brain_view)
	var place_brain := func() -> void:
		brain_view.position = Vector2(get_viewport().get_visible_rect().size.x - BrainViewScript.PANEL_WIDTH - 22.0, 20.0)
	place_brain.call()
	get_viewport().size_changed.connect(place_brain)
