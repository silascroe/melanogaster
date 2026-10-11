extends Node3D

# Presentation-only set dressing: a fly-scale kitchen table. The walkable area
# is the linen placemat (main.gd still clamps the fly to +/-8 units); the giant
# props sit outside it, so nothing here affects movement or the neural circuit.

const MAT_HALF := 8.6


func _ready() -> void:
	_build_lighting()
	_build_table()
	_build_placemat()
	_build_apple(Vector3(-15.0, 0.0, -13.0), 6.0)
	_build_mug(Vector3(15.5, 0.0, -11.0))
	_build_orange(Vector3(13.0, 0.0, 15.5), 5.0)
	_build_sugar_cubes(Vector3(-13.0, 0.0, 11.0))
	_build_crumbs()


func _build_lighting() -> void:
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-38.0, -48.0, 0.0)
	sun.light_color = Color(1.0, 0.90, 0.76)
	sun.light_energy = 1.0
	sun.shadow_enabled = true
	sun.shadow_blur = 1.6
	sun.directional_shadow_max_distance = 60.0
	add_child(sun)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-25.0, 140.0, 0.0)
	fill.light_color = Color(0.70, 0.80, 1.0)
	fill.light_energy = 0.18
	add_child(fill)

	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.42, 0.38, 0.34)
	sky_material.sky_horizon_color = Color(0.66, 0.56, 0.44)
	sky_material.ground_bottom_color = Color(0.20, 0.13, 0.08)
	sky_material.ground_horizon_color = Color(0.62, 0.48, 0.34)
	var sky := Sky.new()
	sky.sky_material = sky_material
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_energy = 0.35
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.tonemap_exposure = 0.9
	environment.glow_enabled = false
	environment.glow_intensity = 0.35
	environment.glow_bloom = 0.05
	# Soft depth haze makes the far table read as out-of-focus macro background.
	environment.fog_enabled = true
	environment.fog_light_color = Color(0.55, 0.47, 0.38)
	environment.fog_density = 0.012
	environment.fog_sky_affect = 0.0
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	add_child(world_environment)


func _build_table() -> void:
	var grain := FastNoiseLite.new()
	grain.noise_type = FastNoiseLite.TYPE_PERLIN
	grain.frequency = 0.035
	grain.fractal_octaves = 4
	grain.seed = 7
	var ramp := Gradient.new()
	ramp.set_color(0, Color(0.30, 0.17, 0.08))
	ramp.set_color(1, Color(0.58, 0.36, 0.19))
	ramp.add_point(0.45, Color(0.44, 0.26, 0.13))
	ramp.add_point(0.55, Color(0.36, 0.20, 0.10))
	var albedo := NoiseTexture2D.new()
	albedo.width = 512
	albedo.height = 512
	albedo.seamless = true
	albedo.noise = grain
	albedo.color_ramp = ramp
	var normal := NoiseTexture2D.new()
	normal.width = 512
	normal.height = 512
	normal.seamless = true
	normal.noise = grain
	normal.as_normal_map = true
	normal.bump_strength = 3.0
	var material := StandardMaterial3D.new()
	material.albedo_texture = albedo
	material.normal_enabled = true
	material.normal_texture = normal
	material.normal_scale = 0.4
	material.roughness = 0.42
	# Stretch the noise along one axis so it reads as long wood grain.
	material.uv1_scale = Vector3(1.5, 12.0, 1.0)
	var mesh := PlaneMesh.new()
	mesh.size = Vector2(140.0, 140.0)
	var table := MeshInstance3D.new()
	table.mesh = mesh
	table.position.y = -0.06
	table.material_override = material
	add_child(table)


