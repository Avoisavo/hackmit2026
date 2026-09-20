"""Box stream lifecycle tests, without models, camera hardware or API calls."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from box_service import BoxService


class BoxServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 10.0
        self.camera_session = 1
        self.online = True
        self.calls = 0
        self.service = BoxService(lambda: (b"source", self.now, self.camera_session),
                                  lambda: self.online, clock=lambda: self.now)
        async def infer(jpeg):
            self.calls += 1
            return {"jpeg": b"annotated", "detections": [{"label": "chair"}],
                    "width": 960, "height": 540, "device": "cpu"}
        self.service.infer = infer

    async def asyncTearDown(self):
        await self.service.close()

    async def test_subscribers_share_one_worker_and_receive_exact_annotated_image(self):
        one, two = self.service.frames(), self.service.frames()
        frames = await asyncio.wait_for(asyncio.gather(anext(one), anext(two)), 2)
        self.assertEqual(self.calls, 1)
        self.assertTrue(all(b"annotated" in frame and b"source" not in frame for frame in frames))
        self.assertEqual(self.service.status()["count"], 1)
        self.assertEqual(self.service.status()["state"], "running")
        await one.aclose()
        await two.aclose()

    async def test_result_from_old_camera_session_is_never_published(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(jpeg):
            entered.set()
            await release.wait()
            return {"jpeg": b"old", "detections": [], "width": 1, "height": 1, "device": "cpu"}
        self.service.infer = delayed
        stream = self.service.frames()
        pending = asyncio.create_task(anext(stream))
        await entered.wait()
        self.camera_session += 1
        self.online = False
        self.service.invalidate_camera()
        release.set()
        with self.assertRaises(StopAsyncIteration):
            await pending
        self.assertEqual(self.service.status()["count"], 0)
        self.assertIsNone(self.service._latest)

    async def test_expired_boxes_are_not_advertised_as_current(self):
        stream = self.service.frames()
        await asyncio.wait_for(anext(stream), 2)
        self.now += 4
        self.assertEqual(self.service.status()["count"], 0)
        self.assertGreater(self.service.status()["frame_age_seconds"], 3)
        await stream.aclose()

    async def test_detector_failure_is_visible_and_stream_exits(self):
        async def fail(jpeg):
            raise RuntimeError("model unavailable")
        self.service.infer = fail
        stream = self.service.frames()
        with self.assertRaises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), 2)
        self.assertEqual(self.service.status()["state"], "error")
        self.assertTrue(self.service.status()["error"])


if __name__ == "__main__":
    unittest.main()
