class_name FlyActor
extends Node3D

# Reusable visual creature. The owning world supplies its floor position,
# heading, walking state, and jump requests. All pose work stays here.

const GAIT_REFERENCE_STANCE_S := 0.19
const GAIT_SWING_S := 0.12
const GAIT_FOOT_LIFT := 0.043
const FOOT_GROUND_OFFSET := 0.012
const REFERENCE_WALK_SPEED := 1.05
const JUMP_SPEED := 3.2
const JUMP_GRAVITY := 12.0
const JUMP_PREP_S := 0.11
const LANDING_S := 0.16
const FLIGHT_HEIGHT := 0.9
const TAKEOFF_S := 0.48
const FLIGHT_LANDING_S := 0.62

enum FlightState { GROUNDED, TAKING_OFF, CRUISING, LANDING }

@onready var body_motion: Node3D = $BodyMotion
@onready var fly_visual: Node3D = $BodyMotion/FlyVisualMotion
@onready var model_root: Node3D = $BodyMotion/FlyVisualMotion/MaleDrosophila

var wing_near: Node3D
var wing_far: Node3D
var legs: Array[Dictionary] = []
var visual_clock := 0.0
var gait_clock := 0.0
var gait_stance_fraction := 0.6
var body_compression := 0.0
var jump_height := 0.0
var jump_velocity := 0.0
var jump_prep_timer := 0.0
var landing_timer := 0.0
var flight_state := FlightState.GROUNDED
var flight_elapsed := 0.0
var flight_height := 0.0
var flight_landing_from := 0.0
# Proboscis extension while feeding: moves the model's existing proboscis and
# labella parts. Presentation only; the decision to feed comes from the brain.
var mouth_parts: Array[Dictionary] = []
var feeding_target := 0.0
var proboscis_extension := 0.0
var proboscis_segments: Array[MeshInstance3D] = []
var proboscis_elbow: MeshInstance3D
var food_world := Vector3.INF
var food_radius := 0.0
# Model space: the head faces -X, up is +Y; the table is about 1.0 model unit
# below the mouth. The extended proboscis grows from inside the model's own
# proboscis nub, bends forward at an elbow, and ends in the labella pad.
const PROBOSCIS_BASE := Vector3(-1.33, 1.02, 0.0)
const PROBOSCIS_DEFAULT_TIP := Vector3(-1.45, 0.40, 0.0)
const PROBOSCIS_MAX_LENGTH := 0.85
const PROBOSCIS_ELBOW_BULGE := 0.10
const LABELLA_PRESSED_SCALE := Vector3(1.45, 0.65, 1.45)


