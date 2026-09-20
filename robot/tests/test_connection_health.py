import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from unitree_webrtc_connect.msgs.heartbeat import WebRTCDataChannelHeartBeat

from robot import app
from robot.connection_health import ConnectionSupervisor, guard_heartbeat


class HeartbeatTests(unittest.TestCase):
    def test_sdk_schedules_next_tick_after_both_failed_and_successful_sends(self):
        scheduled = []
        loop = Mock()
        loop.call_later.side_effect = lambda seconds, callback: scheduled.append(callback) or Mock()
        publish = Mock(side_effect=[RuntimeError('temporary send error'), None])
        heartbeat = WebRTCDataChannelHeartBeat(
            SimpleNamespace(readyState='open'),
            SimpleNamespace(publish_without_callback=publish),
        )
        with patch('unitree_webrtc_connect.msgs.heartbeat.asyncio.get_event_loop', return_value=loop):
            guard_heartbeat(heartbeat)
            with self.assertLogs('robot.connection_health', level='WARNING'):
                scheduled.pop(0)()
            self.assertEqual(len(scheduled), 1)
            scheduled.pop(0)()
            self.assertEqual(len(scheduled), 1)
            self.assertEqual(publish.call_count, 2)

    def test_one_failed_send_does_not_end_heartbeats(self):
        original = Mock(side_effect=[RuntimeError("channel send failed"), None])
        heartbeat = SimpleNamespace(
            send_heartbeat=original, channel=SimpleNamespace(readyState="open"),
            start_heartbeat=Mock(), stop_heartbeat=Mock(),
        )
        guard_heartbeat(heartbeat)
        heartbeat.stop_heartbeat.assert_called_once()
        with self.assertLogs('robot.connection_health', level='WARNING'):
            heartbeat.send_heartbeat()
        self.assertEqual(heartbeat.start_heartbeat.call_count, 2)
        heartbeat.send_heartbeat()
        self.assertEqual(original.call_count, 2)

    def test_closed_peer_does_not_restart_a_failed_heartbeat(self):
        heartbeat = SimpleNamespace(
            send_heartbeat=Mock(side_effect=RuntimeError("closed")),
            channel=SimpleNamespace(readyState="closed"),
            start_heartbeat=Mock(), stop_heartbeat=Mock(),
        )
        guard_heartbeat(heartbeat)
        with self.assertLogs('robot.connection_health', level='WARNING'):
            heartbeat.send_heartbeat()
        self.assertEqual(heartbeat.start_heartbeat.call_count, 1)


class SupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.online = True
        self.busy = False
        self.lost = asyncio.Event()
        self.reconnected = asyncio.Event()

        async def reconnect():
            self.online = True
            self.reconnected.set()

        self.open_connection = AsyncMock(side_effect=reconnect)
        self.supervisor = ConnectionSupervisor(
            lambda: self.online, lambda: self.busy, self.open_connection, self.lost.set,
        )
        self.supervisor.POLL = 0.001
        self.supervisor.GRACE = 0.01
        self.supervisor.RETRY_DELAYS = (0, 0.001, 0.001)
        log = patch('robot.connection_health.logger')
        log.start()
        self.addCleanup(log.stop)

    async def asyncTearDown(self):
        await self.supervisor.stop()

    async def test_dropped_robot_link_is_reconnected_once(self):
        self.supervisor.start()
        self.online = False
        await asyncio.wait_for(self.reconnected.wait(), 1)
        self.assertTrue(self.lost.is_set())
        self.open_connection.assert_awaited_once()
        self.assertFalse(self.supervisor.reconnecting)

    async def test_transient_peer_state_recovers_without_replacing_connection(self):
        self.supervisor.start()
        self.online = False
        await asyncio.wait_for(self.lost.wait(), 1)
        self.online = True
        await asyncio.sleep(0.03)
        self.open_connection.assert_not_awaited()
        self.assertFalse(self.supervisor.reconnecting)

    async def test_retries_are_bounded_and_require_manual_connect_after_exhaustion(self):
        self.open_connection.side_effect = RuntimeError("offline")
        self.online = False
        self.supervisor.start()
        await asyncio.wait_for(self.supervisor.task, 1)
        self.assertEqual(self.open_connection.await_count, 3)
        self.assertIn('click Connect robot', self.supervisor.message)
        self.assertFalse(self.supervisor.reconnecting)

    async def test_reconnect_waits_for_an_inflight_command(self):
        self.online, self.busy = False, True
        self.supervisor.start()
        await asyncio.wait_for(self.lost.wait(), 1)
        await asyncio.sleep(0.03)
        self.open_connection.assert_not_awaited()
        self.busy = False
        await asyncio.wait_for(self.reconnected.wait(), 1)

    async def test_manual_disconnect_cancels_an_inflight_reconnect(self):
        entered, cancelled = asyncio.Event(), asyncio.Event()

        async def pending_connect():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.online = False
        self.open_connection.side_effect = pending_connect
        self.supervisor.start()
        await asyncio.wait_for(entered.wait(), 1)
        await self.supervisor.stop()
        self.assertTrue(cancelled.is_set())
        self.assertIsNone(self.supervisor.task)
        self.assertFalse(self.supervisor.reconnecting)
        self.open_connection.assert_awaited_once()


class TransportFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_endpoint_cancels_reconnect_and_leaves_no_partial_peer(self):
        entered = asyncio.Event()

        async def pending_connect():
            entered.set()
            await asyncio.Event().wait()

        connection = SimpleNamespace(connect=pending_connect, disconnect=AsyncMock())
        supervisor = ConnectionSupervisor(
            app.connected, lambda: app.action_lock.locked(), app.open_robot_connection, lambda: None,
        )
        supervisor.POLL = supervisor.GRACE = 0
        with patch.object(app, 'Go2Connection', return_value=connection), \
                patch.object(app, 'robot', None), patch.object(app, 'action_lock', asyncio.Lock()), \
                patch.object(app, 'connection_watch', supervisor), patch('robot.connection_health.logger'):
            supervisor.start()
            await asyncio.wait_for(entered.wait(), 1)
            result = await app.disconnect_api()
            self.assertEqual(result, {'connected': False})
            connection.disconnect.assert_awaited_once()
            self.assertIsNone(supervisor.task)
            self.assertIsNone(app.robot)
            self.assertFalse(app.armed)
            self.assertFalse(app.action_lock.locked())

    async def test_watchdog_survives_failed_movement_and_zero_sends(self):
        with patch.object(app, 'connected', return_value=True), \
                patch.object(app, 'send_velocity', side_effect=RuntimeError('channel closing')) as send, \
                patch.object(app, 'armed', True), patch.object(app, 'desired', (1, 0, 0)), \
                patch.object(app, 'last_error', ''), patch.object(app, 'logger'):
            watchdog = asyncio.create_task(app.watchdog())
            try:
                await asyncio.sleep(0.12)
                self.assertFalse(watchdog.done())
                self.assertGreaterEqual(send.call_count, 2)
                self.assertFalse(app.armed)
                self.assertEqual(app.desired, (0, 0, 0))
            finally:
                watchdog.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await watchdog

    async def test_cancelling_handshake_releases_peer_and_operation_lock(self):
        entered = asyncio.Event()

        async def pending_connect():
            entered.set()
            await asyncio.Event().wait()

        connection = SimpleNamespace(connect=pending_connect, disconnect=AsyncMock())
        with patch.object(app, 'Go2Connection', return_value=connection), \
                patch.object(app, 'robot', None), patch.object(app, 'action_lock', asyncio.Lock()):
            pending = asyncio.create_task(app.open_robot_connection())
            await asyncio.wait_for(entered.wait(), 1)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            connection.disconnect.assert_awaited_once()
            self.assertIsNone(app.robot)
            self.assertFalse(app.armed)
            self.assertFalse(app.busy)
            self.assertFalse(app.action_lock.locked())

    async def test_link_loss_cancels_auto_movement_and_requires_recovery_again(self):
        with patch.object(app, 'send_velocity'), patch.object(app, 'armed', True), \
                patch.object(app, 'stance', 'balanced'), patch.object(app, 'recovery_needed', False), \
                patch.object(app, 'logger'):
            app.on_robot_link_lost()
            self.assertFalse(app.armed)
            self.assertEqual(app.stance, 'unknown')
            self.assertTrue(app.recovery_needed)


class DashboardSocketTests(unittest.TestCase):
    def test_ready_acknowledges_ownership_and_rejected_tab_cannot_disarm_owner(self):
        with patch.object(app, 'controller', None), patch.object(app, 'send_velocity'), \
                patch.object(app, 'armed', False):
            client = TestClient(app.app, base_url='http://127.0.0.1')
            route = 'ws://127.0.0.1/ws/control?token=' + app.TOKEN
            headers = {'origin': 'http://127.0.0.1'}
            with client.websocket_connect(route, headers=headers) as first:
                self.assertEqual(first.receive_json(), {'type': 'ready'})
                app.armed = True
                owner = app.controller
                with client.websocket_connect(route, headers=headers) as second:
                    with self.assertRaises(app.WebSocketDisconnect) as rejected:
                        second.receive_json()
                    self.assertEqual(rejected.exception.code, 1008)
                self.assertIs(app.controller, owner)
                self.assertTrue(app.armed)
            self.assertIsNone(app.controller)
            self.assertFalse(app.armed)
            client.close()


if __name__ == '__main__':
    unittest.main()
