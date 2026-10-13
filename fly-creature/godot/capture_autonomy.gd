extends SceneTree

# Scripted check of the self-roaming fly, click-placed target, thrown object,
# feeding, courtship song, antennal grooming, a bitter drop and the live brain view. Needs a
# graphics-enabled Godot and a running neural service.
# Frames and telemetry go to the folder in FLY_CREATURE_CAPTURE_DIR.

var scene: Node3D
var song_seen := false
var song_side_seen := ""
var song_seen_ms := 0
var song_snapped := false


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
		if scene != null and scene.singing_now and not song_seen:
			song_seen = true
			song_side_seen = scene.song_side
			song_seen_ms = Time.get_ticks_msec()
		if song_seen and not song_snapped and scene.singing_now \
				and Time.get_ticks_msec() - song_seen_ms > 400:
			# Let the wing swing out, then take the game view and a top view.
			song_snapped = true
			_snap("5_singing")
			var follow: bool = scene.close_camera
			var saved: Transform3D = scene.camera.transform
			scene.close_camera = false
			scene.set_process(false)
			scene.camera.position = scene.fly_position + Vector3(0.0, 2.6, 0.01)
			scene.camera.look_at(scene.fly_position, Vector3.FORWARD)
			await process_frame
			await process_frame
			_snap("5_singing_top")
			scene.camera.transform = saved
			scene.close_camera = follow
			scene.set_process(true)


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
	await _wait(1.0)
	print("CHECK song_seen=", song_seen, " side=", song_side_seen,
		" singing_after_target=", scene.singing_now)
	# Sugar: drop it a little ahead of the fly and let the fly walk to it.
	var ahead := Vector3(sin(scene.heading_rad), 0.0, -cos(scene.heading_rad)) * 2.0
	var drop: Vector3 = scene.fly_position + ahead
	scene.place_sugar(drop)
	scene.place_beacon(drop)
	var fed := false
	var end_feed := Time.get_ticks_msec() + 15000
	while Time.get_ticks_msec() < end_feed and not fed:
		await process_frame
		fed = scene.feeding_now
	print("CHECK feeding_started=", fed, " mn9_hz=", scene.last_trace.get("mn9_rate_hz", "--"),
		" taste_contact=", scene.last_trace.get("taste", {}).get("contact", "--"))
	await _wait(1.5)
	_snap("6_feeding")
	# Close side view of the mouthparts while feeding.
	scene.close_camera = false
	var head: Vector3 = scene.fly_position + Vector3(sin(scene.heading_rad), 0.0, -cos(scene.heading_rad)) * 0.35
	scene.camera.position = head + Vector3(cos(scene.heading_rad), 0.25, sin(scene.heading_rad)) * 1.2
	scene.camera.look_at(head + Vector3(0.0, 0.15, 0.0), Vector3.UP)
	scene.set_process(false)
	await _wait(0.3)
	_snap("7_mouth_closeup")
	scene.set_process(true)
	print("CHECK brain_compute_ms=", scene.last_trace.get("compute_ms", "--"),
		" active_neurons=", scene.last_trace.get("active_neurons", "--"))
	scene.close_camera = true
	var end_meal := Time.get_ticks_msec() + 8000
	while Time.get_ticks_msec() < end_meal and scene.feeding_now:
		await process_frame
	await _wait(1.0)
	# Grooming: dust the antennae (the E key) and wait for the brain to groom.
	scene.antenna_dust = 1.0
	var groomed := false
	var end_groom := Time.get_ticks_msec() + 6000
	while Time.get_ticks_msec() < end_groom and not groomed:
		await process_frame
		groomed = scene.grooming_now
	print("CHECK grooming_started=", groomed, " adn_hz=", scene.last_trace.get("adn_rate_hz", "--"))
	await _wait(0.5)
	_snap("8_grooming")
	scene.close_camera = false
	head = scene.fly_position + Vector3(sin(scene.heading_rad), 0.0, -cos(scene.heading_rad)) * 0.35
	scene.camera.position = head + Vector3(sin(scene.heading_rad) * 1.1 + cos(scene.heading_rad) * 0.55,
		0.3, -cos(scene.heading_rad) * 1.1 + sin(scene.heading_rad) * 0.55)
	scene.camera.look_at(head + Vector3(0.0, 0.12, 0.0), Vector3.UP)
	scene.set_process(false)
	await _wait(0.3)
	_snap("9_grooming_closeup")
	scene.set_process(true)
	scene.close_camera = true
	var end_clean := Time.get_ticks_msec() + 8000
	while Time.get_ticks_msec() < end_clean and (scene.grooming_now or scene.antenna_dust > 0.0):
		await process_frame
	print("CHECK grooming_stopped=", not scene.grooming_now, " dust=", snappedf(scene.antenna_dust, 0.01))
	# Bitter drop: the same approach, but the drop is laced with something bitter.
	await _wait(1.0)
	ahead = Vector3(sin(scene.heading_rad), 0.0, -cos(scene.heading_rad)) * 2.0
	drop = scene.fly_position + ahead
	scene.place_sugar(drop, true)
	scene.place_beacon(drop)
	var bitter_contact := false
	var bitter_fed := false
	var end_bitter := Time.get_ticks_msec() + 12000
	while Time.get_ticks_msec() < end_bitter:
		await process_frame
		bitter_contact = bitter_contact or bool(scene.last_trace.get("taste", {}).get("bitter", false))
		bitter_fed = bitter_fed or scene.feeding_now
		if bitter_contact and scene.taste_wait_s <= 0.0 and not scene.beacon_mode:
			break
	_snap("10_bitter_drop")
	print("CHECK bitter_contact=", bitter_contact, " bitter_fed=", bitter_fed,
		" mn9_hz=", scene.last_trace.get("mn9_rate_hz", "--"))
	quit()