func _ready() -> void:
	wing_near = model_root.find_child("WingNearPivot", true, false) as Node3D
	wing_far = model_root.find_child("WingFarPivot", true, false) as Node3D
	if wing_near == null or wing_far == null:
		push_warning("Imported fly wing pivots were not found.")
	for pivot_name in ["LegNeg0Pivot", "LegNeg1Pivot", "LegNeg2Pivot",
			"LegPos0Pivot", "LegPos1Pivot", "LegPos2Pivot"]:
		var pivot := model_root.find_child(pivot_name, true, false) as Node3D
		var stem: String = pivot_name.trim_suffix("Pivot")
		var knee := model_root.find_child(stem + "KneePivot", true, false) as Node3D
		var foot := model_root.find_child(stem + "Foot", true, false) as Node3D
		if pivot == null or knee == null or foot == null:
			push_warning("Incomplete two-segment rig for " + pivot_name)
			continue
		# v2 models add an ankle: the tibia ends there and the tarsus runs to the
		# claw-tip foot marker. v1 models end the tibia-and-tarsus at the foot.
		var ankle := model_root.find_child(stem + "AnklePivot", true, false) as Node3D
		var upper := knee.position
		var lower := ankle.position if ankle != null else foot.position
		var rest_reach := (upper + lower).normalized()
		var bend := upper - rest_reach * upper.dot(rest_reach)
		legs.append({
			"hip": pivot,
			"knee": knee,
			"ankle": ankle,
			"tarsus_rest": foot.position if ankle != null else Vector3.ZERO,
			"foot": foot,
			"upper_rest": upper,
			"lower_rest": lower,
			"bend_rest": bend,
			"rest_model_foot": model_root.to_local(foot.global_position),
			"anchor": foot.global_position,
			"swinging": false,
			"swing_elapsed": 0.0,
			"previous_phase": 0.0,
			"swing_from": foot.global_position,
			"swing_to": foot.global_position,
			"landing_from": foot.global_position,
		})
	if legs.size() != 6:
		push_warning("Imported fly leg rig is incomplete.")
	var nub := model_root.find_child("proboscis", true, false) as MeshInstance3D
	# Real labella are a pale, fleshy pad; the model's are dark like the rostrum.
	var pad_material := StandardMaterial3D.new()
	pad_material.albedo_color = Color(0.66, 0.50, 0.34)
	pad_material.roughness = 0.45
	for part in model_root.find_children("*labella*", "Node3D", true, false):
		var node := part as Node3D
		if node is MeshInstance3D:
			(node as MeshInstance3D).material_override = pad_material
		mouth_parts.append({"node": node, "position": node.position, "scale": node.scale})
	# Two tapered segments (rostrum, then haustellum) grown while feeding, plus a
	# cap over the elbow. The nub shares their warm brown so it all reads as one organ.
	var proboscis_material := StandardMaterial3D.new()
	proboscis_material.albedo_color = Color(0.40, 0.25, 0.14)
	proboscis_material.roughness = 0.5
	if nub != null:
		nub.material_override = proboscis_material
	for radii in [[0.042, 0.034], [0.034, 0.026]]:
		var segment := MeshInstance3D.new()
		var mesh := CylinderMesh.new()
		mesh.top_radius = radii[0]
		mesh.bottom_radius = radii[1]
		mesh.height = 1.0
		mesh.radial_segments = 12
		segment.mesh = mesh
		segment.material_override = proboscis_material
		segment.visible = false
		model_root.add_child(segment)
		proboscis_segments.append(segment)
	proboscis_elbow = MeshInstance3D.new()
	var elbow_mesh := SphereMesh.new()
	elbow_mesh.radius = 0.036
	elbow_mesh.height = 0.072
	proboscis_elbow.mesh = elbow_mesh
	proboscis_elbow.material_override = proboscis_material
	proboscis_elbow.visible = false
	model_root.add_child(proboscis_elbow)
	if mouth_parts.is_empty():
		push_warning("Labella parts were not found.")
	_reset_leg_anchors()


## Extend or retract the proboscis. When a food drop is given (world-space
## floor position and radius), the tip reaches for the nearest point on it.
func set_feeding(feeding: bool, drop_world := Vector3.INF, drop_radius := 0.0) -> void:
	feeding_target = 1.0 if feeding else 0.0
	if drop_world.is_finite() and drop_radius > 0.0:
		food_world = drop_world
		food_radius = drop_radius


func _proboscis_full_tip() -> Vector3:
	if not food_world.is_finite():
		return PROBOSCIS_DEFAULT_TIP
	# The game's sugar drop is a squashed sphere raised 0.3 radius off the floor,
	# 0.55 radius tall (see main.gd _build_sugar). Aim slightly inside its surface.
	var center := food_world + Vector3(0.0, 0.3 * food_radius, 0.0)
	var radii := Vector3(food_radius, 0.55 * food_radius, food_radius)
	var mouth := model_root.to_global(PROBOSCIS_BASE)
	var unit := (mouth - center) / radii
	if unit.length() < 0.001:
		return PROBOSCIS_DEFAULT_TIP
	var surface := center + unit.normalized() * radii * 0.9
	var reach := model_root.to_local(surface) - PROBOSCIS_BASE
	if reach.y > -0.2:
		return PROBOSCIS_DEFAULT_TIP  # drop not below the mouth; just extend
	return PROBOSCIS_BASE + reach.limit_length(PROBOSCIS_MAX_LENGTH)


