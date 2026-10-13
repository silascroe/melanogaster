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
# proboscis nub, bends forward at an elbow, and ends in the labella pad. The
# base is read from the nub itself in _ready (v1 and v2 heads put it in
# different places); this fallback is the v1 nub.
var proboscis_base := Vector3(-1.33, 1.02, 0.0)
const PROBOSCIS_REST_REACH := Vector3(-0.12, -0.62, 0.0)
const PROBOSCIS_MAX_LENGTH := 0.85
const PROBOSCIS_ELBOW_BULGE := 0.10
const LABELLA_PRESSED_SCALE := Vector3(1.45, 0.65, 1.45)
# Antennal grooming (engineered pose; the decision to groom comes from the brain).
# Both forelegs rise in front of the face and sweep down over the antennae.
var grooming_target := 0.0
var grooming_amount := 0.0
var groom_clock := 0.0
var antenna_points: Array[Vector3] = []  # model space, one per antenna
var dust_specks: Array[MeshInstance3D] = []
const GROOM_SWEEP_HZ := 3.2
const GROOM_BLEND_RATE := 5.0
const GROOM_PITCH := -0.07
# Courtship song (engineered pose; the decision to sing comes from the brain).
# One wing swings out sideways and vibrates. Real song is ~150-250 Hz wing
# vibration; this is a visible stand-in, not the real frequency.
var song_targets := {"near": 0.0, "far": 0.0}
var song_amounts := {"near": 0.0, "far": 0.0}
const SONG_SPREAD := 1.35
const SONG_VIBRATE_RATE := 70.0
const SONG_VIBRATE := 0.09
const SONG_BLEND_RATE := 4.0
# +1 walking forwards, -1 backing up: which way swinging feet are placed.
var step_direction := 1.0


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
		proboscis_base = model_root.to_local(nub.to_global(nub.get_aabb().get_center())) 			+ Vector3(0.0, 0.02, 0.0)
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
	_find_antennae()
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
		return proboscis_base + PROBOSCIS_REST_REACH
	# The game's sugar drop is a squashed sphere raised 0.3 radius off the floor,
	# 0.55 radius tall (see main.gd _build_sugar). Aim slightly inside its surface.
	var center := food_world + Vector3(0.0, 0.3 * food_radius, 0.0)
	var radii := Vector3(food_radius, 0.55 * food_radius, food_radius)
	var mouth := model_root.to_global(proboscis_base)
	var unit := (mouth - center) / radii
	if unit.length() < 0.001:
		return proboscis_base + PROBOSCIS_REST_REACH
	var surface := center + unit.normalized() * radii * 0.9
	var reach := model_root.to_local(surface) - proboscis_base
	if reach.y > -0.2:
		return proboscis_base + PROBOSCIS_REST_REACH  # drop not below the mouth; just extend
	return proboscis_base + reach.limit_length(PROBOSCIS_MAX_LENGTH)


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
	var tip := proboscis_base.lerp(_proboscis_full_tip(), e)
	var showing := e > 0.02 and proboscis_segments.size() == 2
	for segment in proboscis_segments:
		segment.visible = showing
	proboscis_elbow.visible = showing
	if showing:
		# The elbow bows forward (-X), like the joint between rostrum and haustellum.
		var elbow := (proboscis_base + tip) * 0.5 + Vector3(-PROBOSCIS_ELBOW_BULGE * e, 0.0, 0.0)
		_place_segment(proboscis_segments[0], proboscis_base, elbow)
		_place_segment(proboscis_segments[1], elbow, tip)
		proboscis_elbow.position = elbow
	for part in mouth_parts:
		var node: Node3D = part["node"]
		var rest: Vector3 = part["position"]
		var rest_scale: Vector3 = part["scale"]
		# The paired lobes meet at the tip and spread into a flat pad on the food.
		node.position = rest.lerp(tip + Vector3(0.0, 0.0, rest.z * 1.4), e)
		node.scale = rest_scale.lerp(rest_scale * LABELLA_PRESSED_SCALE, e)


## Start or stop antennal grooming (forelegs sweep the face).
func set_grooming(grooming: bool) -> void:
	grooming_target = 1.0 if grooming else 0.0


## Start or stop courtship song with the wing on `side` ("R" or "L").
func set_singing(singing: bool, side: String) -> void:
	# The far wing is the fly's right wing, the near wing its left.
	song_targets["far"] = 1.0 if singing and side == "R" else 0.0
	song_targets["near"] = 1.0 if singing and side == "L" else 0.0


## Show dust on the antennae, 0 (clean) to 1.
## Backing up: feet now land behind their rest spots instead of ahead.
func set_backing(backing: bool) -> void:
	step_direction = -1.0 if backing else 1.0


func set_dust(amount: float) -> void:
	for speck in dust_specks:
		speck.visible = amount > 0.02
		speck.scale = Vector3.ONE * clampf(amount, 0.0, 1.0)


