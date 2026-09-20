import asyncio
import contextlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI, HTTPException

from robot.hare_plane import HareControlPlane
from robot.ai_agent import TOOLS, validate_call, AgentError
from robot import app


class HareTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 100
        self.vision = SimpleNamespace(_api_key='', busy=False, camera_fresh=Mock(return_value=True),
            clear_observation=Mock(), stop_scanning=Mock(), scan=AsyncMock(), status=Mock())
        self.acquire = Mock(return_value='robot-context')
        self.audio_acquire = Mock(return_value='audio-context')
        self.check = Mock()
        self.motion = AsyncMock(return_value={'turned':True,'degrees':180,'note':'Turn completed'})
        self.plane = HareControlPlane(vision=self.vision, acquire=self.acquire, check_context=self.check,
            audio_acquire=self.audio_acquire, audio_check=self.check,
            stop_robot=lambda reason: self.plane.cancel(reason), gesture=AsyncMock(), finish=Mock(),
            demo_turn=self.motion, clock=lambda: self.now)
        self.plane.DEVICE_TIMEOUT = 1000
        self.plane.audio.elevenlabs = 'test'; self.plane.audio.voice_id = 'voice'
        self.plane.audio.deepgram = 'test'; self.plane.audio.speak = Mock(return_value=b'fake-mp3')
        server=FastAPI(); server.include_router(self.plane.router)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=server),base_url='http://localhost')
        self.keys={}
        for role in ('speaker','mic'):
            self.keys[role]=(await self.client.post('/api/plane/pair',json={'role':role})).json()['key']
            await self.device(role,'state')
        self.event_number=0

    async def asyncTearDown(self):
        await self.plane.close(); await self.client.aclose()

    async def device(self,role,path,data=None,extra=''):
        return await self.client.request('GET' if data is None else 'POST','/session/'+path+'?client_id=hare_'+role+'_123'+extra,
            headers={'X-Device-Key':self.keys[role]},json=data)

    async def start(self,name='count_check',background=False,**extra):
        response=await self.client.post('/api/plane/start',json={'demo':name,'control_id':'owner','control_epoch':1,**extra})
        self.assertEqual(response.status_code,200,response.text)
        if not background:
            self.plane._task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.plane._task
        return self.plane.demo

    async def speech(self):
        p=self.plane
        self.assertIsNotNone(p.speech)
        payload={'session_id':p.session_id,'speech_id':p.speech['id']}
        for status in ('started','ended'):
            response=await self.device('speaker','speech',{**payload,'status':status})
            self.assertEqual(response.status_code,200,response.text)

    async def event(self,event,**extra):
        self.event_number+=1
        return await self.client.post('/api/plane/event',json={'event':event,'event_id':f'event_{self.event_number:08d}',
            'session_id':self.plane.session_id,**extra})

    async def answer(self,text,**extra):
        self.event_number+=1
        return await self.device('mic','transcript',{'text':text,'session_id':self.plane.session_id,
            'question_id':self.plane.question_id,'event_id':f'answer_{self.event_number:08d}',**extra})

    async def hellos(self, number):
        for _ in range(number):
            await self.plane.demo.tick()
            self.assertEqual(self.plane.speech['text'], 'Hello!')
            await self.speech()
        await self.plane.demo.tick()
        await self.speech()

    def camera(self,count):
        self.plane.demo.observe({'observation_fresh':True,'observation':{'stable':True,'observed_count':count}})

    async def test_count_check_requires_five_physical_objects(self):
        await self.start()
        self.assertEqual(self.vision.target_object,'small movable objects grouped in the foreground')
        self.assertEqual(self.plane.speech['text'],'Put five objects in front of me.')
        await self.speech(); self.camera(4)
        self.assertEqual(self.plane.speech['text'],'You have four. How many more do we need?')
        await self.speech()
        self.assertEqual((await self.answer('one')).status_code,200)
        self.assertFalse(self.plane.task_complete)
        await self.speech(); self.camera(5)
        self.assertTrue(self.plane.task_complete)
        self.assertEqual(self.plane.demo.equation,'4 + 1 = 5')
        await self.speech()
        self.assertEqual(self.plane.phase,'complete')
        self.motion.assert_not_awaited()

    async def test_fallback_is_explicit_and_never_claims_camera_confirmation(self):
        await self.start(); await self.speech()
        self.assertEqual((await self.event('count',count=4)).status_code,200)
        await self.speech(); await self.event('count',count=5)
        self.assertFalse(self.plane.task_complete)
        self.assertTrue(self.plane.demo.fallback)
        self.assertEqual(self.plane.demo.source,'presenter')
        self.assertEqual(self.plane.demo.equation,'4 + 1 = 5')

    async def test_run_play_turns_then_counts_two_and_three_hellos_and_returns_to_objects(self):
        await self.start('run_play', motion='robot_gestures'); await self.speech()
        self.assertEqual(self.vision.target_object, 'small movable objects grouped in the foreground')
        await self.event('learner_left')
        self.assertEqual(self.plane.phase, 'turning')
        await self.plane.demo.tick()
        self.motion.assert_awaited_once()
        self.assertIn('Come back!', self.plane.speech['text'])
        await self.speech(); await self.hellos(2)
        self.assertEqual(self.plane.phase, 'answer_two')
        self.assertEqual((await self.answer('three')).status_code, 200)
        self.assertFalse(self.plane.answer_correct)
        await self.speech()
        self.assertEqual((await self.answer('two')).status_code, 200)
        await self.speech(); await self.hellos(3)
        self.assertEqual(self.plane.phase, 'answer_five')
        self.assertEqual(self.plane.demo.hellos, 5)
        self.assertEqual(self.plane.gesture.await_count, 5)
        self.assertEqual((await self.answer('five')).status_code, 200)
        self.assertIn('Two plus three is five', self.plane.speech['text'])
        self.assertFalse(self.plane.task_complete)
        await self.speech(); self.camera(5)
        self.assertTrue(self.plane.task_complete)
        await self.speech()
        self.assertEqual(self.plane.phase, 'complete')
        self.assertIn('Hello gestures', self.plane.demo.cue)

    async def test_stall_timer_adapts_once_without_inferring_emotions(self):
        await self.start('run_play'); await self.speech(); self.camera(0)
        self.now+=12; await self.plane.demo.tick()
        self.assertTrue(self.plane.demo.adapted)
        self.assertIn('No object or answer progress',self.plane.events[-1]['text'])
        self.assertEqual((await self.event('learner_left')).status_code,409)

    async def test_soft_hands_presenter_cues_are_ordered_and_deduplicated(self):
        await self.start('soft_hands')
        self.assertEqual((await self.event('gentle')).status_code,409)
        payload={'event':'bump','session_id':self.plane.session_id,'event_id':'bump_123456'}
        self.assertEqual((await self.client.post('/api/plane/event',json=payload)).status_code,200)
        speech_id=self.plane.speech['id']
        self.assertEqual((await self.client.post('/api/plane/event',json=payload)).status_code,200)
        self.assertEqual(self.plane.speech['id'],speech_id)
        self.assertEqual(self.plane.demo.effect['kind'],'wobble')
        await self.speech(); self.assertIn('Other people and animals',self.plane.speech['text'])
        await self.speech(); self.assertEqual(self.plane.speech['text'],'Show me soft hands now.')
        await self.speech(); await self.event('gentle')
        self.assertEqual(self.plane.speech['text'],'Perfect. Soft hands.')
        await self.speech(); self.assertFalse(self.plane.running)
        self.assertEqual((await self.client.post('/api/plane/event',json=payload)).status_code,409)

    async def test_turn_requires_fresh_camera_and_stop_prevents_invitation(self):
        self.vision.camera_fresh.return_value = False
        response = await self.client.post('/api/plane/start', json={'demo':'run_play','motion':'robot_gestures'})
        self.assertEqual(response.status_code,409)
        self.acquire.assert_not_called()
        self.vision.camera_fresh.return_value = True
        await self.start('run_play', motion='robot_gestures')
        self.assertTrue(self.plane.requires_robot)
        await self.speech(); await self.event('learner_left')
        entered,release = asyncio.Event(),asyncio.Event()
        async def turn(check):
            entered.set(); await release.wait(); check()
            return {'turned':True,'note':'done'}
        self.motion.side_effect = turn
        pending = asyncio.create_task(self.plane.demo.tick())
        await entered.wait(); self.plane.cancel('STOP'); release.set()
        with self.assertRaises(HTTPException): await pending
        self.assertIsNone(self.plane.speech)
        self.assertEqual(self.plane.demo.hellos,0)
        self.plane.gesture.assert_not_awaited()

    async def test_rehearsal_needs_no_provider_camera_or_motion(self):
        self.plane.audio.elevenlabs=''; self.plane.devices.clear()
        self.vision.camera_fresh.return_value=False
        await self.start('soft_hands',rehearsal=True)
        await self.event('bump')
        for _ in range(3): self.now+=6; await self.plane.demo.tick()
        self.assertEqual(self.plane.phase,'await_gentle')
        await self.event('gentle'); self.now+=6; await self.plane.demo.tick()
        self.assertFalse(self.plane.running)
        self.acquire.assert_not_called(); self.motion.assert_not_awaited()
        self.plane.audio.speak.assert_not_called()

    async def test_camera_error_does_not_prevent_presenter_fallback(self):
        self.vision._api_key='fake'
        self.vision.scan.side_effect=HTTPException(502,'Camera failed')
        await self.start(background=True); await self.speech()
        await asyncio.sleep(.16)
        self.assertTrue(self.plane.running)
        self.assertEqual((await self.event('count',count=4)).status_code,200)
        self.assertEqual(self.plane.demo.source,'presenter')

    async def test_camera_reply_started_before_fallback_cannot_replace_it(self):
        self.vision._api_key='fake'
        entered,release=asyncio.Event(),asyncio.Event()
        async def scan():
            entered.set();await release.wait()
            return {'observation_fresh':True,'observation':{'stable':True,'observed_count':5}}
        self.vision.scan.side_effect=scan
        await self.start(background=True);await self.speech();await entered.wait()
        await self.event('count',count=0)
        release.set();await asyncio.sleep(.12)
        self.assertEqual(self.plane.observed,0)
        self.assertFalse(self.plane.task_complete)
        self.assertEqual(self.plane.demo.source,'presenter')

    async def test_finished_old_scan_is_discarded_before_new_object_mission(self):
        old=asyncio.create_task(asyncio.sleep(0,result={'observation_fresh':True,'observation':{'stable':True,'observed_count':5}}))
        await old
        self.plane._demo_scan_task=old
        await self.start('run_play')
        self.assertIsNone(self.plane._demo_scan_task)
        self.assertIsNone(self.plane.observed)
        self.assertEqual(self.vision.target_object,'small movable objects grouped in the foreground')

    async def test_finished_demo_does_not_disable_later_microphone_test(self):
        await self.start('close')
        self.assertFalse(self.plane.running)
        response=await self.client.post('/api/plane/test',json={'kind':'microphone','control_id':'owner','control_epoch':1})
        self.assertEqual(response.status_code,200)
        self.assertTrue((await self.device('mic','state')).json()['listen'])
        self.plane.cancel('test complete')

    async def test_old_question_and_after_stop_events_are_rejected(self):
        await self.start(); await self.speech(); self.camera(4); await self.speech()
        self.assertEqual((await self.answer('one',question_id='old')).status_code,409)
        self.assertEqual((await self.answer('please stop')).status_code,200)
        self.assertFalse(self.plane.running)
        self.assertEqual((await self.event('count',count=5)).status_code,409)

    async def test_speak_tool_waits_for_actual_playback_and_listen_returns_transcript(self):
        args={'text':'Hello, I am HARE.','reason':'Introduce the counting game'}
        task=asyncio.create_task(self.plane.call_audio('speak',args,self.check))
        await asyncio.sleep(0)
        state=(await self.device('speaker','state')).json()
        self.assertEqual(state['speech']['text'],args['text'])
        self.assertFalse(task.done())
        payload={'session_id':state['session_id'],'speech_id':state['speech']['id']}
        for status in ('started','ended'): await self.device('speaker','speech',{**payload,'status':status})
        self.assertTrue((await task)['played'])
        task=asyncio.create_task(self.plane.call_audio('listen',{'seconds':10,'reason':'Hear one answer'},self.check))
        await asyncio.sleep(0)
        state=(await self.device('mic','state')).json()
        self.assertTrue(state['listen'])
        await self.device('mic','transcript',{'session_id':state['session_id'],'text':'three'})
        self.assertEqual((await task)['transcript'],'three')
        self.acquire.assert_not_called()

    async def test_listen_timeout_and_spoken_stop_cannot_resume_ai(self):
        args={'seconds':1,'reason':'Hear answer'}
        task=asyncio.create_task(self.plane.call_audio('listen',args,self.check)); await asyncio.sleep(0)
        self.now+=2
        result=await task
        self.assertTrue(result['timed_out']); self.assertFalse(result['heard'])
        task=asyncio.create_task(self.plane.call_audio('listen',args,self.check)); await asyncio.sleep(0)
        state=(await self.device('mic','state')).json()
        await self.device('mic','transcript',{'session_id':state['session_id'],'text':'please stop'})
        with self.assertRaises(HTTPException): await task
        self.assertIsNone(self.plane.speech)

    async def test_audio_dispatch_is_idempotent_and_stop_discards_late_results(self):
        data={'name':'speak','arguments':{'text':'Hello','reason':'Test speech'},'run_id':'audio_call_123456789','control_id':'owner','control_epoch':1}
        self.assertEqual((await self.client.post('/api/plane/call',json=data)).status_code,200)
        duplicate=await self.client.post('/api/plane/call',json=data)
        self.assertTrue(duplicate.json()['duplicate'])
        await asyncio.sleep(0)
        state=(await self.device('speaker','state')).json()
        await self.client.post('/api/plane/stop')
        await self.plane._io_task
        self.assertEqual(self.plane.io_result['status'],'stopped')
        reply=await self.device('speaker','speech',{'session_id':state['session_id'],'speech_id':state['speech']['id'],'status':'started'})
        self.assertEqual(reply.status_code,409)

    async def test_ai_observation_confidence_and_two_counts_gate_completion(self):
        from robot.tests.test_demo_observer import observation
        await self.start(); await self.speech()
        self.plane.apply_observation({**observation(confidence='medium'),'captured_at':self.now})
        self.assertFalse(self.plane.task_complete)
        self.plane.apply_observation({**observation(first_count=4),'captured_at':self.now})
        self.assertIsNone(self.plane.observed)
        self.plane.apply_observation({**observation(),'captured_at':self.now})
        self.assertTrue(self.plane.task_complete)
        self.assertEqual(self.plane.demo.source,'camera')

    async def test_camera_black_cue_runs_the_soft_hands_story_without_presenter_button(self):
        from robot.tests.test_demo_observer import jpeg
        await self.start('soft_hands')
        for color,at in [('white',100),('black',100.1),('black',100.4),('black',100.7)]:
            self.now=at
            self.vision.get_frame=lambda color=color,at=at:(jpeg(color),at,1)
            self.plane.check_black_cue()
        self.assertEqual(self.plane.demo.touch_source,'camera_black')
        self.assertTrue(self.plane.speech['text'].startswith('Ouch'))
        self.assertEqual(self.plane.observer_status['stage'],'camera_covered')
        await self.speech();await self.speech();await self.speech()
        self.assertEqual(self.plane.phase,'await_gentle')
        await self.event('gentle');await self.speech()
        self.assertFalse(self.plane.running)

    async def test_presenter_cannot_label_a_button_event_as_camera_evidence(self):
        await self.start('soft_hands')
        await self.event('bump',source='camera_black')
        self.assertEqual(self.plane.demo.touch_source,'presenter')

    async def test_openai_faces_respect_manual_override_until_auto_is_resumed(self):
        from robot.tests.test_demo_observer import observation
        await self.start('soft_hands')
        result={**observation(stage='waiting',face='Thinking'),'captured_at':self.now}
        self.plane.apply_observation(result)
        self.assertEqual((self.plane.face,self.plane.face_source),('Thinking','OpenAI'))
        response=await self.client.post('/api/plane/face',json={'name':'Rest'})
        self.assertEqual(response.status_code,200)
        self.plane.apply_observation(result)
        self.assertEqual((self.plane.face,self.plane.face_source),('Rest','presenter'))
        await self.client.post('/api/plane/face',json={'auto':True})
        self.plane.apply_observation(result)
        self.assertEqual(self.plane.face,'Thinking')

    async def test_timeout_does_not_require_a_camera_count_and_is_labelled_as_assumption(self):
        demo=await self.start('run_play',stall_seconds=7);await self.speech()
        self.now+=6.9;await demo.tick();self.assertFalse(demo.adapted)
        self.now+=.2;await demo.tick()
        self.assertEqual(demo.adaptation_source,'timeout')
        self.assertIn('demo assumption',self.plane.events[-1]['text'])

    async def test_late_openai_result_cannot_replace_presenter_fallback_or_face_after_stop(self):
        from robot.tests.test_demo_observer import observation
        entered,release=asyncio.Event(),asyncio.Event()
        async def scan(context):
            entered.set();await release.wait()
            return {**observation(face='Celebrate'),'captured_at':self.now}
        self.plane.observer=SimpleNamespace(scan=scan)
        self.vision._api_key='fake'
        await self.start(background=True);await self.speech();await entered.wait()
        await self.event('count',count=0)
        self.plane.cancel('STOP')
        release.set();await asyncio.sleep(.12)
        self.assertEqual(self.plane.observed,0)
        self.assertFalse(self.plane.task_complete)
        self.assertEqual(self.plane.face,'Ready')