func _place_segment(segment: MeshInstance3D, from: Vector3, to: Vector3) -> void:
	var span := to - from
	segment.position = (from + to) * 0.5
	# Stretch along the cylinder's own axis, then turn that axis onto the span.
	segment.basis = Basis(Quaternion(Vector3.DOWN, span.normalized())) \
		* Basis.from_scale(Vector3(1.0, span.length(), 1.0))


func _animate_mouth(delta: float) -> void:
	proboscis_extension = move_toward(proboscis_extension, feeding_target, delta * 2.5)
	if proboscis_extension == 0.0 and feeding_target == 0.0:
		food_world = Vector3.INF  # fully retracted: forget the last drop
	var e := smoothstep(0.0, 1.0, proboscis_extension)
	var tip := PROBOSCIS_BASE.lerp(_proboscis_full_tip(), e)
	var showing := e > 0.02 and proboscis_segments.size() == 2
	for segment in proboscis_segments:
		segment.visible = showing
	proboscis_elbow.visible = showing
	if showing:
		# The elbow bows forward (-X), like the joint between rostrum and haustellum.
		var elbow := (PROBOSCIS_BASE + tip) * 0.5 + Vector3(-PROBOSCIS_ELBOW_BULGE * e, 0.0, 0.0)
		_place_segment(proboscis_segments[0], PROBOSCIS_BASE, elbow)
		_place_segment(proboscis_segments[1], elbow, tip)
		proboscis_elbow.position = elbow
	for part in mouth_parts:
		var node: Node3D = part["node"]
		var rest: Vector3 = part["position"]
		var rest_scale: Vector3 = part["scale"]
		# The paired lobes meet at the tip and spread into a flat pad on the food.
		node.position = rest.lerp(tip + Vector3(0.0, 0.0, rest.z * 1.4), e)
		node.scale = rest_scale.lerp(rest_scale * LABELLA_PRESSED_SCALE, e)


func advance(delta: float, walking: bool, speed: float) -> void:
	_animate_mouth(delta)
	var just_landed := _advance_jump(delta)
	just_landed = _advance_flight(delta) or just_landed
	if just_landed:
		_prepare_landing_legs()
	_animate_visual(delta, walking, speed)


func request_jump() -> bool:
	if jump_height > 0.0 or jump_velocity > 0.0 or jump_prep_timer > 0.0 \
			or landing_timer > 0.0 or is_flying():
		return false
	jump_prep_timer = JUMP_PREP_S
	return true


func request_takeoff() -> bool:
	if is_flying() or jump_height > 0.0 or jump_velocity > 0.0 \
			or jump_prep_timer > 0.0 or landing_timer > 0.0:
		return false
	flight_state = FlightState.TAKING_OFF
	flight_elapsed = 0.0
	return true


func request_landing() -> bool:
	if not is_flying() or flight_state == FlightState.LANDING:
		return false
	flight_landing_from = flight_height
	flight_state = FlightState.LANDING
	flight_elapsed = 0.0
	return true


func is_flying() -> bool:
	return flight_state != FlightState.GROUNDED


func is_recovering() -> bool:
	return jump_prep_timer > 0.0 or landing_timer > 0.0 \
		or flight_state == FlightState.LANDING


func reset_actor() -> void:
	jump_height = 0.0
	jump_velocity = 0.0
	jump_prep_timer = 0.0
	landing_timer = 0.0
	flight_state = FlightState.GROUNDED
	flight_elapsed = 0.0
	flight_height = 0.0
	flight_landing_from = 0.0
	visual_clock = 0.0
	gait_clock = 0.0
	body_compression = 0.0
	body_motion.position.y = 0.0
	body_motion.rotation = Vector3.ZERO
	fly_visual.position.y = 0.0
	if wing_near != null:
		wing_near.rotation.x = 0.0
	if wing_far != null:
		wing_far.rotation.x = 0.0
	_reset_leg_anchors()


