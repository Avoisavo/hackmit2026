"""Go2 Air audio tests use a browser speaker and never acquire robot motion."""
import asyncio
import io
import time
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI, HTTPException
from robot.control_plane import ControlPlane
from robot import app


class AirAudioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 100
        self.motion = Mock(side_effect=AssertionError('Audio must not acquire robot'))
        vision = SimpleNamespace(_api_key='', camera_fresh=lambda: False)
        self.guard = Mock()
        self.plane = ControlPlane(vision=vision, acquire=self.motion, check_context=Mock(),
            stop_robot=lambda reason: self.plane.cancel(reason), gesture=AsyncMock(), finish=Mock(),
            audio_acquire=Mock(return_value='audio-tab-context'), audio_check=self.guard,
            clock=lambda: self.now)
        self.plane.audio.elevenlabs = ''
        self.plane.audio.voice_id = ''
        self.plane.audio.speak = Mock(return_value=b'fake-mp3')
        server = FastAPI(); server.include_router(self.plane.router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url='http://localhost')
        key = (await self.client.post('/api/plane/pair',json={'role':'speaker'})).json()['key']
        self.headers = {'X-Device-Key': key}
        await self.device('state')

    async def asyncTearDown(self):
        await self.plane.close(); await self.client.aclose()

    async def device(self, path, payload=None, extra=''):
        return await self.client.request('GET' if payload is None else 'POST',
            '/session/'+path+'?client_id=air_speaker_123'+extra, headers=self.headers, json=payload)

    async def start(self, kind='tone'):
        response = await self.client.post('/api/plane/test',json={'kind':kind,'control_id':'operator','control_epoch':42})
        self.assertEqual(response.status_code,200,response.text)
        await asyncio.sleep(0)
        return (await self.device('state')).json()

    def ack(self, state, status):
        return {'session_id':state['session_id'],'speech_id':state['speech']['id'],'status':status}

    async def test_tone_works_without_robot_or_keys_and_waits_for_browser_completion(self):
        state = await self.start()
        self.assertEqual(self.plane.speaker_output,'browser')
        self.assertTrue(state['running'])
        self.assertFalse(self.plane.running)
        self.assertEqual(state['speech']['kind'],'tone')
        response = await self.device('audio',extra='&speech_id='+state['speech']['id'])
        self.assertEqual(response.headers['content-type'],'audio/wav')
        with wave.open(io.BytesIO(response.content),'rb') as wav:
            self.assertEqual((wav.getnchannels(),wav.getframerate()),(1,24000))
            self.assertEqual(wav.getnframes(),19200)
        self.assertFalse(self.plane._test_task.done())
        self.assertEqual((await self.device('speech',self.ack(state,'ended'))).status_code,409)
        for status in ('started','ended'):
            self.assertEqual((await self.device('speech',self.ack(state,status))).status_code,200)
        await self.plane._test_task
        self.assertEqual(self.plane.test['status'],'complete')
        self.assertIsNone(self.plane.speech)
        self.motion.assert_not_called()
        self.plane.audio.speak.assert_not_called()

    async def test_voice_test_requires_credentials_and_generates_only_the_fixed_test_line(self):
        response=await self.client.post('/api/plane/test',json={'kind':'voice'})
        self.assertEqual(response.status_code,409)
        self.plane.audio.elevenlabs='test';self.plane.audio.voice_id='voice'
        state=await self.start('voice')
        response=await self.device('audio',extra='&speech_id='+state['speech']['id'])
        self.assertEqual(response.content,b'fake-mp3')
        self.plane.audio.speak.assert_called_once_with(state['speech']['text'])
        self.assertIn('selected speaker',state['speech']['text'])
        self.motion.assert_not_called()

    async def test_stop_invalidates_pending_tts_and_browser_events(self):
        self.plane.audio.elevenlabs='test';self.plane.audio.voice_id='voice'
        state=await self.start('voice')
        entered,release=asyncio.Event(),asyncio.Event()
        async def slow(*args): entered.set();await release.wait();return b'late-mp3'
        with patch('robot.control_plane.asyncio.to_thread',side_effect=slow):
            pending=asyncio.create_task(self.device('audio',extra='&speech_id='+state['speech']['id']))
            await entered.wait()
            await self.client.post('/api/plane/stop')
            self.assertTrue(self.plane.busy)
            release.set()
            self.assertEqual((await pending).status_code,409)
        self.assertEqual((await self.device('speech',self.ack(state,'started'))).status_code,409)
        self.assertFalse((await self.device('state')).json()['running'])

    async def test_speaker_loss_or_focus_loss_stops_audio_test(self):
        state=await self.start()
        await self.device('fault',{})
        await self.plane._test_task
        self.assertEqual(self.plane.test['status'],'stopped')
        self.assertIsNone((await self.device('state')).json()['speech'])
        state=await self.start()
        self.guard.side_effect=HTTPException(409,'Focus lost')
        await self.plane._test_task
        self.assertEqual(self.plane.test['status'],'error')
        self.assertIsNone(self.plane.speech)

    async def test_device_credentials_cannot_start_tests_and_wrong_speech_id_cannot_play(self):
        # Tests are operator routes: actual app middleware protects them.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),base_url='http://localhost') as real:
            self.assertEqual((await real.post('/api/plane/test',headers=self.headers,json={'kind':'tone'})).status_code,403)
        await self.start()
        self.assertEqual((await self.device('audio',extra='&speech_id=not-current')).status_code,409)

    async def test_air_installation_uses_browser_output_and_exposes_matching_buttons(self):
        self.assertEqual(app.plane.speaker_output,'browser')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),base_url='http://localhost') as real:
            page=(await real.get('/plane')).text
            for label in ('GO2 AIR + AUDIO · V3','Use this computer’s speaker','Play speaker test tone'):
                self.assertIn(label,page)
            self.assertNotIn('Play Go2 test tone',page)
            self.assertNotIn('Sound output: Go2 built-in speaker',page)


class AudioOwnershipTests(unittest.TestCase):
    def test_audio_context_needs_current_focused_operator_but_not_connected_robot(self):
        owner=object()
        with patch.object(app,'controller',owner),patch.object(app,'controller_id','operator'),patch.object(app,'stop_epoch',42),patch.object(app,'last_input',time.monotonic()),patch.object(app,'armed',False),patch.object(app,'busy',False),patch.object(app.ai,'running',False),patch.object(app.ai,'_task',None),patch.object(app,'recovering',return_value=False),patch.object(app,'connected',return_value=False):
            context=app.acquire_audio_test('operator',42)
            app.check_audio_test(context)
            for identifier,epoch in (('someone_else',42),('operator',41)):
                with self.assertRaises(HTTPException):app.acquire_audio_test(identifier,epoch)
            with patch.object(app,'last_input',0),self.assertRaises(HTTPException):app.check_audio_test(context)
            with patch.object(app,'stop_epoch',43),self.assertRaises(HTTPException):app.check_audio_test(context)
