extends SceneTree

# Scripted check of the self-roaming fly, click-placed target, thrown object and
# live brain view. Needs a graphics-enabled Godot and a running neural service.
# Frames and telemetry go to the folder in FLY_CREATURE_CAPTURE_DIR.

var scene: Node3D


func _initialize() -> void:
	call_deferred("_run")


func _snap(name: String) -> void:
	var image := root.get_texture().get_image()
	var folder := OS.get_environment("FLY_CREATURE_CAPTURE_DIR")
	image.save_png(folder.path_join(name + ".png"))


func _wait(seconds: float) -> void:
	var end := Time.get_ticks_msec() + int(seconds * 1000.0)
	while Time.get_ticks_msec() < end:
		await process_frame


func _telemetry(label: String) -> void:
	print("CHECK ", label, " fly=(", snappedf(scene.fly_position.x, 0.01), ",",
		snappedf(scene.fly_position.z, 0.01), ") heading_deg=",
		snappedf(rad_to_deg(scene.heading_rad), 0.1), " roam=", scene.roam_enabled,
		" beacon=", scene.beacon_mode, " turn_rate=", snappedf(scene.steering_turn_rate, 0.001),
		" session=", not scene.session_id.is_empty())


func _run() -> void:
	var packed: PackedScene = load("res://main.tscn") as PackedScene
	scene = packed.instantiate() as Node3D
	root.add_child(scene)
	current_scene = scene
	await _wait(2.5)
	_telemetry("start")
	var start_position: Vector3 = scene.fly_position
	await _wait(4.0)
	_telemetry("roaming")
	print("CHECK roamed_distance=", snappedf(scene.fly_position.distance_to(start_position), 0.01))
	_snap("1_roaming")
	scene._launch_ball()
	var jumped := false
	var end := Time.get_ticks_msec() + 12000
	while Time.get_ticks_msec() < end and not jumped:
		await process_frame
		jumped = scene.fly_actor.is_recovering()
	print("CHECK jump_started=", jumped)
	await _wait(0.4)
	_snap("2_jump")
	await _wait(2.5)
	scene.place_beacon(scene.fly_position + Vector3(2.5, 0.0, -3.0))
	_telemetry("beacon placed")
	await _wait(1.2)
	_snap("3_beacon_start")
	for index in range(6):
		await _wait(1.5)
		_telemetry("beacon %d" % index)
		if not scene.beacon_mode:
			break
	_snap("4_after_beacon")
	print("CHECK beacon_ended=", not scene.beacon_mode)
	scene.close_camera = false
	await _wait(2.0)
	_snap("5_wide")
	quit()