func _build_placemat() -> void:
	# Red-and-white gingham: overlapping stripes give three tones.
	var image := Image.create(64, 64, true, Image.FORMAT_RGB8)
	var white := Color(0.80, 0.77, 0.72)
	var pink := Color(0.74, 0.42, 0.40)
	var red := Color(0.60, 0.16, 0.15)
	for y in range(64):
		for x in range(64):
			var stripe_x := x < 32
			var stripe_y := y < 32
			var color := white
			if stripe_x and stripe_y:
				color = red
			elif stripe_x or stripe_y:
				color = pink
			image.set_pixel(x, y, color)
	image.generate_mipmaps()
	var weave := FastNoiseLite.new()
	weave.frequency = 0.9
	weave.seed = 3
	var bump := NoiseTexture2D.new()
	bump.width = 256
	bump.height = 256
	bump.seamless = true
	bump.noise = weave
	bump.as_normal_map = true
	bump.bump_strength = 2.0
	var material := StandardMaterial3D.new()
	material.albedo_texture = ImageTexture.create_from_image(image)
	material.normal_enabled = true
	material.normal_texture = bump
	material.normal_scale = 0.35
	material.roughness = 0.95
	material.uv1_scale = Vector3(8.0, 8.0, 1.0)
	var mat_mesh := BoxMesh.new()
	mat_mesh.size = Vector3(MAT_HALF * 2.0, 0.06, MAT_HALF * 2.0)
	var placemat := MeshInstance3D.new()
	placemat.mesh = mat_mesh
	placemat.position.y = -0.03
	placemat.material_override = material
	add_child(placemat)
	# A stitched border so the edge of the walkable area is visible.
	var stitch := _plain(Color(0.92, 0.90, 0.85), 0.8)
	for side in [-1.0, 1.0]:
		_box(Vector3(0.0, 0.005, side * (MAT_HALF - 0.35)), Vector3(MAT_HALF * 2.0 - 0.5, 0.012, 0.07), stitch)
		_box(Vector3(side * (MAT_HALF - 0.35), 0.005, 0.0), Vector3(0.07, 0.012, MAT_HALF * 2.0 - 0.5), stitch)


func _build_apple(base: Vector3, radius: float) -> void:
	var skin := FastNoiseLite.new()
	skin.frequency = 0.02
	skin.seed = 11
	var ramp := Gradient.new()
	ramp.set_color(0, Color(0.55, 0.05, 0.05))
	ramp.set_color(1, Color(0.86, 0.22, 0.12))
	ramp.add_point(0.8, Color(0.85, 0.55, 0.18))
	var albedo := NoiseTexture2D.new()
	albedo.seamless = true
	albedo.noise = skin
	albedo.color_ramp = ramp
	var material := StandardMaterial3D.new()
	material.albedo_texture = albedo
	material.roughness = 0.28
	material.clearcoat_enabled = true
	material.clearcoat = 0.6
	var apple := _sphere(base + Vector3(0.0, radius * 0.92, 0.0), Vector3(radius, radius * 0.92, radius), material)
	apple.rotation_degrees.z = 6.0
	var stem := MeshInstance3D.new()
	var stem_mesh := CylinderMesh.new()
	stem_mesh.top_radius = 0.12
	stem_mesh.bottom_radius = 0.2
	stem_mesh.height = 2.0
	stem.mesh = stem_mesh
	stem.position = base + Vector3(0.2, radius * 1.84 + 0.7, 0.0)
	stem.rotation_degrees.z = -14.0
	stem.material_override = _plain(Color(0.28, 0.18, 0.08), 0.8)
	add_child(stem)
	var leaf := _sphere(base + Vector3(1.1, radius * 1.84 + 0.9, 0.2), Vector3(1.3, 0.08, 0.6),
		_plain(Color(0.26, 0.52, 0.16), 0.6))
	leaf.rotation_degrees = Vector3(0.0, 25.0, 18.0)


