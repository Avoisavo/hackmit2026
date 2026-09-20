import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI, HTTPException

from robot.control_plane import ControlPlane, AudioProviders, number_answer


class FakeVision:
    _api_key = "sk-test"
    busy = False
    def __init__(self):
        self.count, self.fresh, self.stable, self.camera = 2, True, True, True
        self.scan_count = 0
    def camera_fresh(self): return self.camera
    def stop_scanning(self): pass
    def clear_observation(self): pass
    def status(self):
        return {"observation_fresh": self.fresh,
                "observation": {"stable": self.stable, "observed_count": self.count}}
    async def scan(self):
        self.scan_count += 1
        return self.status()


class PlaneTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 100
        self.vision = FakeVision()
        self.acquire = Mock(return_value="operator-context")
        self.finish = Mock()
        self.gesture = AsyncMock()
        self.stop = Mock(side_effect=lambda reason: self.plane.cancel(reason))
        self.plane = ControlPlane(vision=self.vision, acquire=self.acquire, check_context=Mock(),
            stop_robot=self.stop, gesture=self.gesture, finish=self.finish, clock=lambda: self.now)
        self.plane.audio.deepgram = "dg-test-key"
        self.plane.audio.elevenlabs = "el-test-key"
        self.plane.audio.voice_id = "voice123"
        self.plane.audio.token = Mock(return_value={"access_token": "short-lived-test-token"})
        self.plane.audio.speak = Mock(return_value=b"fake-mp3")
        app = FastAPI(); app.include_router(self.plane.router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost")
        self.keys = {}
        await self.pair("speaker")

    async def asyncTearDown(self):
        await self.plane.close()
        await self.client.aclose()

    async def pair(self, role):
        data = (await self.client.post("/api/plane/pair", json={"role": role})).json()
        self.keys[role] = data["key"]
        self.assertEqual((await self.device(role, "state")).status_code, 200)
        return data

    async def device(self, role, path, payload=None, client_id="device_12345678", extra=""):
        return await self.client.request("GET" if payload is None else "POST",
            f"/session/{path}?client_id={client_id}{extra}",
            headers={"X-Device-Key": self.keys[role]}, json=payload)

    async def start(self, **kwargs):
        result = await self.client.post("/api/plane/start", json={"target": 3, "wave": False,
            "control_id": "test-operator", "control_epoch": 42, **kwargs})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    async def finish_speech(self):
        payload = {"session_id": self.plane.session_id, "speech_id": self.plane.speech["id"]}
        for status in ("started", "ended"):
            response = await self.device("speaker", "speech", {**payload, "status": status})
            self.assertEqual(response.status_code, 200, response.text)

    async def question(self):
        await self.finish_speech()
        for _ in range(20):
            if self.plane.speech: break
            await asyncio.sleep(0.01)
        self.assertIsNotNone(self.plane.speech)
        await self.finish_speech()
        self.assertEqual(self.plane.phase, "waiting_answer")

    def answer_body(self, text, event_id="answer_12345678"):
        return {"text": text, "session_id": self.plane.session_id,
                "question_id": self.plane.question_id, "event_id": event_id}

    async def test_exact_two_then_one_flow_synchronizes_voice_face_and_optional_robot(self):
        await self.start(wave=True)
        self.assertIn("three blocks", self.plane.speech["text"])
        await self.question()
        self.assertEqual(self.plane.observed, 2)
        wrong = await self.client.post("/api/plane/answer", json=self.answer_body("two"))
        self.assertEqual(wrong.status_code, 200)
        self.assertIn("How many more", self.plane.speech["text"])
        self.assertNotIn("comes after", self.plane.speech["text"])
        self.assertEqual(self.plane.face, "Encourage")
        await self.finish_speech()
        answer = self.answer_body("one", "correct_12345678")
        self.assertEqual((await self.client.post("/api/plane/answer", json=answer)).status_code, 200)
        self.assertTrue(self.plane.answer_correct)
        self.assertFalse(self.plane.task_complete)
        self.assertEqual(self.plane.face, "Celebrate")
        self.assertIn("one more", self.plane.speech["text"])
        self.assertEqual((await self.client.post("/api/plane/answer", json=answer)).status_code, 200)
        await self.finish_speech()
        await asyncio.wait_for(self.plane._task, 1)
        self.gesture.assert_awaited_once()
        self.finish.assert_called_once_with("operator-context")
        self.assertFalse(self.plane.running)
        self.assertEqual(self.plane.phase, "complete")

    async def test_gesture_is_opt_in_and_three_observed_blocks_complete_physical_task(self):
        self.vision.count = 3
        await self.start()
        await self.finish_speech()
        await asyncio.sleep(0.12)
        self.assertTrue(self.plane.task_complete)
        self.assertFalse(self.plane.answer_correct)
        self.assertEqual(self.plane.face, "Celebrate")
        await self.finish_speech()
        await self.plane._task
        self.gesture.assert_not_awaited()

    async def test_zero_blocks_waits_without_asking_premature_math_question(self):
        self.vision.count = 0
        await self.start(); await self.finish_speech(); await asyncio.sleep(0.12)
        self.assertEqual(self.plane.phase, "observing")
        self.assertIsNone(self.plane.speech)
        self.assertEqual(self.plane.face, "Watching")

    async def test_camera_reading_during_speech_is_retained_and_revalidated(self):
        await self.start()
        self.plane.observation(self.vision.status())
        self.assertIsNotNone(self.plane._pending_observation)
        await self.finish_speech()
        self.assertIsNotNone(self.plane.speech)
        self.assertIn("two blocks", self.plane.speech["text"])
        self.assertEqual(self.plane.observed, 2)

    async def test_expired_pending_camera_observation_does_not_become_a_question(self):
        await self.start()
        self.plane.observation(self.vision.status())
        self.vision.fresh = False
        await self.finish_speech()
        self.assertIsNone(self.plane.speech)
        self.assertEqual(self.plane.phase, "observing")
        self.assertEqual(self.plane.face, "Soft confused")

    async def test_stale_or_changed_count_cannot_grade_a_child(self):
        await self.start(); await self.question()
        self.vision.count = 1
        result = await self.client.post("/api/plane/answer", json=self.answer_body("one"))
        self.assertEqual(result.status_code, 409)
        self.assertFalse(self.plane.answer_correct)
        self.assertEqual(self.plane.phase, "observing")

    async def test_final_transcript_is_bound_to_current_question_and_not_accepted_while_speaking(self):
        await self.pair("mic"); await self.start()
        self.assertEqual((await self.device("mic", "transcript", self.answer_body("one"))).status_code, 409)
        await self.question()
        old = self.answer_body("one")
        old["question_id"] = "previous-question"
        self.assertEqual((await self.device("mic", "transcript", old)).status_code, 409)
        result = await self.device("mic", "transcript", self.answer_body("one"))
        self.assertEqual(result.status_code, 200)
        self.assertTrue(self.plane.answer_correct)

    async def test_stop_invalidates_late_audio_and_speech_acknowledgement(self):
        await self.start()
        speech = self.plane.speech["id"]
        session = self.plane.session_id
        await self.client.post("/api/plane/stop")
        ack = await self.device("speaker", "speech", {"session_id": session, "speech_id": speech, "status": "ended"})
        self.assertEqual(ack.status_code, 409)
        audio = await self.device("speaker", "audio", extra="&speech_id=" + speech)
        self.assertEqual(audio.status_code, 409)
        self.plane.audio.speak.assert_not_called()
        self.assertEqual(self.plane.phase, "stopped")
        self.assertIsNone(self.plane.speech)

    async def test_failed_playback_stops_instead_of_advancing(self):
        await self.start()
        result = await self.device("speaker", "speech", {"session_id": self.plane.session_id,
            "speech_id": self.plane.speech["id"], "status": "error"})
        self.assertEqual(result.status_code, 200)
        self.assertFalse(self.plane.running)
        self.assertEqual(self.vision.scan_count, 0)

    async def test_spoken_stop_wins_even_if_camera_observation_expired(self):
        await self.start(); await self.question()
        self.vision.fresh = False
        response = await self.client.post("/api/plane/answer", json=self.answer_body("please stop"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.plane.running)
        self.assertEqual(self.plane.message, "Child requested a stop")

    async def test_speech_end_without_start_is_rejected(self):
        await self.start()
        result = await self.device("speaker", "speech", {"session_id": self.plane.session_id,
            "speech_id": self.plane.speech["id"], "status": "ended"})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.plane.phase, "speaking")

    async def test_role_keys_cannot_impersonate_speaker_or_call_speech_provider(self):
        await self.pair("face")
        for path in ("speech", "transcript", "deepgram"):
            self.assertEqual((await self.device("face", path, {})).status_code, 403)
        self.assertEqual((await self.device("face", "audio")).status_code, 403)
        view = (await self.device("face", "state")).json()
        self.assertIsNone(view["speech"])
        for secret in (self.keys["speaker"], "dg-test-key", "el-test-key", "sk-test"):
            self.assertNotIn(secret, json.dumps(view))
            self.assertNotIn(secret, json.dumps(self.plane.status()))

    async def test_only_one_player_owns_each_role_and_repair_revokes_old_key(self):
        old = self.keys["speaker"]
        self.assertEqual((await self.device("speaker", "state", client_id="different_tab_123")).status_code, 409)
        await self.pair("speaker")
        result = await self.client.get("/session/state?client_id=device_12345678", headers={"X-Device-Key": old})
        self.assertEqual(result.status_code, 403)

    async def test_device_and_camera_loss_stop_without_resuming(self):
        await self.start()
        self.now += 5
        await asyncio.wait_for(self.plane._task, 1)
        self.assertFalse(self.plane.running)
        self.assertIn("Speaker disconnected", self.plane.message)
        await self.device("speaker", "state")
        self.assertFalse(self.plane.running)
        await self.start()
        self.vision.camera = False
        await asyncio.wait_for(self.plane._task, 1)
        self.assertFalse(self.plane.running)
        self.assertIn("Camera", self.plane.message)

    async def test_start_missing_dependencies_has_no_actuator_effect(self):
        self.vision.camera = False
        result = await self.client.post("/api/plane/start", json={})
        self.assertEqual(result.status_code, 409)
        self.acquire.assert_not_called()
        self.gesture.assert_not_awaited()

    async def test_audio_is_generated_once_for_exact_current_line_and_cannot_speak_arbitrary_text(self):
        await self.start()
        speech_id = self.plane.speech["id"]
        for _ in range(2):
            result = await self.device("speaker", "audio", extra="&speech_id=" + speech_id + "&text=unauthorized")
            self.assertEqual(result.content, b"fake-mp3")
        self.plane.audio.speak.assert_called_once_with(self.plane.speech["text"])

    async def test_key_validation_is_atomic_and_does_not_echo_values(self):
        response = await self.client.post("/api/plane/keys", json={"deepgram": "updated", "voice_id": "../bad"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.plane.audio.deepgram, "dg-test-key")
        response = await self.client.post("/api/plane/keys", json={"openai": "sk-new-secret", "voice_id": "voice_new"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.vision._api_key, "sk-new-secret")
        self.assertNotIn("sk-new-secret", response.text)

    async def test_slow_speech_provider_cannot_return_playable_audio_after_stop(self):
        await self.start()
        entered, release = asyncio.Event(), asyncio.Event()
        async def work():
            entered.set(); await release.wait(); return b"fake-mp3"
        async def threaded(fn, *args): return await work()
        with patch("robot.control_plane.asyncio.to_thread", side_effect=threaded):
            pending = asyncio.create_task(self.device("speaker", "audio", extra="&speech_id=" + self.plane.speech["id"]))
            await entered.wait()
            await self.client.post("/api/plane/stop")
            release.set()
            response = await pending
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.plane.running)


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_server_routes_hide_operator_credentials_from_lan_devices(self):
        from robot import app
        remote = httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app, client=("192.0.2.10", 4000)),
                                  base_url="http://localhost")
        local = httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url="http://localhost")
        try:
            for path in ("/", "/plane", "/vision"):
                self.assertEqual((await remote.get(path)).status_code, 403)
            for role in ("mic", "face", "speaker"):
                response = await remote.get("/device/" + role)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(app.TOKEN, response.text)
            response = await local.get("/plane")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Control plane", response.text)
            self.assertIn(app.TOKEN, response.text)
            self.assertEqual((await remote.get("/api/plane/status")).status_code, 403)
            self.assertEqual((await remote.post("/api/connect", headers={"X-Device-Key": "role-key"})).status_code, 403)
        finally:
            await remote.aclose(); await local.aclose()

    async def test_websocket_origin_supports_tls_without_allowing_cross_origin(self):
        from robot import app
        socket = SimpleNamespace(scope={"scheme": "wss"}, headers={"host": "localhost:8020", "origin": "https://localhost:8020"})
        self.assertTrue(app.same_origin(socket))
        socket.headers["origin"] = "https://other-host:8020"
        self.assertFalse(app.same_origin(socket))

    async def test_activity_and_independent_camera_agent_cannot_both_acquire_motion(self):
        from robot import app
        with patch.object(app.plane, "running", True), self.assertRaises(HTTPException):
            app.acquire_ai("any-id", 42)

    async def test_other_vision_pages_cannot_change_the_activity_target_or_camera_key(self):
        from robot import app
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url="http://localhost",
                                    headers={"X-Control-Token": app.TOKEN}) as client:
            with patch.object(app.plane, "running", True):
                for path in ("/api/vision/round", "/api/vision/key", "/api/vision/start", "/api/ai/key"):
                    response = await client.post(path, json={})
                    self.assertEqual(response.status_code, 409)


class NumberTests(unittest.TestCase):
    def test_ambiguous_answers_are_not_silently_graded(self):
        for text in ("two or one", "I don't know", "one hundred", "999999", "-1", "twenty one", "1.5", "minus one"):
            self.assertIsNone(number_answer(text))
        self.assertEqual(number_answer("I think one!"), 1)
        self.assertEqual(number_answer("1"), 1)


if __name__ == "__main__": unittest.main()
