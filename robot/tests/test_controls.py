"""Offline control contract tests; the robot transport never contacts hardware."""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as dashboard


def rpc_reply(code=0, data=""):
    return {"type": "msg", "topic": "rt/api/sport/response", "data": {
        "header": {"identity": {"id": 1, "api_id": 0}, "status": {"code": code}},
        "data": data,
    }}


class RobotTransport:
    def __init__(self):
        self.channel = SimpleNamespace(readyState="open")
        self.requests = []
        self.velocities = []
        self.replies = []

    async def publish_request_new(self, topic, options):
        self.requests.append((topic, options, dashboard.armed))
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return rpc_reply()

    def publish_without_callback(self, topic, data):
        self.velocities.append((topic, data))


class ControlSocket:
    headers = {"host": "localhost", "origin": "http://localhost"}

    def __init__(self, move):
        self.query_params = {"token": dashboard.TOKEN}
        self.move = move
        self.received = False
        self.applied = None

    async def accept(self):
        pass

    async def receive_json(self):
        if not self.received:
            self.received = True
            await dashboard.arm()
            return {"type": "move", **self.move}
        self.applied = dashboard.desired
        raise EOFError("Offline browser disconnected")


class ControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = RobotTransport()
        dashboard.robot = SimpleNamespace(
            pc=SimpleNamespace(connectionState="connected"),
            datachannel=SimpleNamespace(data_channel_opened=True, pub_sub=self.transport),
            video=SimpleNamespace(add_track_callback=Mock(), switchVideoChannel=Mock()),
            disconnect=AsyncMock(),
        )
        dashboard.action_lock = asyncio.Lock()
        dashboard.motion_mode = "mcf"
        dashboard.last_error = ""
        dashboard.busy = False
        dashboard.controller = None
        dashboard.stop()

    async def asyncTearDown(self):
        await dashboard.disconnect()

    async def test_forward_can_be_fast_while_sideways_and_turning_stay_bounded(self):
        socket = ControlSocket({"forward": 0.6, "left": 0.8, "turn": -0.9})
        await dashboard.control(socket)
        self.assertEqual(socket.applied, (0.6, 0.3, -0.3))
        self.assertFalse(dashboard.armed)
        self.assertEqual(dashboard.desired, (0, 0, 0))

    async def test_reverse_and_excess_forward_are_bounded_on_server(self):
        for move, expected in [
            ({"forward": 20, "left": -20, "turn": 20}, (0.6, -0.3, 0.3)),
            ({"forward": -20}, (-0.3, 0, 0)),
        ]:
            with self.subTest(move=move):
                socket = ControlSocket(move)
                await dashboard.control(socket)
                self.assertEqual(socket.applied, expected)

    async def test_nonfinite_motion_disarms_without_applying_input(self):
        for value in [float("nan"), float("inf"), -float("inf")]:
            with self.subTest(value=value):
                socket = ControlSocket({"forward": value})
                await dashboard.control(socket)
                self.assertFalse(dashboard.armed)
                self.assertEqual(dashboard.desired, (0, 0, 0))

    async def test_mcf_and_ai_balancing_actions_send_explicit_enter_or_exit(self):
        for mode in ["mcf", "ai"]:
            dashboard.motion_mode = mode
            for name, api_id, enabled in [
                ("handstand", 2044, True), ("exit_handstand", 2044, False),
                ("hind_stand", 2050, True), ("exit_hind_stand", 2050, False),
            ]:
                with self.subTest(mode=mode, action=name):
                    try:
                        await dashboard.action(name)
                    except dashboard.HTTPException as exc:
                        self.fail(f"Supported action {name} rejected: {exc.detail}")
                    self.assertEqual(self.transport.requests[-1], (
                        dashboard.RTC_TOPIC["SPORT_MOD"],
                        {"api_id": api_id, "parameter": {"data": enabled}}, False,
                    ))

    async def test_normal_handstand_preserves_legacy_parameterless_request(self):
        dashboard.motion_mode = "normal"
        await dashboard.action("handstand")
        self.assertEqual(self.transport.requests[-1][1], {"api_id": 1301})

    async def test_status_reports_mode_specific_unavailable_actions(self):
        state = await dashboard.status()
        self.assertIn("actions", state)
        self.assertTrue(state["actions"]["exit_handstand"]["available"])
        self.assertFalse(state["actions"]["right_flip"]["available"])
        self.assertTrue(state["actions"]["right_flip"]["reason"])
        dashboard.motion_mode = "normal"
        self.assertFalse((await dashboard.status())["actions"]["exit_handstand"]["available"])

    async def test_unknown_mode_cannot_send_guessed_trick_ids(self):
        dashboard.motion_mode = ""
        with self.assertRaises(dashboard.HTTPException) as raised:
            await dashboard.action("hello")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.transport.requests, [])

    async def test_explicit_not_implemented_is_cached_per_mode_until_disconnect(self):
        self.transport.replies.append(rpc_reply(3203))
        with self.assertRaises(dashboard.HTTPException) as raised:
            await dashboard.action("front_flip")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("does not implement", raised.exception.detail)
        self.assertFalse((await dashboard.status())["actions"]["front_flip"]["available"])
        with self.assertRaises(dashboard.HTTPException) as repeated:
            await dashboard.action("front_flip")
        self.assertEqual(repeated.exception.status_code, 409)
        self.assertEqual(len(self.transport.requests), 1)
        dashboard.motion_mode = "normal"
        self.assertTrue((await dashboard.status())["actions"]["front_flip"]["available"])
        previous_robot = dashboard.robot
        await dashboard.disconnect()
        dashboard.robot = previous_robot
        dashboard.motion_mode = "mcf"
        self.assertTrue((await dashboard.status())["actions"]["front_flip"]["available"])

    async def test_rejected_or_malformed_reply_is_not_reported_as_success(self):
        for reply in [
            rpc_reply(-1), {}, rpc_reply(None), rpc_reply("0"),
            rpc_reply(False), rpc_reply(3203.0),
        ]:
            with self.subTest(reply=reply):
                self.transport.replies.append(reply)
                with self.assertRaises(dashboard.HTTPException) as raised:
                    await dashboard.action("hello")
                self.assertEqual(raised.exception.status_code, 502)
                self.assertTrue(dashboard.last_error)
                self.assertTrue((await dashboard.status())["actions"]["hello"]["available"])
                self.assertFalse(dashboard.busy)

    async def test_timeout_keeps_outcome_unknown_without_retry_or_disabling_action(self):
        self.transport.replies.append(asyncio.TimeoutError())
        with self.assertRaises(dashboard.HTTPException) as raised:
            await dashboard.action("hello")
        self.assertEqual(raised.exception.status_code, 504)
        self.assertIn("Outcome unknown", raised.exception.detail)
        self.assertEqual(len(self.transport.requests), 1)
        state = await dashboard.status()
        self.assertIn("actions", state)
        self.assertTrue(state["actions"]["hello"]["available"])

    async def test_connection_enables_native_joystick_while_disarmed(self):
        self.transport.replies.extend([rpc_reply(), rpc_reply(data=json.dumps({"name": "mcf"}))])
        await dashboard.after_connect()
        self.assertEqual(self.transport.requests[0], (
            dashboard.RTC_TOPIC["SPORT_MOD"],
            {"api_id": 1027, "parameter": {"data": True}}, False,
        ))
        self.assertEqual(dashboard.motion_mode, "mcf")

    async def test_rejected_joystick_enable_fails_connection(self):
        self.transport.replies.append(rpc_reply(-1))
        with self.assertRaisesRegex(RuntimeError, "joystick"):
            await dashboard.after_connect()
        self.assertFalse(dashboard.armed)

    async def test_mcf_rejects_legacy_mode_switch_without_sending_command(self):
        for mode in ["normal", "ai"]:
            with self.subTest(mode=mode):
                with self.assertRaises(dashboard.HTTPException) as raised:
                    await dashboard.set_mode(mode)
                self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.transport.requests, [])


if __name__ == "__main__":
    unittest.main()