func _build_mug(base: Vector3) -> void:
	var ceramic := _plain(Color(0.20, 0.38, 0.52), 0.18)
	ceramic.clearcoat_enabled = true
	var body := MeshInstance3D.new()
	var body_mesh := CylinderMesh.new()
	body_mesh.top_radius = 4.6
	body_mesh.bottom_radius = 4.2
	body_mesh.height = 10.0
	body.mesh = body_mesh
	body.position = base + Vector3(0.0, 5.0, 0.0)
	body.material_override = ceramic
	add_child(body)
	var coffee := MeshInstance3D.new()
	var coffee_mesh := CylinderMesh.new()
	coffee_mesh.top_radius = 4.25
	coffee_mesh.bottom_radius = 4.25
	coffee_mesh.height = 0.1
	coffee.mesh = coffee_mesh
	coffee.position = base + Vector3(0.0, 9.3, 0.0)
	coffee.material_override = _plain(Color(0.16, 0.08, 0.04), 0.1)
	add_child(coffee)
	var handle := MeshInstance3D.new()
	var handle_mesh := TorusMesh.new()
	handle_mesh.inner_radius = 1.9
	handle_mesh.outer_radius = 2.8
	handle.mesh = handle_mesh
	handle.position = base + Vector3(-4.9, 5.2, 0.0)
	handle.rotation_degrees = Vector3(90.0, 0.0, 0.0)
	handle.material_override = ceramic
	add_child(handle)


func _build_orange(base: Vector3, radius: float) -> void:
	var peel := FastNoiseLite.new()
	peel.noise_type = FastNoiseLite.TYPE_CELLULAR
	peel.frequency = 0.18
	var bump := NoiseTexture2D.new()
	bump.seamless = true
	bump.noise = peel
	bump.as_normal_map = true
	bump.bump_strength = 4.0
	var material := _plain(Color(0.95, 0.48, 0.08), 0.5)
	material.normal_enabled = true
	material.normal_texture = bump
	material.uv1_scale = Vector3(3.0, 3.0, 1.0)
	_sphere(base + Vector3(0.0, radius * 0.95, 0.0), Vector3(radius, radius * 0.95, radius), material)


func _build_sugar_cubes(base: Vector3) -> void:
	var sugar := _plain(Color(0.97, 0.96, 0.93), 0.9)
	var cube_a := _box(base + Vector3(0.0, 1.1, 0.0), Vector3(2.2, 2.2, 2.2), sugar)
	cube_a.rotation_degrees.y = 18.0
	var cube_b := _box(base + Vector3(2.6, 1.1, 1.4), Vector3(2.2, 2.2, 2.2), sugar)
	cube_b.rotation_degrees.y = -11.0
	var cube_c := _box(base + Vector3(1.2, 3.3, 0.6), Vector3(2.2, 2.2, 2.2), sugar)
	cube_c.rotation_degrees.y = 40.0


func _build_crumbs() -> void:
	# Small, flat bread crumbs on the placemat; purely decorative.
	var rng := RandomNumberGenerator.new()
	rng.seed = 21
	var crust := _plain(Color(0.78, 0.55, 0.28), 0.9)
	for index in range(14):
		var spot := Vector3(rng.randf_range(-7.0, 7.0), 0.03, rng.randf_range(-7.0, 7.0))
		var size := rng.randf_range(0.08, 0.2)
		var crumb := _box(spot, Vector3(size, size * 0.5, size * rng.randf_range(0.6, 1.3)), crust)
		crumb.rotation_degrees.y = rng.randf_range(0.0, 180.0)


func _plain(color: Color, roughness: float) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	return material


func _sphere(at: Vector3, scale_vector: Vector3, material: Material) -> MeshInstance3D:
	var mesh := SphereMesh.new()
	mesh.radius = 1.0
	mesh.height = 2.0
	mesh.radial_segments = 48
	mesh.rings = 24
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = at
	instance.scale = scale_vector
	instance.material_override = material
	add_child(instance)
	return instance


func _box(at: Vector3, box_size: Vector3, material: Material) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = box_size
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = at
	instance.material_override = material
	add_child(instance)
	return instance
