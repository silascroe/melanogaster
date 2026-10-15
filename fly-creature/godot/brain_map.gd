extends Control

# Live map of the neurons firing in the brain copies. Each dot is one neuron of
# the packaged subsets, placed at its cell body in the MaleCNS release (sensory
# cells whose bodies lie outside the scan are placed near their partners). Which
# dots light up comes from the Python service every 50 ms step. Glow time,
# colours, dot sizes and the rotation are display choices only.

const BrainViewScript := preload("res://brain_view.gd")

const PANEL_SIZE := Vector2(300.0, 440.0)
const HEADER := 74.0
const FOOTER := 40.0
const GLOW_S := 0.22
const TEXTURE_WIDTH := 256  # neuron i is texel (i & 255, i >> 8); matches the service
const SWAY_RAD := 0.55
const SWAY_SPEED := 0.22
const LABEL_GAP := 14.0
const BACKDROP := Color(0.035, 0.055, 0.07)

const SENSE_COLORS := {
	"taste": BrainViewScript.ACCENT_FEED,
	"loom": BrainViewScript.ACCENT_JUMP,
	"target": BrainViewScript.ACCENT_TURN,
	"touch": BrainViewScript.ACCENT_GROOM,
	"obstacle": BrainViewScript.ACCENT_BACK,
}
const SENSE_NAMES := {"taste": "taste", "loom": "loom", "target": "target",
	"touch": "antenna", "obstacle": "forelegs"}

const SHADER_CODE := """
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, depth_test_disabled, cull_disabled,
	shadows_disabled, fog_disabled;

// Per neuron, from the service: r = steps since it last fired (255 = not
// recently), g = which brain copy fired it. arrived = when that image came.
uniform sampler2D state : filter_nearest, repeat_disable;
uniform float now = 0.0;
uniform float arrived = 0.0;
uniform float step_s = 0.05;
uniform float glow_s = 0.22;
uniform float pixel_scale = 1.0;
uniform vec4 rest_color : source_color = vec4(0.40, 0.50, 0.56, 1.0);
uniform vec4 sense0 : source_color;
uniform vec4 sense1 : source_color;
uniform vec4 sense2 : source_color;
uniform vec4 sense3 : source_color;
uniform vec4 sense4 : source_color;

varying vec3 tint;

vec3 sense_color(int s) {
	if (s == 0) return sense0.rgb;
	if (s == 1) return sense1.rgb;
	if (s == 2) return sense2.rgb;
	if (s == 3) return sense3.rgb;
	return sense4.rgb;
}

void vertex() {
	// Instance custom data holds the neuron index as two bytes plus its kind.
	int index = int(round(INSTANCE_CUSTOM.x * 255.0)) + 256 * int(round(INSTANCE_CUSTOM.y * 255.0));
	int kind = int(round(INSTANCE_CUSTOM.z * 255.0));
	ivec2 size = textureSize(state, 0);
	vec2 cell = round(texelFetch(state, ivec2(index % size.x, index / size.x), 0).rg * 255.0);
	float since = cell.x * step_s + max(0.0, now - arrived);
	float heat = cell.x > 254.0 ? 0.0 : exp(-since / glow_s);
	// Additive dots: dense regions brighten, so ordinary cells stay dim and
	// thousands firing together still show their copy's colour.
	float rest = kind == 2 ? 0.55 : (kind == 1 ? 0.14 : 0.10);
	float hot = kind == 2 ? 1.3 : (kind == 1 ? 0.6 : 0.17);
	tint = rest_color.rgb * rest + sense_color(int(round(cell.y))) * heat * hot;
	float size_px = kind == 2 ? 3.2 : 1.6;
	POINT_SIZE = pixel_scale * (size_px + heat * (kind == 2 ? 5.0 : 1.6));
}

void fragment() {
	vec2 p = POINT_COORD * 2.0 - 1.0;
	float d = dot(p, p);
	if (d > 1.0) {
		discard;
	}
	ALBEDO = tint * (1.0 - 0.55 * d);
}
"""

