extends SceneTree

# Render the actual game asset with the game's materials from a closer camera.


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	var scene := (load("res://main.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(scene)
	current_scene = scene
	for frame in range(4):
		await process_frame
	scene.set_process(false)
	var camera: Camera3D = scene.get("camera")
	camera.position = Vector3(1.25, 0.68, -1.15)
	camera.fov = 39.0
	camera.look_at(Vector3(0.0, 0.27, 0.0), Vector3.UP)
	await process_frame
	await process_frame
	var destination := OS.get_environment("FLY_CREATURE_CAPTURE")
	if destination.is_empty():
		push_error("Set FLY_CREATURE_CAPTURE to an output PNG path.")
		quit(1)
		return
	var image := root.get_texture().get_image()
	print("CAPTURE ", image.get_width(), "x", image.get_height(), " ", destination)
	if image.save_png(destination) != OK:
		push_error("Could not save Godot screenshot.")
		quit(1)
		return
	quit()
