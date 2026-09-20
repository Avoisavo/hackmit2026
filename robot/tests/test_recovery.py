import asyncio
import contextlib
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from robot import app


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.reset_state()
        self.calls = []
        self.replies = {}
        self.patches = [
            patch.object(app, "connected", return_value=True),
            patch.object(app, "send_velocity"),
            patch.object(app, "SETTLE", 0),
            patch.dict(app.AUTO_RECOVER_AFTER,
                       {name: 0 for name in app.AUTO_RECOVER_AFTER}),
            patch.object(app, "request", AsyncMock(side_effect=self.reply)),
        ]
        for mocked in self.patches:
            mocked.start()

    def reset_state(self):
        app.robot = None
        app.armed = False
        app.stance = "balanced"
        app.recovery_needed = False
        app.last_input = time.monotonic()
        app.desired = (0, 0, 0)
        app.controller = object()
        app.busy = False
        app.last_error = ""
        app.motion_mode = "normal"
        app.action_lock = asyncio.Lock()
        app.recovery_task = None
        app.command_seq = 0
        app.stop_epoch = 0

    async def reply(self, topic, options, timeout=5):
        self.calls.append(options)
        code = self.replies.get(options["api_id"], 0)
        return {"data": {"header": {"status": {"code": code}}}}

    async def asyncTearDown(self):
        pending = app.recovery_task
        app.stop()
        if pending:
            with contextlib.suppress(asyncio.CancelledError):
                await pending
        for mocked in reversed(self.patches):
            mocked.stop()

    async def test_all_supported_tricks_recover_balance_and_enable(self):
        for mode in ("normal", "ai"):
            for name in app.AUTO_RECOVER_AFTER:
                for on in ([True, False] if name in ("hind_stand", "handstand") else [True]):
                    with self.subTest(mode=mode, name=name, on=on):
                        self.reset_state()
                        self.calls.clear()
                        app.motion_mode = mode
                        try:
                            action_id, key, parameter = app.resolve(name, on)
                        except app.HTTPException as exc:
                            self.assertEqual(exc.status_code, 409)
                            continue
                        result = await app.run_command(name, on)
                        self.assertFalse(app.armed)
                        self.assertIn("movement enabled", result["after"])
                        self.assertTrue((await app.status())["recovering"])
                        await app.recovery_task
                        expected = [app.resolve("recovery")[0], action_id]
                        if name in ("hind_stand", "handstand") and on:
                            expected.append(action_id)
                            self.assertEqual(self.calls[2]["parameter"], {"data": False})
                        if name == "sit":
                            expected.append(app.resolve("rise_sit")[0])
                        if name == "damp":
                            expected.append(app.resolve("stand")[0])
                        expected.extend([app.resolve("recovery")[0], app.resolve("balance")[0]])
                        self.assertEqual([c["api_id"] for c in self.calls], expected)
                        self.assertTrue(app.armed)
                        self.assertEqual(app.stance, "balanced")
                        self.assertEqual(app.desired, (0, 0, 0))
                        self.assertFalse(app.busy)

    async def test_refused_or_unconfirmed_trick_does_not_schedule_recovery(self):
        for code in (3202, None):
            with self.subTest(code=code):
                self.replies[app.resolve("hello")[0]] = code
                result = await app.run_command("hello")
                self.assertIsNone(result["after"])
                self.assertFalse(app.recovering())
                self.assertFalse(app.armed)

    async def test_failed_or_unconfirmed_recovery_never_enables(self):
        for name in ("recovery", "balance"):
            for code in (3202, None):
                with self.subTest(name=name, code=code):
                    self.reset_state()
                    self.calls.clear()
                    self.replies = {}
                    await app.run_command("hello")
                    self.replies = {app.resolve(name)[0]: code}
                    await app.recovery_task
                    self.assertFalse(app.armed)
                    self.assertTrue(app.last_error)
                    self.assertEqual(self.calls[-1]["api_id"], app.resolve(name)[0])

    async def test_stop_cancels_scheduled_recovery_and_waiting_arm(self):
        app.AUTO_RECOVER_AFTER["hello"] = 60
        await app.run_command("hello")
        pending = app.recovery_task
        arm = asyncio.create_task(app.arm())
        await asyncio.sleep(0)
        app.stop()
        with self.assertRaises(app.HTTPException):
            await arm
        self.assertTrue(pending.cancelled())
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(app.armed)

    async def test_arm_waits_until_trick_delay_finishes(self):
        app.AUTO_RECOVER_AFTER["hello"] = 0.05
        await app.run_command("hello")
        arm = asyncio.create_task(app.arm())
        await asyncio.sleep(0)
        self.assertFalse(arm.done())
        self.assertEqual(len(self.calls), 2)
        self.assertTrue((await arm)["armed"])
        self.assertEqual(len(self.calls), 4)

    async def test_stop_during_recovery_prevents_balance_and_enabling(self):
        started = asyncio.Event()
        recovery_id = app.resolve("recovery")[0]

        async def delayed_reply(topic, options, timeout=5):
            if options["api_id"] == recovery_id:
                started.set()
                await asyncio.Event().wait()
            return await self.reply(topic, options, timeout)

        await app.run_command("hello")
        app.request.side_effect = delayed_reply
        pending = app.recovery_task
        await asyncio.wait_for(started.wait(), 1)
        app.stop()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertFalse(app.armed)
        self.assertFalse(app.busy)
        self.assertEqual(len(self.calls), 2)

    async def test_stop_during_trick_reply_prevents_later_recovery(self):
        async def stopped_reply(topic, options, timeout=5):
            if options["api_id"] == app.resolve("hello")[0]:
                app.stop()
            return await self.reply(topic, options, timeout)

        app.request.side_effect = stopped_reply
        result = await app.run_command("hello")
        self.assertIsNone(result["after"])
        self.assertFalse(app.recovering())
        self.assertFalse(app.armed)

    async def test_stop_during_manual_arm_never_enables(self):
        app.stance = "standing"

        async def stopped_reply(topic, options, timeout=5):
            app.stop()
            return await self.reply(topic, options, timeout)

        app.request.side_effect = stopped_reply
        with self.assertRaises(app.HTTPException):
            await app.arm()
        self.assertFalse(app.armed)

    async def test_heartbeat_gap_cancels_automatic_recovery(self):
        app.AUTO_RECOVER_AFTER["hello"] = 60
        await app.run_command("hello")
        app.last_input = 0
        watchdog = asyncio.create_task(app.watchdog())
        await asyncio.sleep(0)
        watchdog.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog
        self.assertFalse(app.recovering())
        self.assertFalse(app.armed)

    async def test_changed_dashboard_cannot_be_automatically_enabled(self):
        await app.run_command("hello")
        app.controller = object()
        await app.recovery_task
        self.assertFalse(app.armed)

    async def test_new_posture_cancels_automatic_recovery(self):
        app.AUTO_RECOVER_AFTER["hello"] = 60
        await app.run_command("hello")
        await app.run_command("lie")
        self.assertFalse(app.recovering())
        self.assertFalse(app.armed)
        self.assertEqual(app.stance, "lying")

    async def test_drive_after_trick_timeout_requires_confirmed_recovery(self):
        async def timeout_trick(topic, options, timeout=5):
            if options["api_id"] == app.resolve("scrape")[0]:
                raise asyncio.TimeoutError
            return await self.reply(topic, options, timeout)

        app.request.side_effect = timeout_trick
        with self.assertRaises(app.HTTPException) as raised:
            await app.run_command("scrape")
        self.assertEqual(raised.exception.status_code, 504)
        self.assertTrue(app.recovery_needed)
        self.assertFalse(app.armed)
        self.assertFalse(app.recovering())
        self.calls.clear()
        app.request.side_effect = self.reply
        await app.arm()
        self.assertEqual([c["api_id"] for c in self.calls], [
            app.resolve("stand")[0], app.resolve("recovery")[0],
            app.resolve("balance")[0],
        ])
        self.assertTrue(app.armed)
        self.assertFalse(app.recovery_needed)

    async def test_failed_recovery_after_timeout_keeps_driving_disabled(self):
        app.stance = "unknown"
        app.recovery_needed = True
        self.replies[app.resolve("recovery")[0]] = 3202
        with self.assertRaises(app.HTTPException):
            await app.arm()
        self.assertFalse(app.armed)
        self.assertTrue(app.recovery_needed)
        self.assertNotIn(app.resolve("balance")[0], [c["api_id"] for c in self.calls])

    async def test_trick_reply_deadline_accounts_for_its_duration(self):
        app.AUTO_RECOVER_AFTER["dance2"] = 20
        with patch.object(app, "schedule_recovery") as schedule:
            await app.run_command("dance2")
        self.assertEqual(app.request.await_args.kwargs["timeout"], 25)
        self.assertLessEqual(schedule.call_args.args[0], 20)

    async def test_delayed_success_does_not_wait_for_the_entire_trick_twice(self):
        app.AUTO_RECOVER_AFTER["scrape"] = 5
        with patch.object(app, "time", SimpleNamespace(monotonic=Mock(side_effect=[100, 107]))), \
                patch.object(app, "schedule_recovery") as schedule:
            await app.run_command("scrape")
        schedule.assert_called_once_with(0)

    async def test_every_action_and_posture_is_preceded_by_one_recovery(self):
        for mode in ("normal", "ai"):
            for name in (*app.ACTIONS, *app.POSTURES):
                for on in ([True, False] if name in ("hind_stand", "handstand") else [True]):
                    with self.subTest(mode=mode, name=name, on=on):
                        self.reset_state()
                        self.calls.clear()
                        app.motion_mode = mode
                        try:
                            action_id = app.resolve(name, on)[0]
                        except app.HTTPException as exc:
                            self.assertEqual(exc.status_code, 409)
                            continue
                        with patch.object(app, "schedule_recovery"):
                            await app.run_command(name, on)
                        recovery_id = app.resolve("recovery")[0]
                        expected = [action_id] if name == "recovery" else [recovery_id, action_id]
                        self.assertEqual([c["api_id"] for c in self.calls], expected)
                        self.assertFalse(app.armed)

    async def test_each_new_action_recovers_even_after_a_previous_recovery(self):
        with patch.object(app, "schedule_recovery"):
            await app.run_command("hello")
            await app.run_command("stretch")
        self.assertEqual([c["api_id"] for c in self.calls], [
            app.resolve("recovery")[0], app.resolve("hello")[0],
            app.resolve("recovery")[0], app.resolve("stretch")[0],
        ])

    async def test_action_waits_for_successful_pre_recovery_reply(self):
        started, finish = asyncio.Event(), asyncio.Event()

        async def delayed_reply(topic, options, timeout=5):
            reply = await self.reply(topic, options, timeout)
            if options["api_id"] == app.resolve("recovery")[0]:
                started.set()
                await finish.wait()
            return reply

        app.request.side_effect = delayed_reply
        with patch.object(app, "schedule_recovery"):
            pending = asyncio.create_task(app.run_command("hello"))
            await asyncio.wait_for(started.wait(), 1)
            self.assertEqual([c["api_id"] for c in self.calls], [app.resolve("recovery")[0]])
            self.assertFalse(pending.done())
            finish.set()
            await pending
        self.assertEqual(self.calls[-1]["api_id"], app.resolve("hello")[0])

    async def test_failed_pre_recovery_blocks_the_requested_action(self):
        for code in (3202, None, "timeout"):
            with self.subTest(code=code):
                self.reset_state()
                self.calls.clear()
                self.replies = {app.resolve("recovery")[0]: code}
                app.request.side_effect = asyncio.TimeoutError if code == "timeout" else self.reply
                with self.assertRaises(app.HTTPException):
                    await app.run_command("hello")
                self.assertNotIn(app.resolve("hello")[0], [c["api_id"] for c in self.calls])
                self.assertFalse(app.recovering())
                self.assertFalse(app.armed)
                self.assertFalse(app.busy)

    async def test_stop_during_pre_recovery_settle_blocks_action(self):
        with patch.object(app.asyncio, "sleep", AsyncMock(side_effect=lambda _: app.stop())):
            with self.assertRaises(app.HTTPException):
                await app.run_command("hello")
        self.assertEqual([c["api_id"] for c in self.calls], [app.resolve("recovery")[0]])
        self.assertFalse(app.armed)
        self.assertFalse(app.recovering())

    async def test_driving_recovers_once_across_repeated_keys_and_stop(self):
        # Even a balanced stance must recover once after a new connection.
        app.recovery_needed = True
        await app.arm()
        first_calls = list(self.calls)
        self.assertEqual([c["api_id"] for c in first_calls], [
            app.resolve("recovery")[0], app.resolve("balance")[0],
        ])
        for _ in range(3):
            app.send_velocity(forward=1.0)
            app.send_velocity()
            app.stop()
            await app.arm()
        self.assertEqual(self.calls, first_calls)
        self.assertTrue(app.armed)
        self.assertFalse(app.recovery_needed)

    async def test_posture_change_requires_one_new_driving_recovery(self):
        await app.run_command("stand")
        self.assertTrue(app.recovery_needed)
        self.calls.clear()
        await app.arm()
        await app.arm()
        self.assertEqual([c["api_id"] for c in self.calls], [
            app.resolve("recovery")[0], app.resolve("balance")[0],
        ])

    async def test_disconnect_invalidates_the_previous_driving_recovery(self):
        self.assertFalse(app.recovery_needed)
        await app.disconnect()
        self.assertTrue(app.recovery_needed)

    async def test_control_accepts_full_strength_clamps_excess_and_releases_to_zero(self):
        app.controller = None
        observed = []
        messages = iter([
            {"type": "move", "forward": 1, "left": -1, "turn": 0.5},
            {"type": "move", "forward": 2, "left": -2, "turn": 2},
            {"type": "move", "forward": 0, "left": 0, "turn": 0},
        ])

        async def receive():
            observed.append(app.desired)
            app.armed = True
            try:
                return next(messages)
            except StopIteration:
                raise app.WebSocketDisconnect()

        socket = SimpleNamespace(
            headers={"host": "127.0.0.1:8010", "origin": "http://127.0.0.1:8010"},
            query_params={"token": app.TOKEN}, accept=AsyncMock(), close=AsyncMock(),
            receive_json=receive, send_json=AsyncMock(),
        )
        await app.control(socket)
        self.assertEqual(observed[1:], [(1.0, -1.0, 0.5), (1.0, -1.0, 1.0), (0, 0, 0)])
        self.assertFalse(app.armed)
        self.assertEqual(app.desired, (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