func _advance_jump(delta: float) -> bool:
	if jump_prep_timer > 0.0:
		jump_prep_timer = maxf(0.0, jump_prep_timer - delta)
		if jump_prep_timer == 0.0:
			jump_velocity = JUMP_SPEED
		return false
	if jump_height <= 0.0 and jump_velocity <= 0.0:
		landing_timer = maxf(0.0, landing_timer - delta)
		return false
	jump_height += jump_velocity * delta
	jump_velocity -= JUMP_GRAVITY * delta
	if jump_height <= 0.0:
		jump_height = 0.0
		jump_velocity = 0.0
		landing_timer = LANDING_S
		return true
	return false


func _advance_flight(delta: float) -> bool:
	if flight_state == FlightState.GROUNDED:
		return false
	flight_elapsed += delta
	if flight_state == FlightState.TAKING_OFF:
		var progress := minf(1.0, flight_elapsed / TAKEOFF_S)
		var eased := progress * progress * (3.0 - 2.0 * progress)
		flight_height = FLIGHT_HEIGHT * eased
		if progress >= 1.0:
			flight_state = FlightState.CRUISING
			flight_elapsed = 0.0
	elif flight_state == FlightState.CRUISING:
		flight_height = FLIGHT_HEIGHT + 0.025 * sin(visual_clock * 4.0)
	else:
		var progress := minf(1.0, flight_elapsed / FLIGHT_LANDING_S)
		var eased := progress * progress * (3.0 - 2.0 * progress)
		flight_height = flight_landing_from * (1.0 - eased)
		if progress >= 1.0:
			flight_height = 0.0
			flight_state = FlightState.GROUNDED
			landing_timer = LANDING_S
			return true
	return false


func _animate_visual(delta: float, walking: bool, speed: float) -> void:
	visual_clock += delta
	var airborne := jump_height > 0.01 or jump_velocity > 0.01 or is_flying()
	var prep_fraction := 1.0 - jump_prep_timer / JUMP_PREP_S if jump_prep_timer > 0.0 else 0.0
	var land_fraction := landing_timer / LANDING_S if landing_timer > 0.0 else 0.0
	var compression := 0.045 * prep_fraction + 0.025 * sin(land_fraction * PI)
	body_compression = lerpf(body_compression, -compression,
		clampf(delta * 18.0, 0.0, 1.0))
	body_motion.position.y = jump_height + flight_height + body_compression
	var target_pitch := 0.0
	if is_flying():
		target_pitch = -0.16 if flight_state == FlightState.TAKING_OFF else \
			(0.12 if flight_state == FlightState.LANDING else -0.025)
	elif airborne:
		target_pitch = -0.13 if jump_velocity > 0.0 else 0.09
	body_motion.rotation.x = lerpf(body_motion.rotation.x, target_pitch,
		clampf(delta * 10.0, 0.0, 1.0))
	var wing_rate := 56.0 if is_flying() else (48.0 if airborne else 6.0)
	var wing_span := 0.86 if is_flying() else (0.38 if airborne else 0.025)
	if wing_near != null:
		wing_near.rotation.x = sin(visual_clock * wing_rate) * wing_span
	if wing_far != null:
		wing_far.rotation.x = -sin(visual_clock * wing_rate) * wing_span
	if walking and not airborne:
		# Slow walking spends longer on planted feet. Swing stays nearly the same length.
		var stance_s := clampf(GAIT_REFERENCE_STANCE_S * REFERENCE_WALK_SPEED \
			/ maxf(speed, 0.25), 0.15, 0.52)
		var cycle_s := stance_s + GAIT_SWING_S
		gait_stance_fraction = stance_s / cycle_s
		gait_clock += delta / cycle_s
	fly_visual.position.y = 0.004 * sin(gait_clock * TAU * 2.0) if walking and not airborne \
		else 0.003 * sin(visual_clock * 3.0)
	_animate_legs(airborne, walking, delta, speed)


