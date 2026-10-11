extends Control

# Live readout of the two selected circuits. Spike counts and voltages come from
# the Python service; bar scaling and decay below are display choices only.

const PANEL_WIDTH := 330.0
const ROW_HEIGHT := 26.0
const BAR_X := 112.0
const BAR_WIDTH := 148.0
const HOLD_TAU_S := 0.35
const PEAK_TAU_S := 25.0

const ACCENT_JUMP := Color(0.98, 0.55, 0.25)
const ACCENT_TURN := Color(0.30, 0.86, 0.72)
const TEXT_COLOR := Color(0.90, 0.94, 0.96)
const MUTED_COLOR := Color(0.58, 0.67, 0.72)
const BAR_BACK := Color(1.0, 1.0, 1.0, 0.09)

# Each row: key, label, accent color, floor for bar scaling.
var rows: Array = []
var values: Dictionary = {}
var peaks: Dictionary = {}
var turn_rate := 0.0
var jump_flash := 0.0
var turn_active := false
var dna_base := 0.0
var dna_seen := false
var model_note := ""
var condition_text := "INTACT"


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	custom_minimum_size = Vector2(PANEL_WIDTH, 420.0)
	size = custom_minimum_size
	rows = [
		{"section": "JUMP CIRCUIT", "color": ACCENT_JUMP},
		{"key": "lc4", "label": "LC4  (speed)", "color": ACCENT_JUMP, "floor": 6.0},
		{"key": "lplc2", "label": "LPLC2  (size)", "color": ACCENT_JUMP, "floor": 6.0},
		{"key": "gf", "label": "Giant fiber", "color": ACCENT_JUMP, "floor": 1.0},
		{"section": "TURN CIRCUIT", "color": ACCENT_TURN},
		{"key": "lc10a_l", "label": "LC10a  left", "color": ACCENT_TURN, "floor": 4.0},
		{"key": "lc10a_r", "label": "LC10a  right", "color": ACCENT_TURN, "floor": 4.0},
		{"key": "aotu_l", "label": "AOTU  left", "color": ACCENT_TURN, "floor": 1.0},
		{"key": "aotu_r", "label": "AOTU  right", "color": ACCENT_TURN, "floor": 1.0},
		{"key": "dna_l", "label": "DNa02  left", "color": ACCENT_TURN, "floor": 2.0},
		{"key": "dna_r", "label": "DNa02  right", "color": ACCENT_TURN, "floor": 2.0},
	]
	for row in rows:
		if row.has("key"):
			values[row["key"]] = 0.0
			peaks[row["key"]] = float(row["floor"])


func update_trace(trace: Dictionary) -> void:
	var spikes: Dictionary = trace.get("spikes", {})
	_hold("lc4", float(spikes.get("LC4", 0)))
	_hold("lplc2", float(spikes.get("LPLC2", 0)))
	_hold("gf", float(spikes.get("DNp01", 0)))
	if bool(trace.get("jump", false)):
		jump_flash = 1.0
	condition_text = str(trace.get("condition", "intact")).to_upper()
	var steering: Dictionary = trace.get("steering", {})
	turn_active = not steering.is_empty()
	if not turn_active:
		return
	turn_rate = float(steering.get("turn_rate_rad_s", 0.0))
	var lc10a: Dictionary = steering.get("LC10a_spikes", {})
	_hold("lc10a_l", float(lc10a.get("L", 0)))
	_hold("lc10a_r", float(lc10a.get("R", 0)))
	var aotu: Dictionary = steering.get("AOTU_spikes", {})
	var aotu_left := 0.0
	var aotu_right := 0.0
	for cell_type in aotu:
		var sides: Dictionary = aotu[cell_type]
		aotu_left += float(sides.get("L", 0))
		aotu_right += float(sides.get("R", 0))
	_hold("aotu_l", aotu_left)
	_hold("aotu_r", aotu_right)
	var dna: Dictionary = steering.get("DNa02_mean_mv", {})
	# Resting voltage is not zero, so show rise above the lowest value seen.
	# Resting voltage is not zero: draw the rise above a slowly adapting shared
	# resting baseline (about 8 s), so quiet reads as empty on both sides.
	var left_mv := float(dna.get("L", 0.0))
	var right_mv := float(dna.get("R", 0.0))
	var quiet := minf(left_mv, right_mv)
	if not dna_seen:
		dna_base = quiet
		dna_seen = true
	dna_base += (quiet - dna_base) * (1.0 - exp(-0.05 / 8.0))
	dna_base = minf(dna_base, quiet)
	_hold("dna_l", left_mv - dna_base)
	_hold("dna_r", right_mv - dna_base)
	if steering.has("right_minus_left_activity"):
		# The experimental activity model reports activity units, not spikes.
		model_note = "activity model: only the turn readout is shown"
	else:
		model_note = ""


