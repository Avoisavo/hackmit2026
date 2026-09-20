"""Offline detector geometry and drawing tests; no weights or camera required."""
import io
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from object_boxes import ObjectBoxDetector, ObjectBoxError


class Tensor:
    def __init__(self, values):
        self.values = values

    def cpu(self):
        return self

    def tolist(self):
        return self.values


def prediction(rows, names=None):
    return [SimpleNamespace(
        names=names or {0: "cup", 1: "toy car"},
        boxes=SimpleNamespace(
            xyxy=Tensor([row[:4] for row in rows]),
            conf=Tensor([row[4] for row in rows]),
            cls=Tensor([row[5] for row in rows]),
        ),
    )]


class ObjectBoxTests(unittest.TestCase):
    def setUp(self):
        self.source = Image.new("RGB", (200, 100), (20, 20, 20))
        output = io.BytesIO()
        self.source.save(output, "JPEG")
        self.jpeg = output.getvalue()
        self.model = SimpleNamespace(predict=Mock(return_value=prediction([])), to=Mock(), predictor=None)
        self.factory = Mock(return_value=self.model)
        self.standard_factory = Mock(return_value=self.model)
        self.modules = patch.dict(sys.modules, {
            "ultralytics": SimpleNamespace(YOLOE=self.factory, YOLO=self.standard_factory),
            "torch": SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True))),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        environment = patch.dict(os.environ, {"YOLO_CONFIG_DIR": "/offline-test-config", "MPLCONFIGDIR": "/offline-test-fonts"})
        environment.start()
        self.addCleanup(environment.stop)
        self.weights = Path(__file__).with_name("yoloe-26n-seg-pf.pt")
        self.standard_weights = Path(__file__).with_name("yolo11n.pt")
        exists = patch("object_boxes.Path.is_file", lambda path: path in (self.weights, self.standard_weights))
        exists.start()
        self.addCleanup(exists.stop)
        self.detector = ObjectBoxDetector(str(self.weights))

    def test_standard_detector_uses_yolo_loader_for_common_object_labels(self):
        self.model.predict.return_value = prediction([[20, 30, 100, 90, .741, 56]], {56: "chair"})
        detector = ObjectBoxDetector(str(self.standard_weights))
        result = detector.detect(self.jpeg)
        self.assertEqual(result["detections"][0]["label"], "chair")
        self.standard_factory.assert_called_once_with(str(self.standard_weights), verbose=False)
        self.factory.assert_not_called()

    def test_default_confidence_hides_weak_labels_and_matches_model_threshold(self):
        self.model.predict.return_value = prediction([[20, 30, 100, 90, .32, 0]])
        result = self.detector.detect(self.jpeg)
        self.assertEqual(result["detections"], [])
        self.assertEqual(self.model.predict.call_args.kwargs["conf"], .5)

    def test_explicit_lower_confidence_is_applied_to_prediction_and_postprocessing(self):
        detector = ObjectBoxDetector(str(self.weights), confidence=.25)
        self.model.predict.return_value = prediction([[20, 30, 100, 90, .32, 0]])
        result = detector.detect(self.jpeg)
        self.assertEqual(len(result["detections"]), 1)
        self.assertEqual(self.model.predict.call_args.kwargs["conf"], .25)

    def test_invalid_confidence_is_rejected_before_loading_a_model(self):
        for value in [0, -1, 1.1, float("nan"), float("inf"), True, "0.5"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ObjectBoxDetector(str(self.weights), confidence=value)
        self.factory.assert_not_called()

    def test_model_load_is_lazy_and_reused_for_later_frames(self):
        self.factory.assert_not_called()
        first = self.detector.detect(self.jpeg)
        second = self.detector.detect(self.jpeg)
        self.assertIsInstance(first, dict)
        self.assertIsInstance(second, dict)
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(first["device"], "mps")
        self.assertEqual(first["detections"], [])

    def test_real_detection_geometry_is_normalized_and_drawn_on_source_size(self):
        self.model.predict.return_value = prediction([[20, 30, 100, 90, .95, 0]])
        result = self.detector.detect(self.jpeg)
        self.assertIsInstance(result, dict)
        self.assertEqual((result["width"], result["height"]), (200, 100))
        self.assertEqual(result["detections"], [{"label": "cup", "confidence": .95, "xyxy": [.1, .3, .5, .9]}])
        rendered = Image.open(io.BytesIO(result["jpeg"])).convert("RGB")
        self.assertEqual(rendered.size, (200, 100))
        self.assertGreater(rendered.getpixel((21, 36))[1], 100)
        self.assertLess(abs(rendered.getpixel((150, 80))[0] - 20), 8)
        request = self.model.predict.call_args.kwargs
        self.assertEqual(request["source"].size, (200, 100))
        self.assertFalse(request["save"])
        self.assertFalse(request["verbose"])
        self.assertTrue(request["agnostic_nms"])

    def test_clip_bounds_skip_invalid_boxes_and_keep_large_close_objects(self):
        self.model.predict.return_value = prediction([
            [-30, 20, 240, 90, .9, 0],
            [20, 20, 20, 70, .8, 0],
            [10, 20, 50, 60, .2, 0],
            [10, 20, float("nan"), 60, .8, 0],
            [10, 20, 50, 60, float("nan"), 0],
            [10, 20, 50, 60, .8, 99],
        ])
        result = self.detector.detect(self.jpeg)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["detections"], [{"label": "cup", "confidence": .9, "xyxy": [0., .2, 1., .9]}])

    def test_near_full_frame_scene_box_does_not_hide_a_large_close_object(self):
        self.model.predict.return_value = prediction([
            [0, 0, 200, 100, .95, 0],
            [20, 0, 180, 100, .9, 1],
        ], {0: "rock concert", 1: "chair"})
        result = self.detector.detect(self.jpeg)
        self.assertEqual(result["detections"], [{"label": "chair", "confidence": .9, "xyxy": [.1, 0., .9, 1.]}])

    def test_overlapping_categories_are_not_drawn_as_duplicate_objects(self):
        self.model.predict.return_value = prediction([
            [20, 30, 100, 90, .95, 0], [21, 31, 101, 91, .7, 1],
        ])
        result = self.detector.detect(self.jpeg)
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result["detections"]), 1)
        self.assertEqual(result["detections"][0]["label"], "cup")

    def test_at_most_thirty_visible_boxes_are_returned(self):
        rows = [[(i % 10) * 20, (i // 10) * 20, (i % 10) * 20 + 8, (i // 10) * 20 + 8, .8, 0]
                for i in range(40)]
        self.model.predict.return_value = prediction(rows)
        result = self.detector.detect(self.jpeg)
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result["detections"]), 30)

    def test_detector_labels_are_printable_bounded_and_never_replaced_by_inventory(self):
        self.model.predict.return_value = prediction([[10, 30, 40, 70, .8, 0]], {0: "red\ncar\x00" + "X" * 100})
        result = self.detector.detect(self.jpeg)
        self.assertIsInstance(result, dict)
        label = result["detections"][0]["label"]
        self.assertTrue(label.isprintable())
        self.assertLessEqual(len(label), 48)
        self.assertTrue(label.startswith("red car"))

    def test_narrow_label_chip_keeps_the_confidence_visible(self):
        self.model.predict.return_value = prediction([[10, 30, 40, 70, .8, 0]], {0: "a very long but valid detector category name"})
        painted_text = []
        draw_factory = ImageDraw.Draw

        def record_drawing(image):
            draw = draw_factory(image)
            paint = draw.text
            def text_at(position, text, **kwargs):
                painted_text.append(text)
                return paint(position, text, **kwargs)
            draw.text = text_at
            return draw

        with patch("object_boxes.ImageDraw.Draw", side_effect=record_drawing):
            self.detector.detect(self.jpeg)
        self.assertEqual(len(painted_text), 1)
        self.assertTrue(painted_text[0].endswith("80%"))

    def test_mps_prediction_failure_falls_back_to_cpu_and_stays_there(self):
        self.model.predict.side_effect = [RuntimeError("private image details"), prediction([]), prediction([])]
        first = self.detector.detect(self.jpeg)
        second = self.detector.detect(self.jpeg)
        self.assertIsInstance(first, dict)
        self.assertIsInstance(second, dict)
        self.assertEqual(first["device"], "cpu")
        self.assertEqual(second["device"], "cpu")
        self.assertEqual([call.kwargs["device"] for call in self.model.predict.call_args_list], ["mps", "cpu", "cpu"])
        self.model.to.assert_called_with("cpu")

    def test_failed_prediction_is_sanitized_instead_of_empty_success(self):
        self.model.predict.side_effect = RuntimeError("private-image-details")
        with self.assertRaises(ObjectBoxError) as caught:
            self.detector.detect(self.jpeg)
        self.assertNotIn("private-image-details", str(caught.exception))

    def test_invalid_image_never_loads_a_model(self):
        for data in [b"not-jpeg", b"", None]:
            with self.subTest(data=data), self.assertRaises(ObjectBoxError):
                self.detector.detect(data)
        self.factory.assert_not_called()

    def test_missing_weights_do_not_trigger_an_automatic_download(self):
        detector = ObjectBoxDetector("/missing/offline-model.pt")
        with self.assertRaises(ObjectBoxError):
            detector.detect(self.jpeg)
        self.factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
