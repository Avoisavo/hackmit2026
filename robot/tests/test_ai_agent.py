"""Tool validation, camera freshness and cancellation without OpenAI or hardware."""
import asyncio
import json
import threading
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
import requests
from fastapi import FastAPI

from robot.ai_agent import CameraAgent, AgentError, TOOLS, request_decision, validate_call

JPEG = b"\xff\xd8test-camera\xff\xd9"


def decision(name="finish", **kwargs):
    return {"name": name, "arguments": {**kwargs, "reason": "Visible evidence"}, "call_id": "call_123"}


def provider_body(choice=None):
    choice = choice or decision()
    return {"status": "completed", "output": [{
        "type": "function_call", "status": "completed", **choice,
        "arguments": json.dumps(choice["arguments"]),
    }]}


class ToolTests(unittest.TestCase):
    def call(self, body=None, status=200):
        response = Mock(status_code=status)
        response.json.return_value = provider_body() if body is None else body
        with patch("robot.ai_agent.requests.post", return_value=response) as post:
            result = request_decision("secret-test-key", "gpt-4.1-mini", JPEG,
                                      "Wave once", {}, 6, [], [])
            return result, post.call_args

    def test_provider_uses_images_strict_tools_and_single_call_without_storing_response(self):
        result, call = self.call()
        self.assertEqual(result["name"], "finish")
        payload = call.kwargs["json"]
        self.assertFalse(payload["store"])
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertEqual(payload["tool_choice"], "required")
        self.assertEqual(call.args[0], "https://api.openai.com/v1/responses")
        self.assertFalse(call.kwargs["allow_redirects"])
        self.assertTrue(payload["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("secret-test-key", json.dumps(payload))
        for tool in TOOLS:
            self.assertTrue(tool["strict"])
            self.assertFalse(tool["parameters"]["additionalProperties"])
            self.assertEqual(set(tool["parameters"]["required"]), set(tool["parameters"]["properties"]))

    def test_invalid_tool_calls_never_pass_validation(self):
        valid = {"direction": "forward", "seconds": 0.3, "speed": 0.15, "reason": "Open floor"}
        bad = [("move_robot", {**valid, field: value}) for field, values in {
            "direction": ["backward", "jump", "forward; rm"],
            "seconds": [0, -1, 1.1, float("nan"), float("inf"), True, "1"],
            "speed": [0, 0.31, False], "reason": [None, "", "x" * 241, "line\nbreak"],
        }.items() for value in values]
        bad += [("move_robot", {**valid, "extra": "bad"}), ("move_robot", {}),
                ("connect", {"reason": "No"}), ([], {}), ("finish", []),
                ("perform_trick", {"action": "back_flip", "reason": "No"})]
        for name, args in bad:
            with self.subTest(name=name, args=args), self.assertRaises(AgentError):
                validate_call(name, args)
        validate_call("move_robot", valid)

    def test_incomplete_multiple_duplicate_and_malformed_decisions_are_rejected(self):
        good = provider_body()
        call = good["output"][0]
        bodies = [{"status": "incomplete", "output": [call]},
                  {"status": "completed", "output": [call, {"type": "message", "status": "completed",
                      "content": [{"type": "refusal", "refusal": "Cannot act"}]}]},
                  {"status": "completed", "output": [call, call]},
                  {"status": "completed", "output": []},
                  {"status": "completed", "output": [{**call, "status": "in_progress"}]},
                  {"status": "completed", "output": [{**call, "arguments": '{"reason":"one","reason":"two"}'}]},
                  {"status": "completed", "output": [{**call, "arguments": "not JSON"}]},
                  {"status": "completed", "output": [{**call, "name": "back_flip"}]}]
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(AgentError):
                self.call(body)

    def test_provider_errors_do_not_echo_secrets_or_raw_response(self):
        for status in (301, 401, 403, 429, 500):
            with self.subTest(status=status), self.assertRaises(AgentError) as caught:
                self.call({"error": "secret-test-key"}, status)
            self.assertNotIn("secret-test-key", str(caught.exception))
        for exc in (requests.Timeout("secret-test-key"), requests.ConnectionError("secret-test-key")):
            with patch("robot.ai_agent.requests.post", side_effect=exc), self.assertRaises(AgentError) as caught:
                request_decision("secret-test-key", "model", JPEG, "goal", {}, 1, [], [])
            self.assertNotIn("secret-test-key", str(caught.exception))

    def test_bad_images_are_rejected_before_network(self):
        with patch("robot.ai_agent.requests.post") as post:
            for jpeg in (b"", b"not-jpeg", "image", b"\xff\xd8" + b"x" * (8 * 1024 * 1024) + b"\xff\xd9"):
                with self.assertRaises(AgentError):
                    request_decision("key", "model", jpeg, "goal", {}, 1, [], [])
            post.assert_not_called()


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.offset, self.age, self.session = 0, 0, 1
        self.jpeg = JPEG
        self.key = "sk-test-do-not-echo"
        self.service = CameraAgent(
            get_key=lambda: self.key, set_key=AsyncMock(),
            get_frame=lambda: (self.jpeg, self.clock() - self.age, self.session),
            acquire=Mock(return_value="owner"), check_context=Mock(), robot_state=lambda: {"stance": "balanced"},
            execute=AsyncMock(return_value={"stopped": True}), finish=Mock(), clock=self.clock,
        )
        self.service.decide = Mock(return_value=decision())
        app = FastAPI()
        app.include_router(self.service.router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost")

    def clock(self):
        return time.monotonic() + self.offset

    async def asyncTearDown(self):
        await self.service.close()
        await self.client.aclose()

    async def start(self, **overrides):
        return await self.client.post("/api/ai/start", json={
            "goal": "Wave once when you see a person", "run_id": "run_test_123456789",
            "control_id": "owner-id", "control_epoch": 42, **overrides,
        })

    async def done(self):
        await asyncio.wait_for(asyncio.shield(self.service._task), 2)

    async def test_goal_camera_tool_result_then_new_frame_and_finish(self):
        self.service.decide.side_effect = [decision("wait", seconds=0.2), decision()]
        async def execute(*args):
            args[3]()
            self.jpeg = b"\xff\xd8second-frame\xff\xd9"
            return {"stopped": True}
        self.service.execute.side_effect = execute
        self.assertEqual((await self.start()).status_code, 200)
        await self.done()
        calls = self.service.decide.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[2], JPEG)
        self.assertEqual(calls[1].args[2], self.jpeg)
        self.assertEqual(calls[1].args[6][1]["type"], "function_call_output")
        self.assertEqual(calls[1].args[6][1]["call_id"], "call_123")
        self.assertEqual(self.service.phase, "complete")
        self.assertFalse(self.service.running)
        self.service.finish.assert_called_once_with("owner")
        self.service.acquire.assert_called_once_with("owner-id", 42)
        self.assertNotIn(self.key, json.dumps(self.service.status()))

    async def test_start_is_idempotent_and_bounded_to_six_decisions(self):
        self.service.decide.return_value = decision("wait", seconds=0.2)
        await self.start()
        await self.done()
        self.assertEqual(self.service.decide.call_count, 6)
        self.assertEqual((await self.start()).status_code, 200)
        self.assertEqual(self.service.decide.call_count, 6)
        self.assertEqual(len(self.service.steps), 6)

    async def test_missing_key_stale_camera_and_invalid_goal_do_not_call_provider(self):
        self.key = ""
        self.assertEqual((await self.start()).status_code, 409)
        self.key = "sk-test-key"
        self.age = 3
        self.assertEqual((await self.start()).status_code, 409)
        self.age = 0
        for value in ("", "x" * 501, 42, "newline\nhere"):
            self.assertEqual((await self.start(goal=value)).status_code, 400)
        self.service.decide.assert_not_called()

    async def test_frozen_camera_never_yields_a_second_decision(self):
        at = self.clock()
        self.service.CAMERA_MAX_AGE = 0.01
        self.service.get_frame = lambda: (JPEG, at, 1)
        self.service.decide.return_value = decision("wait", seconds=0.2)
        await self.start()
        await self.done()
        self.assertEqual(self.service.decide.call_count, 1)
        self.assertEqual(self.service.phase, "error")

    async def test_slow_decision_does_not_execute_despite_live_camera(self):
        def slow(*args):
            self.offset += 9
            return decision("move_robot", direction="forward", seconds=0.3, speed=0.15)
        self.service.decide.side_effect = slow
        await self.start()
        await self.done()
        self.service.execute.assert_not_awaited()
        self.assertIn("too old", self.service.message)

    async def test_stop_during_provider_discards_late_result_and_preserves_newer_manual_control(self):
        entered = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()
        def blocked(*args):
            loop.call_soon_threadsafe(entered.set)
            release.wait(2)
            return decision("move_robot", direction="forward", seconds=0.3, speed=0.15)
        self.service.decide.side_effect = blocked
        try:
            await self.start()
            await asyncio.wait_for(entered.wait(), 1)
            self.service.cancel("STOP pressed")
            self.assertTrue(self.service.busy)
            self.assertFalse(self.service.running)
            self.assertEqual((await self.start(run_id="run_test_987654321")).status_code, 409)
            key_response = await self.client.post("/api/ai/key", json={"api_key": "sk-other-key"})
            self.assertEqual(key_response.status_code, 409)
        finally:
            release.set()
        await self.done()
        self.service.execute.assert_not_awaited()
        self.service.finish.assert_not_called()
        self.assertEqual(self.service.message, "STOP pressed")
        self.assertFalse(self.service.busy)

    async def test_connection_or_camera_change_while_thinking_blocks_action(self):
        for change in ("connection", "camera"):
            with self.subTest(change=change):
                self.age = 0
                self.service.check_context.side_effect = None
                def decide(*args):
                    if change == "connection":
                        self.service.check_context.side_effect = AgentError("Connection changed")
                    else:
                        self.age = 3
                    return decision()
                self.service.decide.side_effect = decide
                await self.start(run_id="run_test_123456789_" + change)
                await self.done()
                self.assertEqual(self.service.phase, "error")
        self.service.execute.assert_not_awaited()

    async def test_refused_action_ends_sequence(self):
        self.service.execute.side_effect = AgentError("Robot refused gesture")
        await self.start()
        await self.done()
        self.assertEqual(self.service.decide.call_count, 1)
        self.assertEqual(self.service.phase, "error")
        self.service.finish.assert_called_once()

    async def test_decision_and_run_deadlines_are_rechecked_after_preparation(self):
        for seconds in (9, 121):
            async def execute(name, args, context, check):
                self.offset += seconds
                check(decision=True)
                self.fail("Expired decision executed")
            self.service.execute.side_effect = execute
            await self.start(run_id=f"run_deadline_{seconds:016d}")
            await self.done()
            self.assertEqual(self.service.phase, "error")

    async def test_oversized_or_duplicate_request_is_rejected(self):
        for body in ('{"goal":"a","goal":"b"}', '{"goal":"' + 'x' * 5000 + '"}'):
            response = await self.client.post("/api/ai/start", content=body)
            self.assertEqual(response.status_code, 400)
        self.service.acquire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
