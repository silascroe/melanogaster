extends SceneTree

# Optional command-line art inspection: loads the actual creature scene and
# writes a frame to FLY_CREATURE_CAPTURE. No neural service is required to draw.


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	var packed: PackedScene = load("res://main.tscn") as PackedScene
	var scene: Node3D = packed.instantiate() as Node3D
	root.add_child(scene)
	current_scene = scene
	for index in range(8):
		await process_frame
	var fly: Node3D = scene.get_node_or_null("Fly") as Node3D
	print("FLY_VISUAL", fly != null, " WINGS ",
		fly.find_child("WingNearPivot", true, false) != null if fly != null else false,
		" ", fly.find_child("WingFarPivot", true, false) != null if fly != null else false)
	print("LEG_PIVOTS", fly.find_children("Leg*Pivot", "Node3D", true, false).size()
		if fly != null else 0)
	var texture := root.get_texture()
	if texture == null:
		push_error("Godot needs a visible renderer to capture a frame; --headless uses a dummy texture.")
		quit(1)
		return
	var image := texture.get_image()
	if image == null:
		push_error("The viewport did not return an image.")
		quit(1)
		return
	var destination := OS.get_environment("FLY_CREATURE_CAPTURE")
	if destination.is_empty():
		destination = ProjectSettings.globalize_path("user://fly_creature_capture.png")
	print("CAPTURE_SIZE", image.get_width(), image.get_height())
	print("CAPTURE_RESULT", image.save_png(destination), destination)
	quit()
