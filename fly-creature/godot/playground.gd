extends Node3D

signal snapshot_ready

const MODES := ["intact", "disconnected", "ordinary_delayed", "ordinary_immediate"]
const NAMES := ["Intact connectome", "Disconnected", "Ordinary / 200 ms", "Ordinary / no delay"]
const PRESETS := ["gentle", "fast", "reversal", "dropout", "reentry", "stationary", "manual"]
const PRESET_NAMES := ["Gentle following", "Fast lateral motion", "Repeated reversals", "Brief disappearance", "Reappear elsewhere", "Stationary depth", "Move target yourself"]
const COLORS := [Color("55d6bb"), Color("efb85b"), Color("78aaff"), Color("d39af5")]
const FLY := preload("res://fly_actor.tscn")

var request: HTTPRequest
var endpoint := "http://127.0.0.1:8768"
var world_id := ""
var pending := ""
var queued_restart := false
var sequence := 0
var clock := 0.0
var paused := false
var hidden_target := false
var mirrored := false
var preset := "gentle"
var depth := 6.0
var initial_heading := 0.0
var manual_target := Vector2(1.5, -6.0)
var snapshot: Dictionary = {}
var focus := 0
var close_view := false
var dragging := false
var camera: Camera3D
var actor: FlyActor
var target_mesh: MeshInstance3D
var markers: Array[MeshInstance3D] = []
var trails: Array[ImmediateMesh] = []
var points: Array = [[], [], [], []]
var cards: Array[Label] = []
var preset_picker: OptionButton
var focus_picker: OptionButton
var pause_button: Button
var hide_button: Button
var reset_button: Button
var title_label: Label
var hint_label: Label
var request_started := 0
var latencies: Array[float] = []
var last_trace_tick := -1
var fail_message := ""
var auto_seconds := 0.0
var record_trace := false


func _ready() -> void:
	var configured := OS.get_environment("FLY_CREATURE_ENDPOINT")
	if not configured.is_empty(): endpoint = configured.trim_suffix("/")
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--playground-preset="): preset = argument.trim_prefix("--playground-preset=")
		if argument.begins_with("--playground-seconds="): auto_seconds = float(argument.trim_prefix("--playground-seconds="))
	record_trace = OS.get_cmdline_user_args().has("--playground-trace")
	request = HTTPRequest.new()
	request.timeout = 10
	request.use_threads = true
	add_child(request)
	request.request_completed.connect(_completed)
	_build_world()
	_build_ui()
	_restart()


func _process(delta: float) -> void:
	if not paused and not world_id.is_empty() and fail_message.is_empty() and not snapshot.get("done", false):
		clock += delta
		if pending.is_empty() and clock >= .01:
			var ticks := mini(5, int(floor(clock / .01)))
			clock -= ticks * .01
			sequence += 1
			_send("/playground/%s/step" % world_id, {"ticks": ticks, "sequence": sequence,
				"target_enabled": not hidden_target,
				"manual_target": {"x": manual_target.x, "z": manual_target.y}}, "step")
	if snapshot.has("models"):
		var body: Dictionary = snapshot.models[MODES[focus]]
		actor.position = Vector3(body.x, 0, body.z)
		actor.rotation.y = -float(body.heading_rad)
		actor.advance(delta if not paused and not snapshot.done else 0.0,
			not paused and not snapshot.done and not world_id.is_empty(), .55)
		var offset := Vector3(2.8, 2.2, 3.5) if close_view else Vector3(4.5, 8.0, 9.0)
		if not dragging:
			camera.position = camera.position.lerp(actor.position + offset, minf(delta * 4, 1))
			camera.look_at(actor.position + Vector3(0, .2, -2.8 if not close_view else -.5))
	_update_ui()


