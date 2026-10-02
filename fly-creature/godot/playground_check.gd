extends "res://playground.gd"


func _ready() -> void:
	super._ready()
	paused = true
	pause_button.text = "Resume"
	_run_checks.call_deferred()


func _wait_until(predicate: Callable) -> bool:
	var deadline := Time.get_ticks_msec() + 15000
	while not predicate.call():
		await get_tree().process_frame
		if Time.get_ticks_msec() > deadline or not fail_message.is_empty():
			push_error("Playground check timed out: " + fail_message)
			get_tree().quit(1)
			return false
	return true


func _check(value: bool, message: String) -> bool:
	if not value:
		push_error(message)
		get_tree().quit(1)
	return value


func _run_checks() -> void:
	if not await _wait_until(func(): return not world_id.is_empty()): return
	if not _check(snapshot.tick == 0, "Paused startup advanced time"): return
	pause_button.pressed.emit()
	if not await _wait_until(func(): return snapshot.tick >= 100): return
	# Global pause must work even when a UI button has keyboard focus.
	reset_button.grab_focus()
	var space := InputEventKey.new()
	space.keycode = KEY_SPACE
	space.pressed = true
	Input.parse_input_event(space)
	await get_tree().process_frame
	if not _check(paused, "Space was swallowed by focused UI"): return
	space = InputEventKey.new()
	space.keycode = KEY_SPACE
	space.pressed = false
	Input.parse_input_event(space)
	if not await _wait_until(func(): return pending.is_empty()): return
	var frozen_tick: int = snapshot.tick
	for i in range(12): await get_tree().process_frame
	if not _check(snapshot.tick == frozen_tick, "Pause did not freeze the simulation"): return
	hide_button.pressed.emit()
	pause_button.pressed.emit()
	if not await _wait_until(func(): return snapshot.tick >= frozen_tick + 40): return
	if not _check(not snapshot.target.active, "Hide target did not reach Python"): return
	for model in MODES:
		if not _check(snapshot.models[model].steering.turn_rate_rad_s == 0, "Hidden target left queued turn"): return
	pause_button.pressed.emit()
	var old_world := world_id
	preset_picker.select(6)
	preset_picker.item_selected.emit(6)
	if not await _wait_until(func(): return not world_id.is_empty() and world_id != old_world): return
	if not _check(snapshot.tick == 0 and preset == "manual", "Preset reset did not clear time"): return
	hide_button.pressed.emit()
	focus_picker.select(3)
	focus_picker.item_selected.emit(3)
	if not _check(focus == 3 and snapshot.tick == 0, "Inspecting another controller mutated the world"): return
	for i in range(12): await get_tree().process_frame
	# Stabilize the view before testing known world coordinates; reset normally eases it.
	camera.position = Vector3(4.5, 8, 9)
	camera.look_at(Vector3(0, .2, -2.8))
	camera.force_update_transform()
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = get_viewport().get_final_transform() * camera.unproject_position(Vector3(2, .45, -5))
	Input.parse_input_event(press)
	await get_tree().process_frame
	var motion := InputEventMouseMotion.new()
	motion.position = get_viewport().get_final_transform() * camera.unproject_position(Vector3(3, .45, -5))
	Input.parse_input_event(motion)
	await get_tree().process_frame
	var release := InputEventMouseButton.new()
	release.button_index = MOUSE_BUTTON_LEFT
	release.position = get_viewport().get_final_transform() * Vector2(40, 200)
	release.pressed = false
	Input.parse_input_event(release)
	await get_tree().process_frame
	if not _check(not dragging, "Release over UI left dragging active"): return
	if not _check(manual_target.distance_to(Vector2(3, -5)) < .02, "Mouse drag did not map onto target plane"): return
	pause_button.pressed.emit()
	if not await _wait_until(func(): return snapshot.tick >= 50): return
	if not _check(absf(snapshot.target.x - 3) < .02, "Manual target was not sent to the world"): return
	for model in MODES:
		if not _check(snapshot.models[model].steering.model_time_ms == snapshot.tick * 10, "Controller clocks diverged"): return
	# Reset during an actual in-flight request; stale results must be discarded.
	if not await _wait_until(func(): return not pending.is_empty()): return
	old_world = world_id
	pause_button.pressed.emit()
	reset_button.pressed.emit()
	if not await _wait_until(func(): return not world_id.is_empty() and world_id != old_world): return
	if not _check(snapshot.tick == 0, "Queued reset accepted stale ticks"): return
	old_world = world_id
	var depth_slider := find_child("DepthSlider", true, false) as HSlider
	depth_slider.value = 5
	if not await _wait_until(func(): return not world_id.is_empty() and world_id != old_world): return
	if not _check(depth == 5 and snapshot.tick == 0, "Depth slider did not replay"): return
	old_world = world_id
	var heading_slider := find_child("HeadingSlider", true, false) as HSlider
	heading_slider.value = 25
	if not await _wait_until(func(): return not world_id.is_empty() and world_id != old_world): return
	if not _check(absf(snapshot.models.intact.heading_rad - deg_to_rad(25)) < .00001, "Heading slider was not applied"): return
	old_world = world_id
	_mirror()
	if not await _wait_until(func(): return not world_id.is_empty() and world_id != old_world): return
	if not _check(absf(snapshot.models.intact.heading_rad + deg_to_rad(25)) < .00001, "Mirror did not reflect heading"): return
	print("PLAYGROUND_UI_CHECK ", JSON.stringify({"passed": true, "pause": true,
		"hide_clears_turns": true, "preset_reset": true, "focus_preserves_state": true,
		"mouse_drag": true, "clocks": true, "inflight_reset": true,
		"sliders": true, "mirror": true, "keyboard_pause": true, "request_samples": latencies.size()}))
	get_tree().quit()
