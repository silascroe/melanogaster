extends SceneTree

# Scripted check of the female-fly mode (the M key): the male follows the
# wandering female and sings, first with intact wiring, then with the brain's
# connections cut as the control. Needs a graphics-enabled Godot and a running
# neural service. Frames go to the folder in FLY_CREATURE_CAPTURE_DIR.

const RUN_S := 30.0
# Fixed seeds for the female's random walk, so runs are repeatable.
const SEEDS := [11, 22, 33]

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


## Watch one condition for RUN_S seconds and print a summary line.
func _watch(label: String, snap_prefix: String) -> void:
	var frames := 0
	var singing_frames := 0
	var sides := {}
	var distance_sum := 0.0
	var distance_max := 0.0
	var snapped := false
	var sing_start := -1
	var start := Time.get_ticks_msec()
	var next_log := start
	while Time.get_ticks_msec() - start < int(RUN_S * 1000.0):
		await process_frame
		var distance: float = scene.fly_position.distance_to(scene.female_position)
		frames += 1
		distance_sum += distance
		distance_max = maxf(distance_max, distance)
		if scene.singing_now:
			singing_frames += 1
			sides[scene.song_side] = true
			if sing_start < 0:
				sing_start = Time.get_ticks_msec()
			# Snap a song that has lasted 400 ms, so the wing is fully out.
			if not snapped and snap_prefix != "" and Time.get_ticks_msec() - sing_start > 400:
				snapped = true
				await _snap_both(snap_prefix)
		else:
			sing_start = -1
		if Time.get_ticks_msec() >= next_log:
			next_log += 2000
			print("TICK ", label, " t=", snappedf((Time.get_ticks_msec() - start) / 1000.0, 0.1),
				" dist=", snappedf(distance, 0.01),
				" bearing=", scene.last_trace.get("steering", {}).get("bearing_deg", "--"),
				" pip10_hz=", scene.last_trace.get("pip10_rate_hz", "--"),
				" singing=", scene.singing_now, " walking=", scene.walking_now)
	print("CHECK ", label, " singing_fraction=", snappedf(float(singing_frames) / maxf(frames, 1), 0.01),
		" sides=", sides.keys(), " mean_dist=", snappedf(distance_sum / maxf(frames, 1), 0.01),
		" max_dist=", snappedf(distance_max, 0.01))


## The game view, then a top view of both flies.
func _snap_both(prefix: String) -> void:
	_snap(prefix + "_game")
	var follow: bool = scene.close_camera
	var saved: Transform3D = scene.camera.transform
	scene.close_camera = false
	scene.set_process(false)
	var middle: Vector3 = (scene.fly_position + scene.female_position) * 0.5
	var span: float = scene.fly_position.distance_to(scene.female_position)
	scene.camera.position = middle + Vector3(0.0, maxf(3.0, span * 1.9 + 1.5), 0.01)
	scene.camera.look_at(middle, Vector3.FORWARD)
	await process_frame
	await process_frame
	_snap(prefix + "_top")
	scene.camera.transform = saved
	scene.close_camera = follow
	scene.set_process(true)


func _run() -> void:
	scene = (load("res://main.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(scene)
	current_scene = scene
	await _wait_session()
	_press(KEY_M)
	await _wait_session()
	print("CHECK female_mode=", scene.female_mode, " female_visible=", scene.female_actor.visible)
	for condition in ["intact", "disconnected"]:
		if scene.condition != condition:
			_press(KEY_C)  # cut (or restore) the brain's wiring; female mode stays on
		for seed in SEEDS:
			_press(KEY_R)
			scene.roam_rng.seed = seed
			await _wait_session()
			var first: bool = seed == SEEDS[0]
			await _watch("%s seed=%d" % [condition, seed],
				"11_female_song" if first and condition == "intact" else "")
			if first:
				_snap("12_female_follow" if condition == "intact" else "13_female_cut")
	quit()
