import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("ph3_nodes", Path(__file__).parents[1] / "nodes.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tensor:
    def __init__(self, shape=(1, 512, 512, 3)):
        self.shape = shape
        self.ndim = len(shape)
        self.device, self.dtype = "cpu", "float32"

    def __getitem__(self, key):
        return Tensor((len(range(*key.indices(self.shape[0]))), *self.shape[1:]))

    def to(self, **kwargs):
        return self


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def scale(image, method, mp, steps):
            self.calls.append(("scale", method, mp, steps))
            return (Tensor((image.shape[0], 1024, 1024, 3)),)

        def pad(image, width, height, color, method):
            self.calls.append(("pad", width, height, color, method))
            return (Tensor((image.shape[0], height, width, 3)),)

        def cat(images, dim):
            self.assertEqual(dim, 0)
            self.assertTrue(all(i.shape[1:] == images[0].shape[1:] for i in images))
            return Tensor((sum(i.shape[0] for i in images), *images[0].shape[1:]))

        self.context = patch.dict(sys.modules, {
            "torch": types.SimpleNamespace(Tensor=Tensor, cat=cat),
            "comfy_extras": types.ModuleType("comfy_extras"),
            "comfy_extras.nodes_images": types.SimpleNamespace(ResizeAndPadImage=types.SimpleNamespace(execute=pad)),
            "comfy_extras.nodes_post_processing": types.SimpleNamespace(ImageScaleToTotalPixels=types.SimpleNamespace(execute=scale)),
        })
        self.context.start()
        self.addCleanup(self.context.stop)
        self.node = module.PH3UpsamplerPrepare()

    def test_nine_connected_only_two_present(self):
        inputs = {f"image_{i}": None for i in range(1, 10)}
        inputs.update(image_1=Tensor(), image_2=Tensor((1, 720, 1280, 3)))
        text, images, reference = self.node.prepare("Combine <Picture 1> and <Picture 2>.", **inputs)
        self.assertEqual(images.shape, (2, 1024, 1024, 3))
        self.assertEqual(text.count("<|image_pad|>"), 2)
        self.assertIn("Edit <Picture 1>. Combine <Picture 1> and <Picture 2>.", text)
        self.assertEqual(self.calls, [("scale", "lanczos", 1.0, 1), ("pad", 1024, 1024, "white", "lanczos")])

    def test_sparse_slots_and_reference(self):
        text, images, reference = self.node.prepare("Use <Picture 8> with <Picture 2>", 8,
            image_1=Tensor((0, 20, 20, 3)), image_2=Tensor(), image_8=Tensor((1, 720, 1280, 3)))
        self.assertEqual(reference.shape, (1, 720, 1280, 3))
        self.assertIn("Edit <Picture 2>. Use <Picture 2> with <Picture 1>", text)
        self.assertEqual(images.shape[0], 2)

    def test_batch_frames_have_matching_tokens(self):
        text, images, reference = self.node.prepare("Use <Picture 2>", image_1=Tensor((3, 20, 20, 3)), image_2=Tensor())
        self.assertEqual(text.count("<|image_pad|>"), 4)
        self.assertEqual(images.shape[0], 4)
        self.assertIn("Use <Picture 4>", text)

    def test_all_nine(self):
        text, images, reference = self.node.prepare("Edit", **{f"image_{i}": Tensor() for i in range(1, 10)})
        self.assertEqual(images.shape[0], 9)
        self.assertEqual(text.count("<|image_pad|>"), 9)

    def test_over_limit(self):
        for kwargs in ({"image_1": Tensor((10, 20, 20, 3))},
                       {"image_1": Tensor(), "image_10": Tensor()},
                       {"image_1": Tensor(), "reference_image": 10}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.node.prepare("Edit", **kwargs)

    def test_invalid_inputs(self):
        for kwargs in ({}, {"image_1": "bad"}, {"image_1": Tensor(), "megapixels": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.node.prepare("Edit", **kwargs)
        with self.assertRaisesRegex(ValueError, "input is empty"):
            self.node.prepare("Use <Picture 7>", image_1=Tensor())

    def test_single_image_exact_template(self):
        text, _, _ = self.node.prepare("Hello", image_1=Tensor())
        self.assertEqual(text, "<|im_start|>user\n<Picture 1>: <|vision_start|><|image_pad|><|vision_end|>\nEdit <Picture 1>. Hello<|im_end|>\n<|im_start|>assistant\n<think>\n")

    def test_missing_reference_with_two_connected_inputs(self):
        with self.assertLogs(level="WARNING") as logs:
            text, images, reference = self.node.prepare("Use <Picture 1> and <Picture 2>", 3,
                image_1=Tensor(), image_2=Tensor())
        self.assertIn("Edit <Picture 1>.", text)
        self.assertEqual(images.shape[0], 2)
        self.assertIn("using image_1", logs.output[0])

    def test_connected_empty_reference_uses_first_actual_image(self):
        inputs = {f"image_{i}": None for i in range(1, 10)}
        inputs.update(image_3=Tensor((0, 20, 20, 3)), image_7=Tensor((1, 480, 640, 3)))
        with self.assertLogs(level="WARNING"):
            text, images, reference = self.node.prepare("Use <Picture 7>", 3, **inputs)
        self.assertIs(reference, inputs["image_7"])
        self.assertIn("Edit <Picture 1>. Use <Picture 1>", text)
        self.assertEqual(images.shape[0], 1)


    def test_separate_outputs(self):
        node = module.PH3UpsamplerPrepareSeparate()
        for count in (1, 2, 9):
            with self.subTest(count=count):
                result = node.prepare("Use <Picture 8>", 8,
                    image_8=Tensor((count, 720, 1280, 3)))
                self.assertEqual(len(result), 11)
                self.assertEqual(result[0].count("<|image_pad|>"), count)
                self.assertIn("Edit <Picture 1>. Use <Picture 1>", result[0])
                self.assertEqual(result[-1].shape, (count, 720, 1280, 3))
                for image in result[1:count + 1]:
                    self.assertEqual(image.shape, (1, 1024, 1024, 3))
                self.assertTrue(all(image is None for image in result[count + 1:10]))

    def test_original_reference_fallback_for_both_nodes(self):
        for node_class in (module.PH3UpsamplerPrepare, module.PH3UpsamplerPrepareSeparate):
            original = Tensor((2, 480, 640, 3))
            with self.subTest(node=node_class.__name__), self.assertLogs(level="WARNING"):
                result = node_class().prepare("Edit", 8, image_2=original)
            self.assertIs(result[-1], original)
            self.assertEqual(node_class.RETURN_NAMES[-1], "original_ref_image")
            self.assertEqual(node_class.RETURN_TYPES[-1], "IMAGE")
            self.assertEqual(len(result), len(node_class.RETURN_TYPES))

    def test_resolution_selector_original_dimensions(self):
        node = module.PH3ResolutionSelector()
        for count in (1, 3):
            self.assertEqual(node.select("1:1 (Square)", 16.0, 32, True,
                Tensor((count, 713, 1237, 3)))["result"], (1248, 704))
        self.assertEqual(node.select("1:1 (Square)", 16.0, 8, True,
            Tensor((1, 713, 1237, 3)))["result"], (1240, 712))
        self.assertEqual(node.select("1:1 (Square)", 16.0, 32, True,
            Tensor((1, 704, 1248, 3)))["result"], (1248, 704))
        self.assertEqual(node.select("1:1 (Square)", 16.0, 32, True,
            Tensor((1, 1, 1, 3)))["result"], (32, 32))
        for image in (None, "bad", Tensor((0, 713, 1237, 3)), Tensor((1, 0, 1237, 3))):
            with self.subTest(image=image), self.assertRaisesRegex(ValueError, "non-empty IMAGE"):
                node.select("1:1 (Square)", 1.0, 8, True, image)

    def test_resolution_selector_delegates_to_native(self):
        execute = Mock(return_value=(3552, 4736))
        native = types.SimpleNamespace(ResolutionSelector=types.SimpleNamespace(execute=execute))
        with patch.dict(sys.modules, {"comfy_extras.nodes_resolution": native}):
            for image in (None, Tensor((1, 713, 1237, 3))):
                result = module.PH3ResolutionSelector().select("3:4 (Portrait Standard)", 16.0, 32, False, image)
                self.assertEqual(result["result"], (3552, 4736))
                self.assertEqual(result["ui"], {"width": [3552], "height": [4736]})
                execute.assert_called_with("3:4 (Portrait Standard)", 16.0, 32)

    def test_separate_matches_batch(self):
        kwargs = dict(image_2=Tensor(), image_8=Tensor((2, 720, 1280, 3)))
        expected = self.node.prepare("Use <Picture 8>", 8, **kwargs)
        actual = module.PH3UpsamplerPrepareSeparate().prepare("Use <Picture 8>", 8, **kwargs)
        self.assertEqual(actual[0], expected[0])
        self.assertIs(actual[-1], kwargs["image_8"])
        self.assertIs(expected[-1], kwargs["image_8"])
        self.assertEqual(sum(image.shape[0] for image in actual[1:10] if image is not None), expected[1].shape[0])


if __name__ == "__main__":
    unittest.main()