func _send(path: String, payload: Dictionary, kind: String) -> void:
	pending = kind
	request_started = Time.get_ticks_usec()
	var error := request.request(endpoint + path, PackedStringArray(["Content-Type: application/json"]), HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		pending = ""
		fail_message = "Connection failed. Start Python, then Reset."


func _restart() -> void:
	world_id = ""
	clock = 0
	sequence = 0
	fail_message = ""
	if not pending.is_empty():
		queued_restart = true
		return
	queued_restart = false
	snapshot = {}
	points = [[], [], [], []]
	last_trace_tick = -1
	for mesh in trails: mesh.clear_surfaces()
	actor.reset_actor()
	_send("/playground", {"preset": preset, "depth": depth,
		"heading_deg": initial_heading, "mirror": mirrored,
		"target_enabled": not hidden_target,
		"manual_target": {"x": manual_target.x, "z": manual_target.y}}, "create")


func _completed(result: int, code: int, _headers: PackedStringArray, bytes: PackedByteArray) -> void:
	var kind := pending
	pending = ""
	if queued_restart:
		_restart()
		return
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		var error_payload: Variant = JSON.parse_string(bytes.get_string_from_utf8())
		fail_message = str(error_payload.get("error", "Service unavailable")) if error_payload is Dictionary else "Service unavailable"
		fail_message += ". Reset to reconnect."
		world_id = ""
		return
	var payload: Variant = JSON.parse_string(bytes.get_string_from_utf8())
	if not payload is Dictionary or not payload.has("models"):
		fail_message = "Invalid service response. Reset to reconnect."
		world_id = ""
		return
	if kind == "step" and (payload.world_id != world_id or payload.sequence != sequence):
		fail_message = "Stale comparison response. Reset to reconnect."
		world_id = ""
		return
	if kind == "create": world_id = payload.world_id
	if kind == "step":
		latencies.append((Time.get_ticks_usec() - request_started) / 1000.0)
		payload["roundtrip_ms"] = latencies.back()
		if latencies.size() > 120: latencies.pop_front()
	snapshot = payload
	_render_snapshot()
	if record_trace: print("PLAYGROUND_SNAPSHOT ", JSON.stringify(snapshot))
	snapshot_ready.emit()
	if auto_seconds > 0 and float(snapshot.time_s) >= auto_seconds:
		get_tree().quit()


func _render_snapshot() -> void:
	target_mesh.position = Vector3(snapshot.target.x, .45, snapshot.target.z)
	target_mesh.visible = snapshot.target.active
	for i in range(4):
		var body: Dictionary = snapshot.models[MODES[i]]
		markers[i].position = Vector3(body.x, .08, body.z)
		markers[i].visible = i != focus
		if snapshot.tick == 0 or snapshot.tick - last_trace_tick >= 5:
			points[i].append(Vector3(body.x, .025, body.z))
			trails[i].clear_surfaces()
			if points[i].size() >= 2:
				trails[i].surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
				trails[i].surface_set_color(COLORS[i])
				for point in points[i]: trails[i].surface_add_vertex(point)
				trails[i].surface_end()
	if snapshot.tick == 0 or snapshot.tick - last_trace_tick >= 5: last_trace_tick = snapshot.tick


func _update_ui() -> void:
	if not fail_message.is_empty():
		title_label.text = fail_message
		return
	var state := "Paused" if paused else "Complete — Reset to replay" if snapshot.get("done", false) else "Running"
	var latency := 0.0
	for value in latencies: latency += value
	latency /= maxf(1, latencies.size())
	title_label.text = "%s  /  %.2f s of 10 s\nInspecting: %s" % [state, snapshot.get("time_s", 0), NAMES[focus]]
	hint_label.text = "Click/drag the floor in Manual mode.\nColored trails and dots show other bodies.\nRequest %.1f ms  /  backlog %.0f ms\nWalking is authored; only steering is compared." % [latency, clock * 1000]
	if not snapshot.has("models"): return
	for i in range(4):
		var body: Dictionary = snapshot.models[MODES[i]]
		var steering: Dictionary = body.steering
		var error_text := "—" if body.mean_error_deg == null else "%.2f°" % body.mean_error_deg
		var view_text := "—" if body.visible_fraction == null else "%.0f%%" % (body.visible_fraction * 100)
		var seen := "VISIBLE" if steering.get("in_view", false) else "UNSEEN / HIDDEN"
		cards[i].text = "%s\nMean error %s  /  seen %s\n%s  /  turn %.3f rad/s" % [NAMES[i], error_text, view_text, seen, steering.get("turn_rate_rad_s", 0)]


func _pause() -> void:
	paused = not paused
	clock = 0
	pause_button.text = "Resume" if paused else "Pause"


func _select_preset(index: int) -> void:
	preset = PRESETS[index]
	_restart()


func _select_focus(index: int) -> void:
	focus = index
	actor.reset_actor()
	if snapshot.has("models"): _render_snapshot()


func _toggle_target() -> void:
	hidden_target = not hidden_target
	hide_button.text = "Show target" if hidden_target else "Hide target"
	target_mesh.visible = not hidden_target and snapshot.get("target", {}).get("active", false)


func _mirror() -> void:
	mirrored = not mirrored
	if preset == "manual": manual_target.x = -manual_target.x
	_restart()


func _input(event: InputEvent) -> void:
	# Releases over a GUI panel must end a floor drag too.
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and not event.pressed:
		dragging = false
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE and (preset_picker.get_popup().visible or focus_picker.get_popup().visible): return
		if event.keycode == KEY_SPACE: _pause()
		if event.keycode == KEY_R: _restart()
		if event.keycode == KEY_F: close_view = not close_view
		if event.keycode == KEY_ESCAPE: get_tree().change_scene_to_file("res://main.tscn")
		if event.keycode in [KEY_SPACE, KEY_R, KEY_F, KEY_ESCAPE]: get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
	if preset != "manual": return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		dragging = event.pressed
		if dragging: _move_manual(event.position)
	if event is InputEventMouseMotion and dragging: _move_manual(event.position)


func _move_manual(screen: Vector2) -> void:
	var origin := camera.project_ray_origin(screen)
	var direction := camera.project_ray_normal(screen)
	if absf(direction.y) < .0001: return
	var distance := (.45 - origin.y) / direction.y
	if distance <= 0: return
	var hit := origin + direction * distance
	manual_target = Vector2(clampf(hit.x, -30, 30), clampf(hit.z, -30, 30))
	if paused:
		target_mesh.position = Vector3(manual_target.x, .45, manual_target.y)


func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = .7
	return material


func _orb(radius: float, color: Color) -> MeshInstance3D:
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.material_override = _material(color)
	add_child(node)
	return node


func _build_world() -> void:
	actor = FLY.instantiate()
	add_child(actor)
	var floor_mesh := BoxMesh.new()
	floor_mesh.size = Vector3(70, .1, 70)
	var ground := MeshInstance3D.new()
	ground.mesh = floor_mesh
	ground.position.y = -.07
	ground.material_override = _material(Color("283641"))
	add_child(ground)
	var lines := ImmediateMesh.new()
	lines.surface_begin(Mesh.PRIMITIVE_LINES)
	for i in range(-30, 31):
		lines.surface_add_vertex(Vector3(i, -.01, -30))
		lines.surface_add_vertex(Vector3(i, -.01, 30))
		lines.surface_add_vertex(Vector3(-30, -.01, i))
		lines.surface_add_vertex(Vector3(30, -.01, i))
	lines.surface_end()
	var grid := MeshInstance3D.new()
	grid.mesh = lines
	grid.material_override = _material(Color("41535e"))
	add_child(grid)
	for i in range(4):
		markers.append(_orb(.12, COLORS[i]))
		var trail := ImmediateMesh.new()
		trails.append(trail)
		var node := MeshInstance3D.new()
		node.mesh = trail
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.vertex_color_use_as_albedo = true
		node.material_override = material
		add_child(node)
	target_mesh = _orb(.22, Color("a2f56b"))
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -30, 0)
	sun.light_energy = 1.4
	add_child(sun)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(.58, .68, .74)
	environment.environment.ambient_light_energy = .5
	add_child(environment)
	camera = Camera3D.new()
	camera.position = Vector3(4.5, 8, 9)
	camera.fov = 48
	add_child(camera)
	camera.current = true
	camera.look_at(Vector3(0, .2, -2.8))


