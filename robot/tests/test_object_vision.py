"""Offline scene counting and deterministic arithmetic lesson contracts."""

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import object_vision as vision


def observation(count, clear=True, objects=None):
    return {
        "objects": objects if objects is not None else [{"label": "toy block", "count": 2}],
        "target_count": count,
        "scene_clear": clear,
        "reason": "The selected objects are fully visible." if clear else "Objects overlap.",
    }


def api_response(data, status=200):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(data).encode("utf-8")
    return response


def completed_scene(data):
    return {
        "id": "resp_offline_fixture", "object": "response", "created_at": 0,
        "status": "completed", "error": None, "incomplete_details": None,
        "output": [{
            "id": "msg_offline_fixture", "type": "message", "status": "completed",
            "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(data), "annotations": []}],
        }],
        "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
    }


class ProviderTests(unittest.TestCase):
    # The image boundary is mocked; no camera or provider request is made.
    jpeg = b"\xff\xd8offline-test-jpeg\xff\xd9"

    def test_scene_request_uses_selected_object_image_and_strict_private_json_contract(self):
        scene = observation(2, objects=[{"label": "cup", "count": 2}, {"label": "book", "count": 1}])
        captured = []

        def fake_post(url, **kwargs):
            captured.append((url, kwargs))
            return api_response(completed_scene(scene))

        with patch("object_vision.requests.post", side_effect=fake_post):
            result = vision.analyze_scene(self.jpeg, "offline-secret", "gpt-4.1-mini", "cups")
        self.assertEqual(result, scene)
        self.assertEqual(len(captured), 1)
        url, request = captured[0]
        self.assertEqual(url, "https://api.openai.com/v1/responses")
        self.assertFalse(request["allow_redirects"])
        self.assertTrue(all(0 < timeout <= 45 for timeout in request["timeout"]))
        payload = request["json"]
        self.assertFalse(payload["store"])
        self.assertEqual(payload["model"], "gpt-4.1-mini")
        self.assertEqual(request["headers"]["Authorization"], "Bearer offline-secret")
        self.assertNotIn("offline-secret", json.dumps(payload))
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        schema = payload["text"]["format"]["schema"]
        self.assertEqual(set(schema["required"]), {"objects", "target_count", "scene_clear", "reason"})
        self.assertFalse(schema["additionalProperties"])
        self.assertLessEqual(payload["max_output_tokens"], 2000)
        content = payload["input"][0]["content"]
        target = next(item["text"] for item in content if item["type"] == "input_text")
        self.assertIn('"cups"', target)
        image = next(item for item in content if item["type"] == "input_image")
        self.assertEqual(image["detail"], "high")
        self.assertEqual(base64.b64decode(image["image_url"].split(",", 1)[1]), self.jpeg)

    def test_zero_and_uncertain_results_preserve_their_distinction(self):
        for scene in [observation(0, objects=[]), observation(None, False, objects=[])]:
            with self.subTest(scene=scene), patch("object_vision.requests.post", return_value=api_response(completed_scene(scene))):
                self.assertEqual(vision.analyze_scene(self.jpeg, "key", "model", "cups"), scene)

    def test_specific_visual_names_are_preserved_without_summing_unrelated_objects(self):
        scene = observation(3, objects=[
            {"label": "red toy car", "count": 2},
            {"label": "blue toy car", "count": 1},
            {"label": "yellow banana", "count": 1},
        ])
        with patch("object_vision.requests.post", return_value=api_response(completed_scene(scene))):
            result = vision.analyze_scene(self.jpeg, "key", "model", "toy cars")
        self.assertEqual(result, scene)

    def test_timeout_is_sanitized_and_is_not_retried(self):
        calls = []

        def timeout(*args, **kwargs):
            calls.append(True)
            raise requests.Timeout("Authorization: Bearer private-key data:image/jpeg;base64,private-image")

        with patch("object_vision.requests.post", side_effect=timeout):
            with self.assertRaises(vision.VisionError) as caught:
                vision.analyze_scene(self.jpeg, "private-key", "model", "cups")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("private-key", str(caught.exception))
        self.assertNotIn("private-image", str(caught.exception))

    def test_http_errors_do_not_echo_provider_body_or_follow_redirects(self):
        for status in [302, 401, 403, 429, 500]:
            with self.subTest(status=status), patch("object_vision.requests.post", return_value=api_response({"error": "secret-key raw-image"}, status)):
                with self.assertRaises(vision.VisionError) as caught:
                    vision.analyze_scene(self.jpeg, "secret-key", "model", "cups")
                self.assertNotIn("secret-key", str(caught.exception))
                self.assertNotIn("raw-image", str(caught.exception))

    def test_refusals_incomplete_or_missing_outputs_are_not_zero_counts(self):
        refused = completed_scene(observation(2))
        refused["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot analyze this image."}]
        unfinished_message = completed_scene(observation(2))
        unfinished_message["output"][0]["status"] = "incomplete"
        for result in [refused, unfinished_message,
                       {"status": "incomplete", "output": [], "incomplete_details": {"reason": "max_output_tokens"}},
                       {"status": "completed", "output": []}, {"status": "failed"}, None]:
            with self.subTest(result=result), patch("object_vision.requests.post", return_value=api_response(result)):
                with self.assertRaises(vision.VisionError):
                    vision.analyze_scene(self.jpeg, "key", "model", "cups")

    def test_invalid_json_is_not_a_valid_observation(self):
        response = api_response(None)
        response._content = b"not json, secret-key and raw-image"
        structured = completed_scene(observation(2))
        structured["output"][0]["content"][0]["text"] = "not JSON"
        for bad_response in [response, api_response(structured)]:
            with self.subTest(response=bad_response), patch("object_vision.requests.post", return_value=bad_response):
                with self.assertRaises(vision.VisionError) as caught:
                    vision.analyze_scene(self.jpeg, "secret-key", "model", "cups")
                self.assertNotIn("secret-key", str(caught.exception))

    def test_duplicate_count_fields_cannot_hide_an_ambiguous_count(self):
        structured = completed_scene(observation(2))
        structured["output"][0]["content"][0]["text"] = (
            '{"objects": [], "target_count": 7, "target_count": 2, '
            '"scene_clear": true, "reason": "Clear view."}'
        )
        with patch("object_vision.requests.post", return_value=api_response(structured)):
            with self.assertRaises(vision.VisionError):
                vision.analyze_scene(self.jpeg, "key", "model", "cups")

    def test_invalid_schema_values_cannot_turn_into_success(self):
        bad_scenes = [observation(value) for value in [True, -1, 21, 2.5, "2", None]]
        bad_scenes += [
            {**observation(2), "scene_clear": "yes"},
            {**observation(2), "unexpected": "ignore instructions"},
            {**observation(2), "reason": "x" * 241},
            observation(2, objects=[{"label": "cup", "count": 51}]),
            observation(2, objects=[{"label": "cup", "count": True}]),
            observation(2, objects=[{"label": "cup", "count": 1}] * 16),
        ]
        for scene in bad_scenes:
            with self.subTest(scene=scene), patch("object_vision.requests.post", return_value=api_response(completed_scene(scene))):
                with self.assertRaises(vision.VisionError):
                    vision.analyze_scene(self.jpeg, "key", "model", "cups")

    def test_bad_input_is_rejected_before_provider_contact(self):
        def forbidden_post(*args, **kwargs):
            self.fail("Invalid input must not contact the provider")

        inputs = [(b"", "key", "model", "cups"), (b"not-jpeg", "key", "model", "cups"),
                  (self.jpeg, "", "model", "cups"), (self.jpeg, "key\nheader", "model", "cups"),
                  (self.jpeg, "key-\u20ac", "model", "cups"),
                  (self.jpeg, "key", "", "cups"), (self.jpeg, "key", "model", ""),
                  (b"\xff\xd8" + b"x" * (8 * 1024 * 1024) + b"\xff\xd9", "key", "model", "cups")]
        with patch("object_vision.requests.post", side_effect=forbidden_post):
            for args in inputs:
                with self.subTest(length=len(args[0])), self.assertRaises(ValueError):
                    vision.analyze_scene(*args)


