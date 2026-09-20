import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from unitree_webrtc_connect.msgs.pub_sub import WebRTCDataChannelPubSub

from robot import app


class FakeChannel:
    readyState = "open"

    def __init__(self):
        self.sent = asyncio.Queue()

    def send(self, message):
        self.sent.put_nowait(json.loads(message))


class RequestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.channel = FakeChannel()
        # Exercise the installed SDK's real resolver, not a mock of request().
        self.pub_sub = WebRTCDataChannelPubSub(self.channel)
        self.resolver = self.pub_sub.future_resolver
        self.robot = patch.object(app, "robot", SimpleNamespace(
            datachannel=SimpleNamespace(pub_sub=self.pub_sub)
        ))
        self.robot.start()
        self.addCleanup(self.robot.stop)

    def reply(self, sent):
        message = {"type": "response", "topic": sent["topic"], "data": {
            "header": {"identity": sent["data"]["header"]["identity"],
                       "status": {"code": 0}},
        }}
        self.pub_sub.run_resolve(message)
        return message

    async def start_request(self, timeout=1):
        pending = asyncio.create_task(app.request(
            "simulated/sport", {"api_id": 1029}, timeout=timeout
        ))
        sent = await asyncio.wait_for(self.channel.sent.get(), 1)
        return pending, sent

    async def test_normal_and_duplicate_replies_do_not_leak_callbacks(self):
        pending, sent = await self.start_request()
        expected = self.reply(sent)
        self.assertEqual(await pending, expected)
        self.reply(sent)
        self.assertEqual(self.resolver.pending_callbacks, {})

    async def test_late_reply_after_timeout_does_not_raise_invalid_state(self):
        pending, sent = await self.start_request(timeout=0.01)
        request_id = sent["data"]["header"]["identity"]["id"]
        future = self.resolver.pending_callbacks[request_id][0]
        with self.assertRaises(asyncio.TimeoutError):
            await pending
        self.assertTrue(future.cancelled())
        self.assertEqual(self.resolver.pending_callbacks, {})
        received = []
        self.pub_sub.subscriptions["simulated/sport"] = received.append
        self.reply(sent)
        # The old InvalidStateError also prevented subscription dispatch.
        self.assertEqual(len(received), 1)

    async def test_cancelled_recovery_cleans_callbacks_before_a_late_reply(self):
        pending, sent = await self.start_request()
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertEqual(self.resolver.pending_callbacks, {})
        self.reply(sent)

    async def test_timed_out_request_does_not_consume_another_requests_reply(self):
        first, first_message = await self.start_request(timeout=0.01)
        second, second_message = await self.start_request()
        with self.assertRaises(asyncio.TimeoutError):
            await first
        self.reply(first_message)
        self.assertFalse(second.done())
        expected = self.reply(second_message)
        self.assertEqual(await second, expected)
        self.assertEqual(self.resolver.pending_callbacks, {})

    async def test_timeout_also_cleans_partial_chunk_data(self):
        pending, sent = await self.start_request(timeout=0.01)
        request_id = sent["data"]["header"]["identity"]["id"]
        self.resolver.chunk_data_storage[request_id] = [b"partial"]
        with self.assertRaises(asyncio.TimeoutError):
            await pending
        self.assertEqual(self.resolver.chunk_data_storage, {})


if __name__ == "__main__":
    unittest.main()
