"""Exercise camera freshness, concurrency and lesson API without hardware or OpenAI."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision_service import VisionService


def scene(count=2, clear=True):
    return {"objects": [{"label": "red toy car", "count": count}],
            "target_count": count, "scene_clear": clear, "reason": "Separated on the table."}


class VisionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 100.0
        self.camera_online = True
        self.camera_session = 1
        self.frame_age = 0.0
        self.service = VisionService(
            lambda: (b"jpeg", self.now - self.frame_age, self.camera_session),
            lambda: self.camera_online, clock=lambda: self.now,
        )
        self.service.pair_delay = 0
        self.service._api_key = "test-secret-do-not-echo"
        self.service.analyze = Mock(return_value=scene())
        app = FastAPI()
        app.include_router(self.service.router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost")
        await self.client.post("/api/vision/round", json={"target_object": "toy cars", "target_count": 3})

    async def asyncTearDown(self):
        await self.service.close()
        await self.client.aclose()

    async def scan(self):
        # Production requires a new frame timestamp; advance at pair capture.
        async def next_frame():
            self.now += 0.35
        self.service.wait_for_pair = next_frame
        return await self.client.post("/api/vision/scan", json={})

    async def test_specific_inventory_and_deterministic_answer_flow(self):
        response = await self.scan()
        self.assertEqual(response.status_code, 200, response.text)
        state = response.json()
        self.assertEqual(state["observation"]["objects"][0]["label"], "red toy car")
        self.assertEqual(state["lesson"]["missing_count"], 1)
        for answer, event in [(2, "try_again"), (1, "happy")]:
            response = await self.client.post("/api/vision/answer", json={
                "answer": answer, "round_id": state["round_id"], "observation_id": state["observation_id"],
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["last_event"]["event"], event)
            self.assertFalse(response.json()["last_event"]["task_complete"])
        self.assertEqual(self.service.analyze.call_count, 2)

    async def test_disconnected_or_stale_camera_never_calls_provider(self):
        for online, age in [(False, 0), (True, 3)]:
            self.camera_online, self.frame_age = online, age
            response = await self.scan()
            self.assertEqual(response.status_code, 409)
        self.service.analyze.assert_not_called()

    async def test_same_frame_is_not_an_independent_observation(self):
        response = await self.client.post("/api/vision/scan", json={})
        self.assertEqual(response.status_code, 409)
        self.service.analyze.assert_not_called()

    async def test_expired_observation_cannot_grade_answer_or_repeat_happy(self):
        state = (await self.scan()).json()
        self.now += 21
        response = await self.client.post("/api/vision/answer", json={
            "answer": 1, "round_id": state["round_id"], "observation_id": state["observation_id"],
        })
        self.assertEqual(response.status_code, 409)
        state = (await self.client.get("/api/vision/status")).json()
        self.assertFalse(state["observation_fresh"])
        self.assertEqual(state["lesson"]["status"], "uncertain")
        self.assertIsNone(state["last_event"])

    async def test_changed_round_and_changed_observation_reject_old_answers(self):
        old = (await self.scan()).json()
        await self.scan()
        response = await self.client.post("/api/vision/answer", json={
            "answer": 1, "round_id": old["round_id"], "observation_id": old["observation_id"],
        })
        self.assertEqual(response.status_code, 409)
        await self.client.post("/api/vision/round", json={"target_object": "cups", "target_count": 4})
        self.assertEqual((await self.client.post("/api/vision/answer", json={
            "answer": 1, "round_id": old["round_id"], "observation_id": old["observation_id"],
        })).status_code, 409)

    async def test_scan_result_after_stop_or_camera_change_is_discarded(self):
        for change in [self.service.stop_scanning, self.change_camera]:
            with self.subTest(change=change):
                entered, release = asyncio.Event(), asyncio.Event()
                async def delayed_pair(*args):
                    entered.set()
                    await release.wait()
                    return scene(), scene()
                self.service.analyze_pair = delayed_pair
                scan = asyncio.create_task(self.scan())
                await entered.wait()
                change()
                release.set()
                response = await scan
                self.assertEqual(response.status_code, 409)
                self.assertIsNone(response.json().get("observation"))
                self.assertFalse(self.service.status()["busy"])

    def change_camera(self):
        self.camera_session += 1

    async def test_inflight_scan_is_not_duplicated(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed_pair(*args):
            entered.set()
            await release.wait()
            return scene(), scene()
        self.service.analyze_pair = delayed_pair
        scan = asyncio.create_task(self.scan())
        await entered.wait()
        response = await self.client.post("/api/vision/scan", json={})
        self.assertEqual(response.status_code, 409)
        release.set()
        self.assertEqual((await scan).status_code, 200)

    async def test_missing_key_and_key_validation_do_not_leak_secrets(self):
        self.service._api_key = ""
        response = await self.scan()
        self.assertEqual(response.status_code, 409)
        for payload in [{"api_key": ["do-not-echo"]}, {"api_key": "do-not-echo\n"}]:
            response = await self.client.post("/api/vision/key", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("do-not-echo", response.text)
        response = await self.client.post("/api/vision/key", json={"api_key": "sk-test-do-not-echo"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["configured"])
        self.assertNotIn("sk-test", response.text)

    async def test_invalid_target_and_bool_answer_are_rejected(self):
        for payload in [{"target_object": "", "target_count": 3}, {"target_object": "cups", "target_count": True}]:
            self.assertEqual((await self.client.post("/api/vision/round", json=payload)).status_code, 400)
        state = (await self.scan()).json()
        response = await self.client.post("/api/vision/answer", json={
            "answer": True, "round_id": state["round_id"], "observation_id": state["observation_id"],
        })
        self.assertEqual(response.status_code, 400)

    async def test_uncertain_frames_do_not_grade_or_invent_zero(self):
        self.service.analyze.side_effect = [scene(2), scene(3)]
        state = (await self.scan()).json()
        self.assertIsNone(state["observation"]["observed_count"])
        self.assertEqual(state["lesson"]["status"], "uncertain")
        response = await self.client.post("/api/vision/answer", json={
            "answer": 1, "round_id": state["round_id"], "observation_id": state["observation_id"],
        })
        self.assertEqual(response.status_code, 409)

    async def test_live_session_is_bounded_and_reports_camera_loss(self):
        self.service.SESSION_SCANS = 2
        self.service.INTERVAL = 0.001
        async def next_frame():
            self.now += 0.35
        self.service.wait_for_pair = next_frame
        response = await self.client.post("/api/vision/start", json={})
        self.assertEqual(response.status_code, 200)
        await asyncio.gather(*list(self.service._runners))
        self.assertEqual(self.service.analyze.call_count, 4)
        self.assertFalse(self.service.running)
        await self.client.post("/api/vision/start", json={})
        self.camera_online = False
        await asyncio.gather(*list(self.service._runners))
        self.assertIn("offline", self.service.status()["error"])

    async def test_vision_routes_keep_existing_control_token_gate(self):
        import app as dashboard
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=dashboard.app), base_url="http://localhost")
        try:
            for route in ["status", "key", "round", "scan", "start", "stop", "answer"]:
                method = "GET" if route == "status" else "POST"
                response = await client.request(method, "/api/vision/" + route)
                self.assertEqual(response.status_code, 403)
            response = await client.get("/api/vision/status", headers={"X-Control-Token": dashboard.TOKEN})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("api_key", response.json())
        finally:
            await client.aclose()


if __name__ == "__main__":
    unittest.main()
