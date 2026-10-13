extends SceneTree

# Scripted check of backing up (the O key): a sugar cube is placed in the
# roaming fly's path, first with intact wiring, then with the brain's
# connections cut as the control. Needs a graphics-enabled Godot and a running
# neural service. Frames go to the folder in FLY_CREATURE_CAPTURE_DIR.

const TRIALS := 3
const TRIAL_S := 8.0

var scene: Node3D


func _initialize() -> void:
	call_deferred("_run")


func _snap(name: String) -> void:
	var image := root.get_texture().get_image()
	image.save_png(OS.get_environment("FLY_CREATURE_CAPTURE_DIR").path_join(name + ".png"))


func _press(keycode: Key) -> void:
	var event := InputEventKey.new()
	event.keycode = keycode
	event.pressed = true
	scene._unhandled_key_input(event)


func _wait_session() -> void:
	var end := Time.get_ticks_msec() + 15000
	while Time.get_ticks_msec() < end and scene.session_id.is_empty():
		await process_frame


## Side view of the fly and the cube.
func _snap_side(name: String) -> void:
	var follow: bool = scene.close_camera
	var saved: Transform3D = scene.camera.transform
	scene.close_camera = false
	scene.set_process(false)
	var middle: Vector3 = (scene.fly_position + scene.obstacle_position) * 0.5
	var along: Vector3 = (scene.obstacle_position - scene.fly_position).normalized()
	var side := Vector3(-along.z, 0.0, along.x)
	scene.camera.position = middle + side * 2.6 + Vector3(0.0, 0.9, 0.0)
	scene.camera.look_at(middle + Vector3(0.0, 0.25, 0.0), Vector3.UP)
	await process_frame
	await process_frame
	_snap(name)
	scene.camera.transform = saved
	scene.close_camera = follow
	scene.set_process(true)


func _trial(label: String, snap_prefix: String) -> void:
	_press(KEY_R)
	await _wait_session()
	_press(KEY_O)
	var start := Time.get_ticks_msec()
	var contact_ms := -1
	var backing_ms := -1
	var back_from := 0.0
	var backed := 0.0
	var turned := false
	var gave_up := false
	var snapped := false
	while Time.get_ticks_msec() - start < int(TRIAL_S * 1000.0):
		await process_frame
		var gap: float = scene.fly_position.distance_to(scene.obstacle_position)
		if scene.forelegs_pressed and contact_ms < 0:
			contact_ms = Time.get_ticks_msec()
		if scene.reversing:
			if backing_ms < 0:
				backing_ms = Time.get_ticks_msec()
				back_from = gap
			backed = maxf(backed, gap - back_from)
			if not snapped and snap_prefix != "" and Time.get_ticks_msec() - backing_ms > 250:
				snapped = true
				_snap(snap_prefix + "_game")
				await _snap_side(snap_prefix + "_side")
		if scene.turning_away and not turned:
			turned = true
			gave_up = backing_ms < 0
			if gave_up and snap_prefix != "":
				_snap(snap_prefix + "_gave_up")
		if turned and not scene.turning_away and not scene.reversing:
			break
	print("CHECK ", label, " contact=", contact_ms >= 0,
		" backed_up=", backing_ms >= 0,
		" onset_s=", snappedf((backing_ms - contact_ms) / 1000.0, 0.01) if backing_ms >= 0 and contact_ms >= 0 else "--",
		" backed_m=", snappedf(backed, 0.01), " turned_away=", turned, " gave_up=", gave_up)


func _run() -> void:
	scene = (load("res://main.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(scene)
	current_scene = scene
	await _wait_session()
	for condition in ["intact", "disconnected"]:
		if scene.condition != condition:
			_press(KEY_C)
		for trial in TRIALS:
			var prefix := ""
			if trial == 0:
				prefix = "14_backup" if condition == "intact" else "15_cut"
			await _trial("%s trial=%d" % [condition, trial], prefix)
	quit()
