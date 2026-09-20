"""Vision wiring must reuse the camera without changing driving or recovery."""
import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx

from robot import app


class VisionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = SimpleNamespace(
            pc=SimpleNamespace(connectionState="connected"),
            datachannel=SimpleNamespace(
                data_channel_opened=True,
                pub_sub=SimpleNamespace(
                    channel=SimpleNamespace(readyState="open"),
                    publish_without_callback=Mock(),
                ),
            ),
            disconnect=AsyncMock(),
        )
        for name, value in {
            "robot": self.connection, "latest_jpeg": b"current-frame",
            "frame_at": time.monotonic(), "camera_session": 42,
            "armed": True, "desired": (1, 0, 0), "recovery_task": None,
            "stop_epoch": 0, "stance": "balanced", "recovery_needed": False,
        }.items():
            replacement = patch.object(app, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        frame = lambda: (app.latest_jpeg, app.frame_at, app.camera_session)
        boxes = patch.object(app, "boxes", app.BoxService(frame, app.connected))
        boxes.start()
        self.addCleanup(boxes.stop)
        vision = patch.object(app, "vision", app.VisionService(
            frame, app.connected, box_status=app.boxes.status,
        ))
        vision.start()
        self.addCleanup(vision.stop)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.app), base_url="http://127.0.0.1",
            headers={"X-Control-Token": app.TOKEN},
        )

    async def asyncTearDown(self):
        await app.vision.close()
        await app.boxes.close()
        await self.client.aclose()

    async def test_pages_and_box_stream_reuse_existing_robot_without_motion(self):
        for route, expected in [("/controls", "Robot IP"), ("/vision", "Look &amp; Count")]:
            response = await self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertIn(expected, response.text)
            self.assertNotIn("__TOKEN__", response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")
        app.boxes.infer = AsyncMock(return_value={
            "jpeg": b"boxed-current-frame", "detections": [{"label": "cup"}],
            "device": "cpu",
        })
        response = await app.camera_boxes(app.TOKEN)
        stream = response.body_iterator
        try:
            frame = await asyncio.wait_for(anext(stream), 2)
            self.assertIn(b"boxed-current-frame", frame)
            app.boxes.infer.assert_awaited_once_with(b"current-frame")
            status = (await self.client.get("/api/status")).json()
            self.assertEqual(status["boxes"]["count"], 1)
            self.assertTrue(status["armed"])
            self.assertEqual(status["stance"], "balanced")
            self.connection.datachannel.pub_sub.publish_without_callback.assert_not_called()
        finally:
            await stream.aclose()

    async def test_box_stream_requires_camera_token(self):
        for query in ["", "?token=wrong"]:
            response = await self.client.get("/camera.boxes.mjpeg" + query)
            self.assertEqual(response.status_code, 403)
        self.assertIsNone(app.boxes._task)

    async def test_disconnect_clears_both_vision_results_and_disarms(self):
        app.vision.running = True
        app.vision._observation = {"observed_count": 3, "stable": True}
        app.boxes._latest = (app.frame_at, 42, {"jpeg": b"old", "detections": []})
        await app.disconnect()
        self.assertEqual(app.camera_session, 43)
        self.assertEqual(app.latest_jpeg, b"")
        self.assertEqual(app.frame_at, 0)
        self.assertFalse(app.vision.running)
        self.assertIsNone(app.vision._observation)
        self.assertIsNone(app.boxes._latest)
        self.assertFalse(app.armed)
        self.assertTrue(app.recovery_needed)
        self.connection.disconnect.assert_awaited_once()

    async def test_frame_encoding_in_flight_cannot_restore_disconnected_camera(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed_encode(*args):
            entered.set()
            await release.wait()
            return b"old-frame"

        with patch.object(app.asyncio, "to_thread", side_effect=delayed_encode):
            reader = asyncio.create_task(app.read_video(SimpleNamespace(recv=AsyncMock())))
            await asyncio.wait_for(entered.wait(), 2)
            await app.disconnect()
            release.set()
            await asyncio.wait_for(reader, 2)
        self.assertEqual(app.latest_jpeg, b"")
        self.assertEqual(app.frame_at, 0)


if __name__ == "__main__":
    unittest.main()