var loaded := false
var n := 0
var senses: Array = []
var labels: Array = []          # {name, sense, kind, centroid, cells}
var running: Dictionary = {}    # sense -> true while its copy runs
var left_x := 1.0
var approximate_count := 0
var clock := 0.0
var sway_time := 0.0
var drag_yaw := 0.0
var dragging := false
var note := "waiting for the brain service..."

var container: SubViewportContainer
var viewport: SubViewport
var camera: Camera3D
var pivot: Node3D
var cloud_material: ShaderMaterial
var state_image: Image
var state_texture: ImageTexture
var overlay: Control


func _ready() -> void:
	custom_minimum_size = PANEL_SIZE
	size = PANEL_SIZE
	mouse_filter = Control.MOUSE_FILTER_STOP
	container = SubViewportContainer.new()
	container.stretch = true
	container.position = Vector2(0.0, HEADER)
	container.size = Vector2(PANEL_SIZE.x, PANEL_SIZE.y - HEADER - FOOTER)
	container.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(container)
	viewport = SubViewport.new()
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_WHEN_VISIBLE
	container.add_child(viewport)
	camera = Camera3D.new()
	camera.fov = 30.0
	camera.position = Vector3(0.0, 0.0, 4.4)
	camera.current = true
	# Opaque dark backdrop (additive dots need one) with a soft bloom.
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = BACKDROP.srgb_to_linear()
	environment.glow_enabled = true
	environment.glow_intensity = 0.35
	environment.glow_bloom = 0.0
	camera.environment = environment
	viewport.add_child(camera)
	pivot = Node3D.new()
	viewport.add_child(pivot)
	overlay = Control.new()
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.position = container.position
	overlay.size = container.size
	overlay.draw.connect(_draw_labels)
	add_child(overlay)


## Builds the dot cloud from the service's /brain_map payload.
func load_map(payload: Dictionary) -> void:
	n = int(payload.get("n", 0))
	senses = payload.get("senses", [])
	approximate_count = int(payload.get("approximate_count", 0))
	var xyz := Marshalls.base64_to_raw(str(payload.get("xyz", ""))).to_float32_array()
	if n <= 0 or xyz.size() != n * 3 or int(payload.get("texture_width", 0)) != TEXTURE_WIDTH:
		note = "neuron map data missing; update the brain service"
		return
	var kinds := PackedByteArray()
	kinds.resize(n)
	labels.clear()
	for entry in payload.get("labels", []):
		var cells := _decode_u16(str(entry.get("cells", "")))
		if cells.is_empty():
			continue
		var kind: int = 2 if str(entry.get("kind", "")) == "readout" else 1
		var centroid := Vector3.ZERO
		for i in cells:
			kinds[i] = maxi(kinds[i], kind)
			centroid += Vector3(xyz[3 * i], xyz[3 * i + 1], xyz[3 * i + 2])
		labels.append({"name": str(entry.get("name", "")), "sense": str(entry.get("sense", "")),
			"kind": kind, "centroid": centroid / cells.size(), "cells": cells})
	left_x = float(payload.get("left_x_sign", 1.0))

	# One point per neuron; static transforms, index and kind in custom data.
	var buffer := PackedFloat32Array()
	buffer.resize(n * 16)
	for i in n:
		var o := i * 16
		buffer[o] = 1.0
		buffer[o + 3] = xyz[3 * i]
		buffer[o + 5] = 1.0
		buffer[o + 7] = xyz[3 * i + 1]
		buffer[o + 10] = 1.0
		buffer[o + 11] = xyz[3 * i + 2]
		buffer[o + 12] = float(i & 255) / 255.0
		buffer[o + 13] = float(i >> 8) / 255.0
		buffer[o + 14] = float(kinds[i]) / 255.0
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_custom_data = true
	multimesh.mesh = PointMesh.new()
	multimesh.instance_count = n
	multimesh.buffer = buffer
	multimesh.custom_aabb = AABB(Vector3(-1.2, -1.2, -1.2), Vector3(2.4, 2.4, 2.4))

	var rows := int(ceil(float(n) / TEXTURE_WIDTH))
	state_image = Image.create_empty(TEXTURE_WIDTH, rows, false, Image.FORMAT_RG8)
	state_image.fill(Color(1.0, 0.0, 0.0, 0.0))  # age 255: not fired recently
	state_texture = ImageTexture.create_from_image(state_image)
	var shader := Shader.new()
	shader.code = SHADER_CODE
	cloud_material = ShaderMaterial.new()
	cloud_material.shader = shader
	cloud_material.set_shader_parameter("state", state_texture)
	cloud_material.set_shader_parameter("glow_s", GLOW_S)
	for k in senses.size():
		cloud_material.set_shader_parameter("sense%d" % k, SENSE_COLORS.get(senses[k], Color.WHITE))
	var cloud := MultiMeshInstance3D.new()
	cloud.multimesh = multimesh
	cloud.material_override = cloud_material
	for child in pivot.get_children():
		child.queue_free()
	pivot.add_child(cloud)
	loaded = true
	note = ""