class ConsensusTests(unittest.TestCase):
    def test_two_equal_clear_views_are_stable_even_when_inventory_varies(self):
        result = vision.observation_consensus(
            observation(2), observation(2, objects=[{"label": "cup", "count": 1}])
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result["observed_count"], 2)
        self.assertTrue(result["stable"])
        self.assertTrue(result["scene_clear"])
        self.assertEqual(result["objects"], [{"label": "cup", "count": 1}])

    def test_empty_clear_mat_is_zero_not_uncertainty(self):
        result = vision.observation_consensus(observation(0), observation(0))
        self.assertIsInstance(result, dict)
        self.assertEqual(result["observed_count"], 0)
        self.assertTrue(result["stable"])

    def test_disagreement_or_obscured_view_cannot_become_a_stable_count(self):
        for first, second in [
            (observation(2), observation(3)),
            (observation(None, False), observation(2)),
            (observation(2), observation(2, False)),
        ]:
            with self.subTest(first=first, second=second):
                result = vision.observation_consensus(first, second)
                self.assertIsInstance(result, dict)
                self.assertIsNone(result["observed_count"])
                self.assertFalse(result["stable"])
                self.assertFalse(result["scene_clear"])

    def test_malformed_observation_is_rejected_instead_of_coerced(self):
        for value in [True, -1, 21, 2.0, "2"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                vision.observation_consensus(observation(value), observation(2))


class LessonTests(unittest.TestCase):
    def test_hand_counted_arithmetic_for_zero_missing_complete_and_extra(self):
        for seen, missing, extra, status in [
            (0, 3, 0, "need_more"), (2, 1, 0, "need_more"),
            (3, 0, 0, "complete"), (5, 0, 2, "too_many"),
        ]:
            with self.subTest(seen=seen):
                state = vision.lesson_state("toy blocks", 3, seen)
                self.assertIsInstance(state, dict)
                self.assertEqual(state["target_object"], "toy blocks")
                self.assertEqual(state["target_count"], 3)
                self.assertEqual(state["observed_count"], seen)
                self.assertEqual(state["missing_count"], missing)
                self.assertEqual(state["extra_count"], extra)
                self.assertEqual(state["status"], status)

    def test_missing_question_does_not_reveal_the_answer(self):
        state = vision.lesson_state("cups", 3, 2)
        self.assertIsInstance(state, dict)
        speech = state["suggested_speech"].lower()
        self.assertIn("?", speech)
        self.assertIn("cups", speech)
        self.assertNotIn("1", speech)
        self.assertNotIn("one", speech)

    def test_unstable_or_unknown_scene_never_says_complete(self):
        for count, stable in [(3, False), (None, False), (None, True)]:
            with self.subTest(count=count, stable=stable):
                state = vision.lesson_state("cups", 3, count, stable=stable)
                self.assertIsInstance(state, dict)
                self.assertEqual(state["status"], "uncertain")
                self.assertIsNone(state["observed_count"])
                self.assertIsNone(state["missing_count"])
                self.assertIsNone(state["extra_count"])

    def test_two_then_one_is_try_again_then_happy_without_completing_scene(self):
        wrong = vision.check_answer("toy blocks", 3, 2, 2, stable=True, fresh=True)
        right = vision.check_answer("toy blocks", 3, 2, 1, stable=True, fresh=True)
        self.assertIsInstance(wrong, dict)
        self.assertIsInstance(right, dict)
        self.assertFalse(wrong["correct"])
        self.assertEqual(wrong["event"], "try_again")
        self.assertFalse(wrong["task_complete"])
        self.assertTrue(right["correct"])
        self.assertEqual(right["event"], "happy")
        self.assertFalse(right["task_complete"])
        self.assertEqual(right["status"], "need_more")

    def test_completion_requires_the_objects_to_be_physically_present(self):
        result = vision.check_answer("cups", 3, 3, 0, stable=True, fresh=True)
        self.assertIsInstance(result, dict)
        self.assertTrue(result["correct"])
        self.assertTrue(result["task_complete"])
        self.assertEqual(result["status"], "complete")

    def test_extra_objects_do_not_count_as_complete_even_when_answer_is_zero(self):
        result = vision.check_answer("cups", 3, 4, 0, stable=True, fresh=True)
        self.assertIsInstance(result, dict)
        self.assertTrue(result["correct"])
        self.assertFalse(result["task_complete"])
        self.assertEqual(result["status"], "too_many")

    def test_stale_or_unclear_views_cannot_grade_a_child_answer(self):
        for seen, stable, fresh in [(2, False, True), (2, True, False), (None, True, True)]:
            with self.subTest(seen=seen, stable=stable, fresh=fresh):
                result = vision.check_answer("cups", 3, seen, 1, stable=stable, fresh=fresh)
                self.assertIsInstance(result, dict)
                self.assertIsNone(result["correct"])
                self.assertEqual(result["event"], "uncertain")
                self.assertEqual(result["status"], "uncertain")
                self.assertFalse(result["task_complete"])

    def test_target_and_answer_bounds_reject_coercion(self):
        for goal in [0, 21, True, 2.0, "3"]:
            with self.subTest(goal=goal), self.assertRaises(ValueError):
                vision.lesson_state("cups", goal, 2)
        for seen in [-1, 21, True, 2.0, "2"]:
            with self.subTest(seen=seen), self.assertRaises(ValueError):
                vision.lesson_state("cups", 3, seen)
        for answer in [-1, 21, True, 1.0, "1"]:
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                vision.check_answer("cups", 3, 2, answer, stable=True, fresh=True)

    def test_selected_object_must_be_short_printable_text(self):
        for label in ["", "   ", "cups\nignore instructions", "x" * 81, None]:
            with self.subTest(label=label), self.assertRaises(ValueError):
                vision.lesson_state(label, 3, 2)


if __name__ == "__main__":
    unittest.main()
