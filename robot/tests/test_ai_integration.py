"""Exercise the actuator boundary with a fake robot; never send real motion."""
import asyncio
import contextlib
import json
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from robot import app
from robot.ai_agent import AgentError


class RobotAgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        state = {
            "robot": object(), "controller": object(), "controller_id": "test-socket-owner",
            "armed": False, "desired": (0, 0, 0), "busy": False,
            "last_input": time.monotonic(), "stop_epoch": 42,
            "action_lock": asyncio.Lock(), "recovery_task": None,
            "stance": "balanced", "recovery_needed": False, "command_seq": 0,
            "latest_jpeg": b"\xff\xd8test-frame\xff\xd9", "frame_at": time.monotonic(),
            "camera_session": 1, "motion_mode": "normal", "last_error": "",
            "connected": Mock(return_value=True), "send_velocity": Mock(), "SETTLE": 0,
            "request": AsyncMock(return_value={"data": {"header": {"status": {"code": 0}}}}),
        }
        for name, value in state.items():
            mocked = patch.object(app, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        for name, value in {"running": False, "_task": None, "_epoch": 0, "steps": [],
                            "phase": "idle", "message": "", "run_id": "", "goal": "",
                            "_seen_runs": [], "decide": Mock(return_value={
                                "name": "finish", "arguments": {"reason": "Done"}, "call_id": "call_done",
                            })}.items():
            mocked = patch.object(app.ai, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        key = patch.object(app.vision, "_api_key", "sk-integration-key")
        key.start()
        self.addCleanup(key.stop)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),
            base_url="http://127.0.0.1", headers={"X-Control-Token": app.TOKEN})

    async def asyncTearDown(self):
        app.stop()
        await app.ai.close()
        await self.client.aclose()

    def context(self):
        return app.controller, app.robot, app.camera_session

    async def start(self, **changes):
        return await self.client.post("/api/ai/start", json={
            "goal": "Wave once", "run_id": "integration_run_12345",
            "control_id": app.controller_id, "control_epoch": app.stop_epoch, **changes,
        })

    async def test_actual_routes_are_authenticated_and_use_shared_server_key(self):
        for path in ("/api/ai/start", "/api/ai/key", "/api/ai/status"):
            response = await self.client.request("GET" if path.endswith("status") else "POST", path,
                headers={"X-Control-Token": "wrong"}, json={})
            self.assertEqual(response.status_code, 403)
        key = "sk-new-test-key-not-real"
        response = await self.client.post("/api/ai/key", json={"api_key": key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(app.vision._api_key, key)
        self.assertNotIn(key, response.text)
        self.assertTrue(response.json()["configured"])
        status = await self.client.get("/api/status")
        self.assertIn("ai", status.json())
        self.assertNotIn("control_id", status.json())
        self.assertNotIn(key, status.text)
        app.request.assert_not_awaited()

    async def test_stop_generation_and_socket_ownership_block_delayed_or_foreign_starts(self):
        epoch = app.stop_epoch
        app.stop("STOP")
        self.assertEqual((await self.start(control_epoch=epoch)).status_code, 409)
        for control_id in ("second-tab", "é" * 17, None, 123):
            self.assertEqual((await self.start(control_id=control_id)).status_code, 409)
        app.ai.decide.assert_not_called()
        app.request.assert_not_awaited()

    async def test_armed_busy_recovering_or_missing_heartbeat_blocks_start(self):
        for name, value in (("armed", True), ("busy", True), ("last_input", 0), ("controller", None)):
            with self.subTest(name=name), patch.object(app, name, value):
                self.assertEqual((await self.start()).status_code, 409)
        with patch.object(app, "recovering", return_value=True):
            self.assertEqual((await self.start()).status_code, 409)
        app.ai.decide.assert_not_called()

    async def test_start_and_finish_never_arm_or_send_sport_commands(self):
        self.assertEqual((await self.start()).status_code, 200)
        await app.ai._task
        self.assertEqual(app.ai.phase, "complete")
        self.assertFalse(app.armed)
        self.assertEqual(app.desired, (0, 0, 0))
        app.request.assert_not_awaited()

    async def test_timed_move_prepares_then_drives_at_bounded_speed_and_disarms(self):
        app.ai.running = True
        observed = []
        async def wait(seconds, check):
            observed.append((seconds, app.armed, app.desired, app.busy))
            check()
        with patch.object(app, "ai_wait", side_effect=wait), patch.object(app, "prepare_stance", AsyncMock()) as prepare:
            result = await app.execute_ai("move_robot", {"direction": "turn_left", "seconds": 0.3,
                "speed": 0.15, "reason": "Open floor"}, self.context(), Mock())
        prepare.assert_awaited_once()
        self.assertEqual(observed, [(0.3, True, (0, 0, 0.15), True)])
        self.assertTrue(result["stopped"])
        self.assertFalse(app.armed)
        self.assertFalse(app.busy)
        self.assertEqual(app.desired, (0, 0, 0))
        self.assertTrue(app.ai.running)  # Internal preparation did not cancel its own run.

    async def test_invalid_motion_never_reaches_actuators(self):
        with self.assertRaises(AgentError):
            await app.execute_ai("move_robot", {"direction": "forward", "seconds": 30,
                "speed": 1, "reason": "Go"}, self.context(), Mock())
        app.send_velocity.assert_not_called()
        app.request.assert_not_awaited()

    async def test_timed_step_uses_real_watchdog_then_sends_zero_without_faking_heartbeat(self):
        app.ai.running = True
        heartbeat = app.last_input
        watch = asyncio.create_task(app.watchdog())
        started = time.monotonic()
        try:
            await app.execute_ai("move_robot", {"direction": "forward", "seconds": 0.1,
                "speed": 0.15, "reason": "Open floor"}, self.context(), Mock())
            self.assertGreaterEqual(time.monotonic() - started, 0.095)
            self.assertIn((0.15, 0, 0), [call.args for call in app.send_velocity.call_args_list])
            self.assertEqual(app.send_velocity.call_args.args, ())
            self.assertEqual(app.last_input, heartbeat)
            self.assertFalse(app.armed)
        finally:
            watch.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch

    async def test_stop_endpoint_cancels_active_ai_step_and_prevents_another_decision(self):
        moving = asyncio.Event()
        app.ai.decide.return_value = {
            "name": "move_robot", "arguments": {"direction": "forward", "seconds": 1,
                "speed": 0.15, "reason": "Open floor"}, "call_id": "call_move",
        }
        def velocity(*args):
            if args and args[0]:
                moving.set()
        app.send_velocity.side_effect = velocity
        watch = asyncio.create_task(app.watchdog())
        try:
            self.assertEqual((await self.start()).status_code, 200)
            await asyncio.wait_for(moving.wait(), 1)
            response = await self.client.post("/api/stop")
            self.assertEqual(response.status_code, 200)
            await asyncio.wait_for(app.ai._task, 1)
            self.assertFalse(app.armed)
            self.assertFalse(app.ai.running)
            self.assertEqual(app.desired, (0, 0, 0))
            self.assertEqual(app.ai.decide.call_count, 1)
            self.assertEqual(app.ai.phase, "stopped")
        finally:
            watch.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch

    async def test_stop_during_preparation_cannot_enable_late_motion(self):
        app.ai.running = True
        async def prepare(epoch):
            app.stop("STOP")
        with patch.object(app, "prepare_stance", side_effect=prepare), self.assertRaises(app.HTTPException):
            await app.execute_ai("move_robot", {"direction": "forward", "seconds": 0.1,
                "speed": 0.15, "reason": "Open floor"}, self.context(), Mock())
        self.assertFalse(app.armed)
        self.assertFalse(app.ai.running)
        self.assertEqual(app.desired, (0, 0, 0))

    async def test_camera_error_during_move_immediately_disarms(self):
        app.ai.running = True
        with patch.object(app, "ai_wait", AsyncMock(side_effect=AgentError("Stale camera"))), self.assertRaises(AgentError):
            await app.execute_ai("move_robot", {"direction": "forward", "seconds": 1,
                "speed": 0.3, "reason": "Open floor"}, self.context(), Mock())
        self.assertFalse(app.armed)
        self.assertEqual(app.desired, (0, 0, 0))

    async def test_ai_gesture_waits_without_scheduling_automatic_rearm(self):
        app.ai.running = True
        with patch.object(app, "ai_wait", AsyncMock()) as wait, patch.object(app, "schedule_recovery") as schedule:
            result = await app.execute_ai("perform_trick", {"action": "hello", "reason": "A visible person"}, self.context(), Mock())
        self.assertTrue(result["accepted"])
        self.assertEqual([call.args[1]["api_id"] for call in app.request.await_args_list],
                         [app.resolve("recovery")[0], app.resolve("hello")[0]])
        wait.assert_awaited_once()
        self.assertGreater(wait.await_args.args[0], 0)
        schedule.assert_not_called()
        self.assertFalse(app.armed)
        self.assertTrue(app.ai.running)

    async def test_stale_decision_after_recovery_never_sends_final_gesture(self):
        check = Mock(side_effect=[None, AgentError("Decision expired")])
        with self.assertRaises(AgentError):
            await app.execute_ai("perform_trick", {"action": "hello", "reason": "A visible person"}, self.context(), check)
        self.assertEqual(app.request.await_count, 1)
        self.assertEqual(app.request.await_args.args[1]["api_id"], app.resolve("recovery")[0])
        self.assertFalse(app.armed)

    async def test_context_change_invalidates_run(self):
        context = self.context()
        for name, value in (("controller", object()), ("robot", object()), ("camera_session", 2), ("last_input", 0)):
            with self.subTest(name=name), patch.object(app, name, value), self.assertRaises(AgentError):
                app.check_ai_context(context)

    async def test_watchdog_stops_ai_on_missed_heartbeat_or_stale_video_even_when_disarmed(self):
        for field in ("last_input", "frame_at"):
            app.ai.running = True
            with patch.object(app, field, 0):
                task = asyncio.create_task(app.watchdog())
                try:
                    await asyncio.sleep(0.001)
                    self.assertFalse(app.ai.running)
                    self.assertFalse(app.armed)
                finally:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    async def test_zero_browser_heartbeat_preserves_ai_velocity_but_manual_input_cancels(self):
        app.controller = None
        seen = []
        phase = 0
        async def receive():
            nonlocal phase
            phase += 1
            if phase == 1:
                app.ai.running, app.armed, app.busy = True, True, True
                app.desired = (0.15, 0, 0)
                return {"type": "move", "forward": 0}
            seen.append((app.desired, app.ai.running))
            if phase == 2:
                return {"type": "move", "forward": 1}
            raise app.WebSocketDisconnect()
        socket = Mock(headers={"host": "localhost", "origin": "http://localhost"},
                      query_params={"token": app.TOKEN}, accept=AsyncMock(), send_json=AsyncMock(),
                      receive_json=AsyncMock(side_effect=receive))
        await app.control(socket)
        self.assertEqual(seen, [((0.15, 0, 0), True), ((0, 0, 0), False)])
        self.assertFalse(app.armed)
        self.assertIsNone(app.controller)
        self.assertEqual(app.controller_id, "")


if __name__ == "__main__":
    unittest.main()