## Lights the neurons that fired in the latest 50 ms step.
func update_trace(trace: Dictionary) -> void:
	running.clear()
	for sense in trace.get("brain_copies_running", []):
		running[str(sense)] = true
	if not loaded:
		return
	if not trace.has("neuron_map"):
		note = "the map shows the whole-brain model only (press B)" \
			if str(trace.get("model", "")) != "brain" else ""
		return
	note = ""
	# Ready-made image from the service: no per-neuron work here.
	var raw := Marshalls.base64_to_raw(str(trace["neuron_map"]))
	if raw.size() != state_image.get_width() * state_image.get_height() * 2:
		return
	state_image.set_data(TEXTURE_WIDTH, state_image.get_height(), false, Image.FORMAT_RG8, raw)
	state_texture.update(state_image)
	cloud_material.set_shader_parameter("arrived", clock)


func _decode_u16(text: String) -> PackedInt32Array:
	var raw := Marshalls.base64_to_raw(text)
	var out := PackedInt32Array()
	out.resize(raw.size() / 2)
	for k in out.size():
		out[k] = raw.decode_u16(2 * k)
	return out


func _gui_input(event: InputEvent) -> void:
	var button := event as InputEventMouseButton
	if button != null and button.button_index == MOUSE_BUTTON_LEFT:
		dragging = button.pressed
		accept_event()
		return
	var motion := event as InputEventMouseMotion
	if motion != null and dragging:
		drag_yaw += motion.relative.x * 0.012
		accept_event()


func _process(delta: float) -> void:
	if not is_visible_in_tree():
		return
	clock += delta
	if not dragging:
		sway_time += delta
	pivot.rotation.y = drag_yaw + SWAY_RAD * sin(sway_time * SWAY_SPEED)
	if cloud_material != null:
		cloud_material.set_shader_parameter("now", clock)
		# Canvas stretching scales the map; keep dots the same size relative to it.
		var scale_px := float(viewport.size.y) / container.size.y if container.size.y > 0.0 else 1.0
		cloud_material.set_shader_parameter("pixel_scale", scale_px)
	queue_redraw()
	overlay.queue_redraw()


