import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from robot.control_plane import ControlPlane
from robot.ai_agent import TOOLS
from robot import app


class ComponentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 100
        self.speaker = SimpleNamespace(ready=Mock(return_value=True), play=AsyncMock(return_value={"sent": True}),
            stop=Mock(), status=lambda: {"ready": True, "output": "go2"})
        self.vision = SimpleNamespace(_api_key='sk-test', busy=False, camera_fresh=lambda: True,
            stop_scanning=Mock(), clear_observation=Mock(), scan=AsyncMock(return_value={}), status=lambda: {})
        self.acquire = Mock(return_value='context')
        self.plane = ControlPlane(vision=self.vision, acquire=self.acquire, check_context=Mock(),
            stop_robot=lambda reason: self.plane.cancel(reason), gesture=AsyncMock(), finish=Mock(),
            speaker=self.speaker, clock=lambda: self.now)
        self.plane.audio.elevenlabs = 'test'; self.plane.audio.voice_id = 'voice'
        self.plane.audio.speak = Mock(return_value=b'fake-audio')
        server = FastAPI(); server.include_router(self.plane.router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url='http://localhost')

    async def asyncTearDown(self):
        await self.plane.close(); await self.client.aclose()

    async def test_tone_needs_no_voice_key_and_uses_robot_output_only(self):
        self.plane.audio.elevenlabs = ''
        response = await self.client.post('/api/plane/test', json={'kind': 'tone', 'control_id': 'owner', 'control_epoch': 4})
        self.assertEqual(response.status_code, 200)
        await self.plane._test_task
        self.acquire.assert_called_once_with('owner', 4)
        self.speaker.play.assert_awaited_once()
        self.assertTrue(self.speaker.play.call_args.kwargs['tone'])
        self.plane.audio.speak.assert_not_called()
        self.assertEqual(self.plane.test['status'], 'complete')

    async def test_stop_while_generating_voice_prevents_late_playback(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def generate(*args): entered.set(); await release.wait(); return b'late-voice'
        with patch('robot.control_plane.asyncio.to_thread', side_effect=generate):
            self.assertEqual((await self.client.post('/api/plane/test', json={'kind': 'voice'})).status_code, 200)
            await entered.wait()
            await self.client.post('/api/plane/stop')
            self.assertTrue(self.plane.busy)
            self.assertEqual((await self.client.post('/api/plane/test', json={'kind': 'tone'})).status_code, 409)
            release.set(); await self.plane._test_task
        self.speaker.play.assert_not_awaited()
        self.assertEqual(self.plane.test['status'], 'stopped')

    async def test_robot_activity_no_longer_requires_a_paired_browser_speaker(self):
        response = await self.client.post('/api/plane/start', json={})
        self.assertEqual(response.status_code, 200, response.text)
        await self.plane._speech_task
        self.speaker.play.assert_awaited_once()
        self.assertEqual(self.plane.phase, 'observing')
        self.assertFalse(self.plane.online('speaker'))
        self.plane.cancel()
        await self.plane._task

    async def test_browser_speaker_cannot_advance_go2_speech(self):
        data = (await self.client.post('/api/plane/pair', json={'role': 'speaker'})).json()
        headers = {'X-Device-Key': data['key']}
        response = await self.client.post('/session/speech?client_id=client_1234', headers=headers, json={'status': 'ended'})
        self.assertEqual(response.status_code, 409)
        response = await self.client.get('/session/audio?client_id=client_1234', headers=headers)
        self.assertEqual(response.status_code, 409)
        self.plane.audio.speak.assert_not_called()

    async def test_microphone_test_transcript_does_not_grade_or_move_robot(self):
        data = (await self.client.post('/api/plane/pair', json={'role': 'mic'})).json()
        headers = {'X-Device-Key': data['key']}
        path = '?client_id=microphone123'
        await self.client.get('/session/state'+path, headers=headers)
        response = await self.client.post('/api/plane/test', json={'kind': 'microphone'})
        self.assertEqual(response.status_code, 200)
        state = (await self.client.get('/session/state'+path, headers=headers)).json()
        self.assertTrue(state['listen'])
        self.assertFalse(state['running'])
        response = await self.client.post('/session/transcript'+path, headers=headers,
            json={'text': 'two blocks', 'session_id': state['session_id']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.plane.test['transcript'], 'two blocks')
        self.acquire.assert_not_called()
        self.speaker.play.assert_not_awaited()
        self.now += 21
        await self.plane._test_task
        self.assertEqual(self.plane.test['status'], 'complete')
        response = await self.client.post('/session/transcript'+path, headers=headers,
            json={'text': 'late answer', 'session_id': state['session_id']})
        self.assertEqual(response.status_code, 409)


class ToolApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),
            base_url='http://localhost', headers={'X-Control-Token': app.TOKEN})
        self.calls = []
        async def execute(name, args, context, check):
            check(); self.calls.append((name,args)); return {'accepted': True, 'stopped': True}
        state = {'_task': None, '_epoch': 0, 'running': False, 'phase': 'idle', 'steps': [], '_seen_runs': [],
            'get_frame': lambda: (b'jpeg', time.monotonic(), 1), 'acquire': Mock(return_value='context'),
            'check_context': Mock(), 'execute': execute, 'finish': Mock()}
        for key, value in state.items():
            change = patch.object(app.ai, key, value); change.start(); self.addCleanup(change.stop)

    async def asyncTearDown(self):
        await app.ai.close(); await self.client.aclose()

    def payload(self, **kwargs):
        return {'name': 'move_robot', 'arguments': {'direction': 'forward', 'seconds': .3, 'speed': .15, 'reason': 'Test clear space'},
            'run_id': 'unique_test_call_123', 'control_id': 'operator', 'control_epoch': 7, **kwargs}

    async def test_catalog_matches_the_actual_model_schemas_and_has_manual_only_flips(self):
        response = await self.client.get('/api/ai/tools')
        self.assertEqual(response.status_code, 200)
        catalog = response.json()
        self.assertEqual(catalog['tools'], TOOLS)
        flips = [m for m in catalog['movements'] if 'flip' in m['name']]
        self.assertTrue(flips); self.assertTrue(all(m['ai_tool'] is None for m in flips))
        self.assertEqual((await self.client.get('/api/ai/tools', headers={'X-Control-Token': 'bad'})).status_code, 403)

    async def test_guarded_dispatch_is_idempotent_and_returns_the_executor_result(self):
        response = await self.client.post('/api/ai/call', json=self.payload())
        self.assertEqual(response.status_code, 200)
        await app.ai._task
        self.assertEqual(app.ai.phase, 'complete')
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(app.ai.steps[-1]['result']['stopped'])
        app.ai.acquire.assert_called_once_with('operator', 7)
        response = await self.client.post('/api/ai/call', json=self.payload())
        self.assertTrue(response.json()['duplicate'])
        self.assertEqual(len(self.calls), 1)

    async def test_invalid_tool_limits_and_stale_camera_have_no_actuator_effect(self):
        for changes in ({'name': 'front_flip'}, {'arguments': {'direction': 'forward', 'seconds': 50, 'speed': .15, 'reason': 'bad'}}):
            response = await self.client.post('/api/ai/call', json=self.payload(**changes))
            self.assertEqual(response.status_code, 400)
        with patch.object(app.ai, 'get_frame', return_value=(b'jpeg', 0, 1)):
            self.assertEqual((await self.client.post('/api/ai/call', json=self.payload())).status_code, 409)
        app.ai.acquire.assert_not_called()
        self.assertFalse(self.calls)

    async def test_stop_before_queued_tool_executes_prevents_execution(self):
        # Stop synchronously at task creation so the asynchronous tool sees an old generation.
        task_factory = asyncio.create_task
        def schedule(coroutine):
            task = task_factory(coroutine)
            app.ai.cancel('STOP')
            return task
        # Call the handler directly: patch only the task creator used there.
        request = SimpleNamespace(stream=None)
        with patch.object(app.ai, 'body', AsyncMock(return_value=self.payload())), patch('robot.ai_agent.asyncio.create_task', side_effect=schedule):
            await app.ai.call_api(request)
        await app.ai._task
        self.assertFalse(self.calls)
        self.assertEqual(app.ai.phase, 'stopped')

    async def test_landing_redirect_and_new_controls_remain_local_only(self):
        response = await self.client.get('/')
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers['location'], '/plane')
        page = await self.client.get('/plane')
        for label in ('Play speaker test tone', 'Test ElevenLabs voice', 'Movement tool map', 'Listen for 20 seconds'):
            self.assertIn(label, page.text)
        self.assertEqual((await self.client.get('/controls')).status_code, 200)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app, client=('192.0.2.1',4000)), base_url='http://localhost') as remote:
            self.assertEqual((await remote.get('/controls')).status_code, 403)
