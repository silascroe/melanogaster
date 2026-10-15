extends SceneTree

# Fixed look-development shots of the game scene, HUD hidden, for before/after
# comparisons of the fly's appearance. No brain service is needed: the feeding
# pose is set directly on the actor, so these images say nothing about neural
# behaviour. Run with FLY_CREATURE_CAPTURE_DIR set to an output folder:
#   godot --path godot --resolution 1280x720 -s res://capture_looks.gd

const SHOTS := [
	# name, camera position, look-at point, fov, feeding pose
	["game", Vector3(2.8, 2.2, 3.5), Vector3(0.0, 0.25, -1.0), 47.0, false],
	["three_quarter", Vector3(1.25, 0.68, -1.15), Vector3(0.0, 0.27, 0.0), 39.0, false],
	["feeding_side", Vector3(1.55, 0.42, -0.35), Vector3(0.0, 0.22, -0.35), 36.0, true],
	["front_low", Vector3(0.35, 0.32, -2.2), Vector3(0.0, 0.3, 0.0), 40.0, false],
]


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	var out_dir := OS.get_environment("FLY_CREATURE_CAPTURE_DIR")
	if out_dir.is_empty():
		push_error("Set FLY_CREATURE_CAPTURE_DIR to an output folder.")
		quit(1)
		return
	var scene := (load("res://main.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(scene)
	current_scene = scene
	await process_frame
	scene.set_process(false)
	scene.set_process_unhandled_input(false)
	for layer in scene.find_children("*", "CanvasLayer", true, false):
		(layer as CanvasLayer).visible = false
	var fly: FlyActor = scene.get("fly_actor")
	fly.position = Vector3.ZERO
	fly.rotation.y = 0.0
	fly.reset_actor()
	var camera: Camera3D = scene.get("camera")
	var sugar: Node3D = scene.get("sugar_root")
	var drop := Vector3(0.0, 0.0, -0.52)
	for shot in SHOTS:
		var feeding: bool = shot[4]
		sugar.visible = feeding
		sugar.position = drop
		fly.set_feeding(feeding, drop if feeding else Vector3.INF, 0.22)
		for i in range(70):  # let the proboscis and legs settle
			fly.advance(1.0 / 60.0, false, 0.0)
			await process_frame
		camera.position = shot[1]
		camera.fov = shot[3]
		camera.look_at(shot[2], Vector3.UP)
		await process_frame
		await process_frame
		var path := out_dir.path_join("%s.png" % shot[0])
		root.get_texture().get_image().save_png(path)
		print("CAPTURE ", path)
	quit()
