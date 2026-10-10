"""Integration checks for the separately saved realistic-fly Blender scene."""

from pathlib import Path
import sys
import unittest

import bpy


ROOT = Path(__file__).resolve().parents[3]
SCENE_PATH = Path(__file__).resolve().parent / "realistic_male_fruit_fly.blend"
RENDER_PATH = ROOT / "outputs" / "blender" / "realistic-fly" / "realistic_male_fruit_fly.png"


class RealisticFlySceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene_loaded = SCENE_PATH.is_file()
        if cls.scene_loaded:
            bpy.ops.wm.open_mainfile(filepath=str(SCENE_PATH))

    def require_scene(self):
        if not self.scene_loaded:
            self.skipTest("the new Blender scene has not been generated yet")

    def test_scene_is_saved_as_a_new_blend_file(self):
        self.assertTrue(SCENE_PATH.is_file(), "the separate realistic-fly .blend must exist")

    def test_fly_is_anatomically_separated_and_complete(self):
        self.require_scene()
        fly_collection = bpy.data.collections.get("FLY | D. melanogaster · male")
        self.assertIsNotNone(fly_collection)
        self.assertIsNotNone(bpy.data.objects.get("Fly model root"))

        for side in ("near", "far"):
            eye = bpy.data.objects.get(f"Compound-eye facets · {side}")
            wing = bpy.data.objects.get(f"Wing membrane · {side}")
            veins = bpy.data.objects.get(f"Wing venation · {side}")
            anatomical_side = "left" if side == "near" else "right"
            comb = bpy.data.objects.get(f"Male sex comb · {anatomical_side} foreleg")
            self.assertIsNotNone(eye, f"missing {side} compound-eye facet mesh")
            self.assertIsNotNone(wing, f"missing {side} translucent wing")
            self.assertIsNotNone(veins, f"missing {side} wing veins")
            self.assertIsNotNone(comb, f"missing male {side} foreleg sex comb")
            self.assertGreater(len(eye.data.polygons), 1000)

        head = bpy.data.objects.get("Head capsule")
        self.assertAlmostEqual(head.scale.x, 0.36, delta=0.005)
        self.assertAlmostEqual(head.scale.y, 0.34, delta=0.005)
        self.assertAlmostEqual(head.scale.z, 0.34, delta=0.005)

        for pair in ("fore", "mid", "hind"):
            for side in ("left", "right"):
                self.assertIsNotNone(bpy.data.objects.get(f"Leg assembly · {pair} {side}"))

        for segment in ("A5", "A6"):
            tergite = bpy.data.objects.get(f"Abdominal tergite {segment}")
            self.assertIsNotNone(tergite, f"missing male terminal tergite {segment}")
            self.assertIn("Male terminal cuticle", {mat.name for mat in tergite.data.materials})

    def test_render_is_camera_ready_and_present(self):
        self.require_scene()
        self.assertIsNotNone(bpy.context.scene.camera)
        self.assertEqual(bpy.context.scene.render.engine, "CYCLES")
        self.assertGreaterEqual(bpy.context.scene.render.resolution_x, 1400)
        self.assertGreaterEqual(bpy.context.scene.render.resolution_y, 1000)
        self.assertTrue(RENDER_PATH.is_file(), "the render preview must be saved beside the project outputs")
        self.assertGreater(RENDER_PATH.stat().st_size, 100_000)

        preview = bpy.data.images.load(str(RENDER_PATH), check_existing=False)
        try:
            self.assertGreaterEqual(preview.size[0], 1400)
            self.assertGreaterEqual(preview.size[1], 1000)
        finally:
            bpy.data.images.remove(preview)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RealisticFlySceneTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