func _draw() -> void:
	var font := ThemeDB.fallback_font
	draw_rect(Rect2(Vector2.ZERO, PANEL_SIZE), Color(BACKDROP, 0.96))
	draw_rect(Rect2(Vector2.ZERO, PANEL_SIZE), Color(1, 1, 1, 0.12), false, 1.0)
	draw_string(font, Vector2(14.0, 26.0), "NEURON MAP", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 17,
		BrainViewScript.TEXT_COLOR)
	var subtitle := "%s neurons at their cell bodies" % _thousands(n) if loaded else note
	draw_string(font, Vector2(14.0, 44.0), subtitle, HORIZONTAL_ALIGNMENT_LEFT, PANEL_SIZE.x - 28.0, 12,
		BrainViewScript.MUTED_COLOR)
	# Legend: one colour per brain copy, bright while that copy runs.
	var x := 14.0
	for sense in ["taste", "loom", "target", "touch", "obstacle"]:
		var on := running.has(sense)
		var color: Color = SENSE_COLORS[sense]
		color.a = 1.0 if on else 0.35
		draw_circle(Vector2(x + 4.0, 60.0), 4.0, color)
		var text: String = SENSE_NAMES[sense]
		draw_string(font, Vector2(x + 11.0, 64.0), text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11,
			BrainViewScript.TEXT_COLOR if on else BrainViewScript.MUTED_COLOR)
		x += 15.0 + font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11).x + 8.0
	var footer_y := PANEL_SIZE.y - FOOTER + 14.0
	var line_one := note if loaded and not note.is_empty() else "colour = which brain copy fired · drag to turn"
	draw_string(font, Vector2(14.0, footer_y), line_one, HORIZONTAL_ALIGNMENT_LEFT, PANEL_SIZE.x - 28.0,
		11, BrainViewScript.MUTED_COLOR)
	if loaded:
		draw_string(font, Vector2(14.0, footer_y + 15.0),
			"%s sensory cells: position approximate" % _thousands(approximate_count),
			HORIZONTAL_ALIGNMENT_LEFT, PANEL_SIZE.x - 28.0, 11, BrainViewScript.MUTED_COLOR)


## Readout neurons get a ring and a label in a column at the right edge.
func _draw_labels() -> void:
	if not loaded:
		return
	var font := ThemeDB.fallback_font
	var area := overlay.size
	var scale_px := container.size.y / float(viewport.size.y) if viewport.size.y > 0 else 1.0
	var placed: Array = []
	for label in labels:
		if label["kind"] != 2:
			continue
		var world: Vector3 = pivot.global_transform * label["centroid"]
		placed.append({"label": label, "at": camera.unproject_position(world) * scale_px})
	placed.sort_custom(func(a, b): return a["at"].y < b["at"].y)
	var next_y := 8.0
	for item in placed:
		var label: Dictionary = item["label"]
		var at: Vector2 = item["at"]
		var on := running.has(label["sense"])
		var color: Color = SENSE_COLORS.get(label["sense"], Color.WHITE)
		color.a = 1.0 if on else 0.45
		var y := maxf(at.y, next_y)
		next_y = y + LABEL_GAP
		var text: String = label["name"]
		var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11).x
		var text_x := area.x - width - 8.0
		overlay.draw_arc(at, 5.0, 0.0, TAU, 20, color, 1.2)
		overlay.draw_line(at + Vector2(5.0, 0.0), Vector2(text_x - 4.0, y - 4.0), Color(color, color.a * 0.6), 1.0)
		overlay.draw_string(font, Vector2(text_x, y), text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11, color)
	# The fly's left and right, under each half of the brain, and region names.
	for side in [["L", left_x], ["R", -left_x]]:
		var at := camera.unproject_position(pivot.global_transform * Vector3(0.42 * side[1], 0.36, 0.0)) * scale_px
		overlay.draw_string(font, at + Vector2(-4.0, 4.0), side[0], HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11,
			BrainViewScript.MUTED_COLOR)
	var brain := camera.unproject_position(Vector3(-0.95, 0.72, 0.0)) * scale_px
	overlay.draw_string(font, Vector2(8.0, brain.y), "brain", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11,
		BrainViewScript.MUTED_COLOR)
	var cord := camera.unproject_position(Vector3(-0.95, -0.45, 0.0)) * scale_px
	overlay.draw_string(font, Vector2(8.0, cord.y), "nerve cord", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11,
		BrainViewScript.MUTED_COLOR)


func _thousands(value: int) -> String:
	var text := str(value)
	var out := ""
	while text.length() > 3:
		out = "," + text.substr(text.length() - 3) + out
		text = text.substr(0, text.length() - 3)
	return text + out