func _ground_y() -> float:
	return global_position.y + FOOT_GROUND_OFFSET


func _forward() -> Vector3:
	var forward := -global_transform.basis.z
	forward.y = 0.0
	return forward.normalized()


func _reset_leg_anchors() -> void:
	for leg in legs:
		var hip: Node3D = leg["hip"]
		var knee: Node3D = leg["knee"]
		hip.quaternion = Quaternion.IDENTITY
		knee.quaternion = Quaternion.IDENTITY
		if leg["ankle"] != null:
			(leg["ankle"] as Node3D).quaternion = Quaternion.IDENTITY
		var rest_world := model_root.to_global(leg["rest_model_foot"] as Vector3)
		leg["anchor"] = Vector3(rest_world.x, _ground_y(), rest_world.z)
		leg["swinging"] = false
		leg["swing_elapsed"] = 0.0
		leg["previous_phase"] = 0.0


func _prepare_landing_legs() -> void:
	gait_clock = 0.0
	for leg in legs:
		var foot: Node3D = leg["foot"]
		var rest_world := model_root.to_global(leg["rest_model_foot"] as Vector3)
		leg["landing_from"] = foot.global_position
		leg["anchor"] = Vector3(rest_world.x, _ground_y(), rest_world.z)
		leg["swinging"] = false
		leg["swing_elapsed"] = 0.0
		leg["previous_phase"] = 0.0


func _animate_legs(airborne: bool, walking: bool, delta: float, speed: float) -> void:
	var moving := walking and not airborne and jump_prep_timer <= 0.0 \
		and landing_timer <= 0.0
	var forward := _forward()
	for index in range(legs.size()):
		var leg := legs[index]
		var rest_world := model_root.to_global(leg["rest_model_foot"] as Vector3)
		var rest_ground := Vector3(rest_world.x, _ground_y(), rest_world.z)
		var target: Vector3
		if is_flying():
			leg["swinging"] = false
			var hip: Node3D = leg["hip"]
			var tuck_target := hip.global_position.lerp(rest_world, 0.48) \
				+ Vector3(0.0, 0.05, 0.0)
			var tuck := 1.0
			if flight_state == FlightState.TAKING_OFF:
				tuck = minf(1.0, flight_elapsed / TAKEOFF_S)
			elif flight_state == FlightState.LANDING:
				tuck = maxf(0.0, 1.0 - flight_elapsed / FLIGHT_LANDING_S)
			target = rest_world.lerp(tuck_target, tuck)
		elif airborne:
			leg["swinging"] = false
			target = rest_world + Vector3(0.0, 0.11, 0.0)
		elif landing_timer > 0.0:
			var land_progress := 1.0 - landing_timer / LANDING_S
			var eased_land := land_progress * land_progress * (3.0 - 2.0 * land_progress)
			target = (leg["landing_from"] as Vector3).lerp(leg["anchor"] as Vector3,
				eased_land)
		elif moving:
			# Within each diagonal tripod, front lifts first, then middle, then hind.
			# The stagger is wider during a slow walk, as seen in real flies.
			var stagger := lerpf(0.09, 0.045, clampf(speed / REFERENCE_WALK_SPEED, 0.0, 1.0))
			var tripod_offset := 0.0
			match index:
				0: tripod_offset = stagger
				4: tripod_offset = stagger * 0.5
				2: tripod_offset = 0.0
				3: tripod_offset = 0.5 + stagger
				1: tripod_offset = 0.5 + stagger * 0.5
				5: tripod_offset = 0.5
			var phase := fposmod(gait_clock + tripod_offset, 1.0)
			var scheduled_step := phase >= gait_stance_fraction \
				and float(leg["previous_phase"]) < gait_stance_fraction
			var hip: Node3D = leg["hip"]
			var max_reach := ((leg["upper_rest"] as Vector3).length() \
				+ (leg["lower_rest"] as Vector3).length()) * fly_visual.scale.x
			var ankle_anchor: Vector3 = (leg["anchor"] as Vector3) - (hip.get_parent() as Node3D) \
				.global_transform.basis * (leg["tarsus_rest"] as Vector3)
			var overextended := hip.global_position.distance_to(ankle_anchor) \
				> max_reach * 0.88
			if not bool(leg["swinging"]) and (scheduled_step or overextended):
				var marker: Node3D = leg["foot"]
				leg["swing_from"] = marker.global_position
				var lead := 0.075 if index % 3 == 0 else (0.06 if index % 3 == 1 else 0.05)
				leg["swing_to"] = rest_ground + forward * lead
				leg["swing_elapsed"] = 0.0
				leg["swinging"] = true
			if bool(leg["swinging"]):
				leg["swing_elapsed"] = float(leg["swing_elapsed"]) + delta
				var swing_fraction := minf(1.0, float(leg["swing_elapsed"]) \
					/ GAIT_SWING_S)
				var eased := swing_fraction * swing_fraction * (3.0 - 2.0 * swing_fraction)
				target = (leg["swing_from"] as Vector3).lerp(leg["swing_to"] as Vector3, eased)
				target.y = _ground_y() + sin(swing_fraction * PI) * GAIT_FOOT_LIFT
				if swing_fraction >= 1.0:
					leg["anchor"] = leg["swing_to"]
					leg["swinging"] = false
			else:
				target = leg["anchor"]
			leg["previous_phase"] = phase
		else:
			leg["swinging"] = false
			leg["anchor"] = (leg["anchor"] as Vector3).lerp(rest_ground, 0.16)
			target = leg["anchor"]
		_solve_leg_ik(leg, target)


