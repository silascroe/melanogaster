"""Blender integration checks for the separate high-detail hero fly scene."""

from pathlib import Path
import sys
import unittest

import bpy


ROOT = Path(__file__).resolve().parents[3]
SCENE_PATH = Path(__file__).resolve().parent / "male_drosophila_hero.blend"
RENDER_PATH = ROOT / "outputs" / "blender" / "realistic-fly-hero" / "male_drosophila_hero.png"
DETAIL_RENDER_PATH = ROOT / "outputs" / "blender" / "realistic-fly-hero" / "male_drosophila_hero-detail.png"


class HeroFlySceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene_loaded = SCENE_PATH.is_file()
        if cls.scene_loaded:
            bpy.ops.wm.open_mainfile(filepath=str(SCENE_PATH))

    def require_scene(self):
        if not self.scene_loaded:
            self.skipTest("hero scene is not built yet")

    def test_scene_is_a_separate_saved_artifact(self):
        self.assertTrue(SCENE_PATH.is_file(), "build a new .blend without replacing either existing scene")

    def test_body_is_custom_continuous_geometry_with_male_pattern(self):
        self.require_scene()
        abdomen = bpy.data.objects.get("Continuous sculpted abdomen shell")
        self.assertIsNotNone(abdomen)
        self.assertEqual(abdomen.type, "MESH")
        self.assertGreater(len(abdomen.data.polygons), 3000)
        self.assertEqual(abdomen.get("segment_count"), 6)
        self.assertEqual(abdomen.get("male_terminal_tergites"), "A5-A6")
        self.assertGreater(len(bpy.data.objects["Thoracic microtrichia"].data.splines), 2500)

    def test_macro_anatomy_and_surface_detail_are_present(self):
        self.require_scene()
        fly = bpy.data.collections.get("FLY | male Drosophila hero")
        self.assertIsNotNone(fly)
        for name in ("Head capsule · sculpted", "Scutellum · shell", "Proboscis · labellum", "Aristae · plumose pair"):
            self.assertIsNotNone(bpy.data.objects.get(name), f"missing {name}")

        for side in ("near", "far"):
            eye = bpy.data.objects.get(f"Corneal ommatidia · {side}")
            wing = bpy.data.objects.get(f"Hyaline wing membrane · {side}")
            veins = bpy.data.objects.get(f"Wing vein network · {side}")
            anatomical_side = "left" if side == "near" else "right"
            comb = bpy.data.objects.get(f"Male sex comb · {anatomical_side} fore tarsus")
            self.assertIsNotNone(eye)
            self.assertGreaterEqual(eye.get("lens_count", 0), 700)
            self.assertIsNotNone(wing)
            self.assertIsNotNone(veins)
            self.assertGreaterEqual(veins.get("vein_count", 0), 9)
            self.assertIsNotNone(comb)
            self.assertEqual(comb.get("tooth_count"), 11)

        for pair in ("fore", "mid", "hind"):
            for side in ("left", "right"):
                self.assertIsNotNone(bpy.data.objects.get(f"Leg assembly · {pair} {side}"))

        membrane = bpy.data.materials.get("Wing membrane · optically thin")
        self.assertIsNotNone(membrane)
        principled = membrane.node_tree.nodes.get("Principled BSDF")
        self.assertGreater(principled.inputs["Transmission Weight"].default_value, 0.7)
        self.assertLess(membrane.node_tree.nodes.get("Mix Shader").inputs[0].default_value, 0.12)

    def test_saved_render_is_high_resolution_and_gpu_configured(self):
        self.require_scene()
        scene = bpy.context.scene
        self.assertIsNotNone(scene.camera)
        self.assertEqual(scene.render.engine, "CYCLES")
        self.assertEqual(scene.cycles.device, "GPU")
        self.assertGreaterEqual(scene.cycles.samples, 64)
        self.assertGreaterEqual(scene.render.resolution_x, 1920)
        self.assertGreaterEqual(scene.render.resolution_y, 1440)
        self.assertTrue(RENDER_PATH.is_file(), "render the scene to its new output path")
        self.assertGreater(RENDER_PATH.stat().st_size, 150_000)
        self.assertTrue(DETAIL_RENDER_PATH.is_file(), "render a close-up anatomy plate")
        self.assertGreater(DETAIL_RENDER_PATH.stat().st_size, 100_000)
        image = bpy.data.images.load(str(RENDER_PATH), check_existing=False)
        try:
            self.assertGreaterEqual(image.size[0], 1920)
            self.assertGreaterEqual(image.size[1], 1440)
        finally:
            bpy.data.images.remove(image)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HeroFlySceneTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