class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_tools_include_speaker_and_microphone_and_dispatch_to_audio(self):
        self.assertTrue({'speak','listen'} <= {tool['name'] for tool in TOOLS})
        with self.assertRaises(AgentError): validate_call('speak',{'text':'x'*401,'reason':'test'})
        with self.assertRaises(AgentError): validate_call('listen',{'seconds':21,'reason':'test'})
        with patch.object(app,'disarm'),patch.object(app.plane,'call_audio',new_callable=AsyncMock,return_value={'heard':True,'transcript':'three'}) as call:
            result=await app.execute_ai('listen',{'seconds':10,'reason':'Count hops'},None,Mock())
            self.assertEqual(result['transcript'],'three')
            call.assert_awaited_once()

    async def test_jump_uses_existing_tested_action_without_automatic_rearm(self):
        with patch.object(app,'run_command',new_callable=AsyncMock,return_value={'status_code':0,'remaining_seconds':4}) as command,patch.object(app,'ai_wait',new_callable=AsyncMock):
            check=Mock();await app.demo_jump(check)
            command.assert_awaited_once_with('front_jump',automatic_recovery=False,interrupt_ai=False,guard=check)
        with patch.object(app,'run_command',new_callable=AsyncMock,return_value={'status_code':3202}),self.assertRaises(HTTPException):
            await app.demo_jump(Mock())

    async def test_half_turn_uses_heading_controller_and_disarms_after_failure(self):
        async def fail(read, command, check):
            command(0,0,.25)
            raise HTTPException(409,'Heading lost')
        with patch.object(app,'action_lock',asyncio.Lock()), patch.object(app,'stop'), \
             patch.object(app,'prepare_stance',new_callable=AsyncMock), \
             patch.object(app.heading,'status',return_value={'ready':True}), \
             patch.object(app,'half_turn',side_effect=fail) as turn, \
             patch.object(app,'robot',None), patch.object(app,'armed',False), patch.object(app,'busy',False):
            with self.assertRaises(HTTPException): await app.demo_turn(Mock())
            turn.assert_awaited_once()
            self.assertFalse(app.armed);self.assertFalse(app.busy)
            self.assertEqual(app.desired,(0,0,0))

    async def test_hare_and_audio_routes_require_operator_credentials(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),base_url='http://localhost') as client:
            for path in ('/api/plane/event','/api/plane/call'):
                self.assertEqual((await client.post(path,json={})).status_code,403)
            page=await client.get('/plane')
            for marker in ('Count and Check','Soft Hands','Closing slide','Hardware backup','Call speak tool'):
                self.assertIn(marker,page.text)
            tools=(await client.get('/api/ai/tools',headers={'X-Control-Token':app.TOKEN})).json()
            self.assertEqual(tools['audio_dispatch']['path'],'/api/plane/call')