func _solve_leg_ik(leg: Dictionary, target_world: Vector3) -> void:
	var hip: Node3D = leg["hip"]
	var knee: Node3D = leg["knee"]
	var upper_rest: Vector3 = leg["upper_rest"]
	var lower_rest: Vector3 = leg["lower_rest"]
	var upper_length := upper_rest.length()
	var lower_length := lower_rest.length()
	var hip_position := hip.position
	var hip_parent := hip.get_parent() as Node3D
	# With an ankle, the claw tip is the target but the tibia ends at the ankle;
	# the tarsus keeps its rest pose relative to the body, so feet stay flat.
	var goal: Vector3 = hip_parent.to_local(target_world) - (leg["tarsus_rest"] as Vector3)
	var reach: Vector3 = goal - hip_position
	if reach.length_squared() < 0.000001:
		return
	var axis: Vector3 = reach.normalized()
	var distance := clampf(reach.length(), absf(upper_length - lower_length) + 0.0005,
		upper_length + lower_length - 0.0005)
	var along := (upper_length * upper_length - lower_length * lower_length \
		+ distance * distance) / (2.0 * distance)
	var aside := sqrt(maxf(0.0, upper_length * upper_length - along * along))
	var bend: Vector3 = leg["bend_rest"]
	bend -= axis * bend.dot(axis)
	if bend.length_squared() < 0.000001:
		bend = Vector3.UP - axis * axis.y
	bend = bend.normalized()
	var knee_goal: Vector3 = hip_position + axis * along + bend * aside
	var clamped_goal: Vector3 = hip_position + axis * distance
	var upper_direction: Vector3 = (knee_goal - hip_position).normalized()
	var lower_direction: Vector3 = (clamped_goal - knee_goal).normalized()
	hip.quaternion = Quaternion(upper_rest.normalized(), upper_direction)
	knee.quaternion = Quaternion(lower_rest.normalized(), hip.quaternion.inverse() * lower_direction)
	var ankle := leg["ankle"] as Node3D
	if ankle != null:
		ankle.quaternion = (hip.quaternion * knee.quaternion).inverse()
