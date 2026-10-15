extends SceneTree

# Screenshots of the neuron map (N panel) while each sense's brain copy runs:
# rest, loom (SPACE), sugar, antenna dust (E), obstacle (O), plus frame times.
# Needs a graphics-enabled Godot and a running neural service. Frames go to
# the folder in FLY_CREATURE_CAPTURE_DIR.

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


func _wait(seconds: float) -> Array:
	var end := Time.get_ticks_msec() + int(seconds * 1000.0)
	var frames := []
	var last := Time.get_ticks_usec()
	while Time.get_ticks_msec() < end:
		await process_frame
		var now := Time.get_ticks_usec()
		frames.append((now - last) / 1000.0)
		last = now
	return frames


func _report(label: String, frames: Array) -> void:
	frames.sort()
	var total := 0.0
	for f in frames:
		total += f
	print("FRAMES ", label, " mean_ms=", snappedf(total / frames.size(), 0.1),
		" p95_ms=", snappedf(frames[int(frames.size() * 0.95)], 0.1))


func _run() -> void:
	scene = (load("res://main.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(scene)
	current_scene = scene
	var end := Time.get_ticks_msec() + 20000
	while Time.get_ticks_msec() < end and (scene.session_id.is_empty() or not scene.brain_map.loaded):
		await process_frame
	print("MAP loaded=", scene.brain_map.loaded, " note=", scene.brain_map.note)
	scene.roam_enabled = false
	_report("rest", await _wait(2.0))
	_snap("map_0_rest")
	_press(KEY_SPACE)
	await _wait(1.35)
	_snap("map_1_loom")
	_report("loom", await _wait(1.0))
	await _wait(1.5)
	var forward := Vector3(sin(scene.heading_rad), 0.0, -cos(scene.heading_rad))
	scene.place_sugar(scene.fly_position + forward * 0.4)
	_report("sugar", await _wait(1.5))
	_snap("map_2_sugar")
	scene.sugar_active = false
	await _wait(1.5)
	_press(KEY_E)
	_report("dust", await _wait(1.2))
	_snap("map_3_dust")
	await _wait(3.0)
	_press(KEY_O)
	var deadline := Time.get_ticks_msec() + 8000
	while Time.get_ticks_msec() < deadline and not scene.reversing:
		await process_frame
	await _wait(0.2)
	_snap("map_4_obstacle")
	print("MAP backing=", scene.reversing)
	scene.brain_map.drag_yaw = 1.3  # as if dragged: the map seen from the side
	await _wait(0.2)
	_snap("map_6_turned")
	_press(KEY_N)
	await _wait(0.3)
	_snap("map_5_hidden")
	quit()