func _find_antennae() -> void:
	var dust_material := StandardMaterial3D.new()
	dust_material.albedo_color = Color(0.80, 0.76, 0.66)
	dust_material.roughness = 0.9
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	for node in model_root.find_children("antenna flagellum*", "MeshInstance3D", true, false):
		var antenna := node as MeshInstance3D
		var center := model_root.to_local(antenna.to_global(antenna.get_aabb().get_center()))
		antenna_points.append(center)
		for k in range(14):
			var speck := MeshInstance3D.new()
			var mesh := SphereMesh.new()
			mesh.radius = rng.randf_range(0.005, 0.010)
			mesh.height = mesh.radius * 2.0
			speck.mesh = mesh
			speck.material_override = dust_material
			speck.position = center + Vector3(rng.randf_range(-0.055, -0.03),
				rng.randf_range(-0.07, 0.07), rng.randf_range(-0.03, 0.03))
			speck.visible = false
			model_root.add_child(speck)
			dust_specks.append(speck)
	if antenna_points.size() != 2:
		push_warning("Expected two antennae for grooming; found %d." % antenna_points.size())


func advance(delta: float, walking: bool, speed: float) -> void:
	grooming_amount = move_toward(grooming_amount, grooming_target, delta * GROOM_BLEND_RATE)
	for wing in song_amounts:
		song_amounts[wing] = move_toward(song_amounts[wing], song_targets[wing], delta * SONG_BLEND_RATE)
	if grooming_amount > 0.0:
		groom_clock += delta
	else:
		groom_clock = 0.0
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
	for wing in [wing_near, wing_far]:
		if wing != null:
			wing.rotation = Vector3.ZERO
	song_targets = {"near": 0.0, "far": 0.0}
	song_amounts = {"near": 0.0, "far": 0.0}
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
	else:
		target_pitch = GROOM_PITCH * grooming_amount
	body_motion.rotation.x = lerpf(body_motion.rotation.x, target_pitch,
		clampf(delta * 10.0, 0.0, 1.0))
	var wing_rate := 56.0 if is_flying() else (48.0 if airborne else 6.0)
	var wing_span := 0.86 if is_flying() else (0.38 if airborne else 0.025)
	if wing_near != null:
		wing_near.rotation.x = sin(visual_clock * wing_rate) * wing_span
		_sing_wing(wing_near, float(song_amounts["near"]), -1.0)
	if wing_far != null:
		wing_far.rotation.x = -sin(visual_clock * wing_rate) * wing_span
		_sing_wing(wing_far, float(song_amounts["far"]), 1.0)
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
				leg["swing_to"] = rest_ground + forward * lead * step_direction
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
		var groom := grooming_amount if not airborne and not is_flying() else 0.0
		if groom > 0.0 and index % 3 == 0 and antenna_points.size() == 2:
			_groom_foreleg(leg, target, groom)
		else:
			_solve_leg_ik(leg, target)


func _groom_foreleg(leg: Dictionary, standing_claw: Vector3, groom: float) -> void:
	# The ankle travels from above the antenna to below it while the tarsus lies
	# across the face, so the tarsus brushes down over the antenna each sweep.
	var parent_basis: Basis = ((leg["hip"] as Node3D).get_parent() as Node3D).global_transform.basis
	var tarsus_rest: Vector3 = leg["tarsus_rest"]
	var side := signf((leg["rest_model_foot"] as Vector3).z)
	var antenna: Vector3 = antenna_points[0] if signf(antenna_points[0].z) == side else antenna_points[1]
	var phase := groom_clock * GROOM_SWEEP_HZ + (0.0 if side > 0.0 else 0.12)
	var sweep := 0.5 - 0.5 * cos(TAU * phase)
	var ankle_model := antenna + Vector3(lerpf(-0.07, -0.12, sweep), lerpf(0.17, -0.09, sweep),
		side * lerpf(0.13, 0.06, sweep))
	var tarsus_model := Vector3(-0.25, -0.50, -0.83 * side).normalized()
	var standing_ankle: Vector3 = standing_claw - parent_basis * tarsus_rest
	var ankle_goal: Vector3 = standing_ankle.lerp(model_root.to_global(ankle_model), groom)
	var rest_direction: Vector3 = (parent_basis * tarsus_rest).normalized()
	var groom_direction := (model_root.global_transform.basis * tarsus_model).normalized()
	var direction: Vector3 = rest_direction.slerp(groom_direction, groom)
	_solve_leg_ik(leg, ankle_goal + parent_basis * tarsus_rest)
	var ankle := leg["ankle"] as Node3D
	if ankle != null:
		var local_direction := (parent_basis.inverse() * direction).normalized()
		var hip_knee := (leg["hip"] as Node3D).quaternion * (leg["knee"] as Node3D).quaternion
		ankle.quaternion = hip_knee.inverse() * Quaternion(tarsus_rest.normalized(), local_direction)


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


func _sing_wing(wing: Node3D, amount: float, outward: float) -> void:
	# Swing the wing out from over the abdomen to the side, then vibrate it.
	var eased := amount * amount * (3.0 - 2.0 * amount)
	wing.rotation.y = outward * SONG_SPREAD * eased
	wing.rotation.x += sin(visual_clock * SONG_VIBRATE_RATE) * SONG_VIBRATE * eased