func _hold(key: String, value: float) -> void:
	if value >= values[key]:
		values[key] = value
	peaks[key] = maxf(peaks[key], value)


func _process(delta: float) -> void:
	var decay := exp(-delta / HOLD_TAU_S)
	var peak_decay := exp(-delta / PEAK_TAU_S)
	for row in rows:
		if row.has("key"):
			var key: String = row["key"]
			values[key] *= decay
			peaks[key] = maxf(float(row["floor"]), peaks[key] * peak_decay)
	jump_flash = maxf(0.0, jump_flash - delta * 1.4)
	queue_redraw()


func _draw() -> void:
	var font := ThemeDB.fallback_font
	var height := 60.0 + rows.size() * ROW_HEIGHT + 130.0
	draw_rect(Rect2(0.0, 0.0, PANEL_WIDTH, height), Color(0.05, 0.08, 0.10, 0.82))
	draw_rect(Rect2(0.0, 0.0, PANEL_WIDTH, height), Color(1, 1, 1, 0.12), false, 1.0)
	draw_string(font, Vector2(14.0, 26.0), "BRAIN  /  %s" % condition_text,
		HORIZONTAL_ALIGNMENT_LEFT, -1.0, 17, TEXT_COLOR)
	draw_string(font, Vector2(14.0, 44.0), "recorded wiring, simplified LIF neurons",
		HORIZONTAL_ALIGNMENT_LEFT, -1.0, 12, MUTED_COLOR)
	var y := 58.0
	for row in rows:
		if row.has("section"):
			y += 8.0
			draw_string(font, Vector2(14.0, y + 14.0), row["section"],
				HORIZONTAL_ALIGNMENT_LEFT, -1.0, 13, row["color"])
			y += 22.0
			continue
		var key: String = row["key"]
		var fraction := clampf(values[key] / peaks[key], 0.0, 1.0)
		draw_string(font, Vector2(14.0, y + 15.0), row["label"],
			HORIZONTAL_ALIGNMENT_LEFT, BAR_X - 18.0, 13, TEXT_COLOR)
		draw_rect(Rect2(BAR_X, y + 4.0, BAR_WIDTH, 12.0), BAR_BACK)
		if fraction > 0.003:
			draw_rect(Rect2(BAR_X, y + 4.0, BAR_WIDTH * fraction, 12.0), row["color"])
		y += ROW_HEIGHT
	# Jump output flash.
	y += 6.0
	if jump_flash > 0.0:
		draw_rect(Rect2(14.0, y, PANEL_WIDTH - 28.0, 26.0),
			Color(ACCENT_JUMP.r, ACCENT_JUMP.g, ACCENT_JUMP.b, 0.25 + 0.6 * jump_flash))
	draw_string(font, Vector2(24.0, y + 18.0), "JUMP" if jump_flash > 0.05 else "no jump",
		HORIZONTAL_ALIGNMENT_LEFT, -1.0, 14, TEXT_COLOR if jump_flash > 0.05 else MUTED_COLOR)
	y += 36.0
	# Turn gauge: DNa02 right minus left through the engineered turn rule.
	draw_string(font, Vector2(14.0, y + 12.0), "TURN  (engineered readout of DNa02 right - left)",
		HORIZONTAL_ALIGNMENT_LEFT, -1.0, 12, MUTED_COLOR)
	var gauge := Rect2(14.0, y + 20.0, PANEL_WIDTH - 28.0, 14.0)
	draw_rect(gauge, BAR_BACK)
	var middle := gauge.position.x + gauge.size.x * 0.5
	draw_line(Vector2(middle, gauge.position.y - 2.0), Vector2(middle, gauge.end.y + 2.0), MUTED_COLOR, 1.0)
	var swing := clampf(turn_rate / 1.2, -1.0, 1.0) * gauge.size.x * 0.5
	if absf(swing) > 0.5:
		draw_rect(Rect2(minf(middle, middle + swing), gauge.position.y, absf(swing), gauge.size.y), ACCENT_TURN)
	draw_string(font, Vector2(14.0, y + 52.0), "left", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 12, MUTED_COLOR)
	draw_string(font, Vector2(PANEL_WIDTH - 40.0, y + 52.0), "right", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 12, MUTED_COLOR)
	if not model_note.is_empty():
		draw_string(font, Vector2(14.0, y + 70.0), model_note, HORIZONTAL_ALIGNMENT_LEFT, -1.0, 11, MUTED_COLOR)