func _label(text: String, size: int = 16) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	return label


func _button(text: String, parent: Node, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 36
	parent.add_child(button)
	button.pressed.connect(callback)
	return button


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var panel := PanelContainer.new()
	panel.position = Vector2(16, 16)
	panel.custom_minimum_size = Vector2(286, maxf(680, get_viewport().get_visible_rect().size.y - 32))
	var style := StyleBoxFlat.new()
	style.bg_color = Color(.055, .075, .10, .96)
	style.content_margin_left = 16
	style.content_margin_right = 16
	style.content_margin_top = 14
	style.content_margin_bottom = 14
	panel.add_theme_stylebox_override("panel", style)
	layer.add_child(panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 9)
	panel.add_child(box)
	box.add_child(_label("PURSUIT PLAYGROUND", 20))
	box.add_child(_label("Four bodies. One target trajectory.\nChange your view, not the results.", 14))
	box.add_child(_label("Target motion"))
	preset_picker = OptionButton.new()
	for name in PRESET_NAMES: preset_picker.add_item(name)
	preset_picker.select(maxi(0, PRESETS.find(preset)))
	preset_picker.item_selected.connect(_select_preset)
	box.add_child(preset_picker)
	box.add_child(_label("Inspect controller"))
	focus_picker = OptionButton.new()
	for name in NAMES: focus_picker.add_item(name)
	focus_picker.item_selected.connect(_select_focus)
	box.add_child(focus_picker)
	var distance_label := _label("Starting depth: 6.0 m")
	box.add_child(distance_label)
	var distance := HSlider.new()
	distance.min_value = 3
	distance.max_value = 8
	distance.step = .5
	distance.value = depth
	distance.name = "DepthSlider"
	distance.value_changed.connect(func(value): depth = value; distance_label.text = "Starting depth: %.1f m" % value; _restart())
	box.add_child(distance)
	var heading_label := _label("Starting heading: 0°")
	box.add_child(heading_label)
	var heading := HSlider.new()
	heading.min_value = -105
	heading.max_value = 105
	heading.step = 5
	heading.name = "HeadingSlider"
	heading.value_changed.connect(func(value): initial_heading = value; heading_label.text = "Starting heading: %.0f°" % value; _restart())
	box.add_child(heading)
	pause_button = _button("Pause", box, _pause)
	reset_button = _button("Reset / replay", box, _restart)
	hide_button = _button("Hide target", box, _toggle_target)
	_button("Mirror + replay", box, _mirror)
	_button("Close / wide camera", box, func(): close_view = not close_view)
	box.add_child(_label("Space pause  /  R reset  /  F camera\nEsc returns to the creature demo", 13))
	hint_label = _label("", 13)
	hint_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint_label.custom_minimum_size.x = 254
	box.add_child(hint_label)
	box.add_child(_label("Activity is modeled, not measured.\nOrdinary modes contain no neurons.\nNo neural search or stopping behavior.", 13))
	title_label = _label("Connecting…", 20)
	title_label.position = Vector2(330, 22)
	layer.add_child(title_label)
	var scores := GridContainer.new()
	scores.columns = 2
	scores.position = Vector2(330, get_viewport().get_visible_rect().size.y - 225)
	scores.add_theme_constant_override("h_separation", 14)
	scores.add_theme_constant_override("v_separation", 10)
	layer.add_child(scores)
	for i in range(4):
		var card := PanelContainer.new()
		card.custom_minimum_size = Vector2(420, 80)
		var card_style := style.duplicate() as StyleBoxFlat
		card_style.border_width_left = 4
		card_style.border_color = COLORS[i]
		card.add_theme_stylebox_override("panel", card_style)
		scores.add_child(card)
		var label := _label(NAMES[i], 15)
		cards.append(label)
		card.add_child(label)
