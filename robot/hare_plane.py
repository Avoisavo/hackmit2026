"""HARE demo orchestration and scoped speech/listening tools on one control plane."""
import asyncio
import re
import secrets
from fastapi import HTTPException, Request

if __package__:
    from .control_plane import ControlPlane, body, number_answer, EMOTES
    from .demo_observer import BlackCameraCue, VisionError
    from .hare_demo import HareDemo, DEMOS, COUNT_PHASES, ANSWER_PHASES
    from .ai_agent import validate_call, AgentError
else:
    from control_plane import ControlPlane, body, number_answer, EMOTES
    from demo_observer import BlackCameraCue, VisionError
    from hare_demo import HareDemo, DEMOS, COUNT_PHASES, ANSWER_PHASES
    from ai_agent import validate_call, AgentError

AUDIO_TOOLS = ('speak', 'listen')


class HareControlPlane(ControlPlane):
    def __init__(self, *, demo_turn=None, demo_gesture=None, observer=None, face_bridge=None, **kwargs):
        self.face_bridge = face_bridge
        self.face_mode, self.face_source = 'auto', 'lesson'
        super().__init__(**kwargs)
        self.demo = None
        self.demo_turn, self.observer = demo_turn, observer
        self.demo_gesture = demo_gesture
        self.black_cue = BlackCameraCue()
        self.observer_status = {'status':'idle', 'stage':'waiting', 'reason':'Start a demo to observe the camera'}
        self._demo_scan_signature = None
        self.message = 'Choose Demo 1, 2 or 3. Audio and camera prepare automatically.'
        self._io = None
        self._io_task = None
        self._demo_scan_task = None
        self._demo_revision = 0
        self.io_result = {'status': 'idle', 'run_id': '', 'result': None}
        self._io_seen = []
        self.router.add_api_route('/api/plane/event', self.event_api, methods=['POST'])
        self.router.add_api_route('/api/plane/call', self.audio_call_api, methods=['POST'])

    @property
    def face(self):
        return self._face_value

    @face.setter
    def face(self, value):
        if getattr(self, 'face_mode', 'auto') != 'manual':
            self.select_face(value, 'lesson')

    def select_face(self, value, source):
        self._face_value, self.face_source = value, source
        if self.face_bridge:
            self.face_bridge.select(value, source)

    async def face_api(self, request: Request):
        data = await body(request)
        if data.get('auto') is True:
            self.face_mode = 'auto'
            self.select_face('Ready' if not self.running else 'Watching', 'lesson')
            self._next_scan = 0
        elif data.get('name') in EMOTES:
            self.face_mode = 'manual'
            self.select_face(data['name'], 'presenter')
        else:
            raise HTTPException(400, 'Choose one of the eight HB expressions or auto=true')
        self._demo_revision += 1
        return self.status()

    @property
    def busy(self):
        return super().busy or bool(self._io) or any(task and not task.done() for task in (self._io_task, self._demo_scan_task))

    @property
    def requires_robot(self):
        return self.running and (self.demo is None or self.demo.motion == 'robot_gestures')

    @property
    def requires_camera(self):
        return self.running and self.demo is None

    def status(self):
        return {**super().status(), 'demo': self.demo.status() if self.demo else None,
                'audio_tool': dict(self.io_result), 'observer':dict(self.observer_status),
                'face_mode':self.face_mode, 'face_source':self.face_source,
                'face_board':self.face_bridge.status() if self.face_bridge else None}

    def cancel(self, reason='Activity stopped'):
        super().cancel(reason)
        if self.demo:
            self.demo.pending_gentle = False
            self.demo.pending_count = None
            self.demo.cue_feedback = None
        if self._io:
            self._io['cancelled'] = True

    def check(self, session_id, *, decision=False):
        if not self.demo:
            return super().check(session_id, decision=decision)
        if not self.running or session_id != self.session_id:
            raise HTTPException(409, 'Demo stopped or replaced')
        if self.demo.motion == 'robot_gestures':
            self.check_context(self._context)
        else:
            self.audio_check(self._context)
        if not self.demo.rehearsal and not self.speaker_ready():
            raise HTTPException(409, 'Speaker disconnected; demo stopped')
        if self.clock() >= self._deadline:
            raise HTTPException(409, 'Demo time limit reached')

    def speech_ended(self):
        if not self.demo:
            return super().speech_ended()
        self.speech = None
        self.phase = self._after_speech
        self.demo.after_speech()

    async def device_state(self, request: Request):
        state = await super().device_state(request)
        if self.demo:
            state['demo'] = self.demo.status()
            if self.running:
                state['listen'] = not self.speech and self.phase in ('waiting_blocks', 'await_apology', *ANSWER_PHASES)
            if self.running and self.demo.rehearsal:
                state['speech'] = None
        return state

    def discard_finished_scan(self):
        if self._demo_scan_task and self._demo_scan_task.done():
            try:
                self._demo_scan_task.result()
            except (Exception, asyncio.CancelledError):
                pass
            self._demo_scan_task = None

    async def start_api(self, request: Request):
        # Starlette caches request.body(), so the legacy handler can parse it too.
        await request.body()
        data = await body(request)
        if 'demo' not in data:
            if not self.running and not self.busy:
                self.demo = None
                self.discard_finished_scan()
            return await super().start_api(request)
        if self.running or self.busy:
            raise HTTPException(409, 'Stop the current activity and wait for pending work')
        name, rehearsal = data.get('demo'), data.get('rehearsal', False)
        motion = data.get('motion', 'screen')
        if not isinstance(name, str) or name not in DEMOS or type(rehearsal) is not bool or motion not in ('screen', 'robot_gestures'):
            raise HTTPException(400, 'Choose a HARE demo and valid rehearsal/motion settings')
        if rehearsal and motion != 'screen':
            raise HTTPException(400, 'Caption rehearsal cannot command robot motion')
        if name in ('close', 'backup'):
            motion = 'screen'
        if motion == 'robot_gestures' and (not self.demo_gesture or not self.vision.camera_fresh() or (name == 'run_play' and not self.demo_turn)):
            raise HTTPException(409, 'Connect Go2 and wait for a fresh camera before demo gestures')
        jump_clearance = data.get('jump_clearance', False)
        if type(jump_clearance) is not bool:
            raise HTTPException(400, 'Forward jump clearance must be true or false')
        if not rehearsal and name not in ('close', 'backup') and (not self.speaker_ready() or not self.audio.elevenlabs or not self.audio.voice_id):
            raise HTTPException(409, 'Enable the speaker and configure ElevenLabs, or select caption rehearsal')
        stall_seconds = data.get('stall_seconds', 12)
        if type(stall_seconds) is not int or not 5 <= stall_seconds <= 120:
            raise HTTPException(400, 'Inactivity timeout must be 5–120 seconds')
        self.discard_finished_scan()
        self._demo_revision += 1
        context = (self.acquire if motion == 'robot_gestures' else self.audio_acquire)(data.get('control_id'), data.get('control_epoch'))
        self.vision.stop_scanning()
        self.vision.clear_observation()
        self.target = DEMOS[name]['target']
        self.vision.target_count = max(1, self.target)
        self.vision.target_object = 'small movable objects grouped in the foreground'
        self.vision.round_id = secrets.token_hex(8)
        self._context = context
        self.session_id = secrets.token_hex(16)
        self.events.clear(); self.seen_events.clear()
        self.running = True
        self.observed = None
        self.question_id = ''
        self.speech = None
        self.task_complete = self.answer_correct = False
        self._gesture_task = None
        self._wave = False
        self._require_mic = False
        self._next_scan = 0
        self._pending_observation = None
        self._deadline = self.clock() + self.SESSION_SECONDS
        self.face_mode = 'auto'
        self.black_cue = BlackCameraCue()
        self.observer_status = {'status':'waiting', 'stage':'waiting', 'reason':'Waiting for fresh Go2 camera frames'}
        self.demo = HareDemo(self, name, rehearsal, motion, stall_seconds=stall_seconds, jump_clearance=jump_clearance)
        self.demo.begin()
        self._task = asyncio.create_task(self.run(self.session_id))
        return self.status()

    def scan_signature(self):
        return (self.session_id, self.phase, self.question_id, self.speech['id'] if self.speech else None, self._demo_revision)

    def apply_observation(self, result):
        demo = self.demo
        self.observer_status = {'status':'observed', 'stage':result['stage'], 'reason':result['reason'],
            'confidence':result['confidence'], 'face':result['face']}
        demo.person_visible = result['person_visible']
        demo.person_observed_at = result['captured_at']
        if self.face_mode == 'auto' and result['confidence'] in ('medium', 'high'):
            self.select_face(result['face'], 'OpenAI')
        if result['confidence'] != 'high':
            return
        if self.phase in COUNT_PHASES and demo.name in ('count_check', 'run_play'):
            stable = result['scene_clear'] and result['first_count'] is not None and result['first_count'] == result['second_count']
            if stable:
                demo.count(result['second_count'], 'camera')
            else:
                demo.note = 'OpenAI count uncertain; keep objects visible or use F.'
        # A timeout is explicit demo policy, not a claim about a child's feelings.
        if demo.timeout_due and result['stage'] == 'learner_away' and result['person_visible'] is False:
            demo.adapt('Inactivity timeout and a clear camera view with no person', 'camera_timeout')

    def check_black_cue(self):
        if self.demo.name != 'soft_hands' or self.demo.rehearsal or self.phase != 'await_bump':
            return
        if not hasattr(self.vision, 'get_frame'):
            return
        frame, at, session = self.vision.get_frame()
        if self.black_cue.update(frame, at, session, fresh=self.vision.camera_fresh()):
            self.demo.event('bump', {'source':'camera_black'})
            self._demo_revision += 1
            self.observer_status = {'status':'camera cue', 'stage':'camera_covered',
                'reason':'Clear camera followed by sustained black frames; staged bump cue, not an impact measurement'}

    async def run(self, session_id):
        if not self.demo:
            return await super().run(session_id)
        try:
            while self.running and self.session_id == session_id:
                self.check(session_id)
                if self.speech and self.clock() - self._speech_at >= self.SPEECH_TIMEOUT:
                    raise HTTPException(409, 'Speech playback timed out')
                self.check_black_cue()
                if self._demo_scan_task and self._demo_scan_task.done():
                    try:
                        result = self._demo_scan_task.result()
                        self.check(session_id)
                        if self.scan_signature() == self._demo_scan_signature:
                            if self.observer:
                                self.apply_observation(result)
                            else:
                                self.demo.observe(result)
                    except (HTTPException, VisionError):
                        self.observer_status = {'status':'unavailable', 'stage':'uncertain', 'reason':'Camera AI check failed; manual overrides remain available'}
                        self.demo.note = 'Camera check failed. F applies the presenter count override.'
                    finally:
                        self._demo_scan_task = None
                        self._next_scan = self.clock() + 2
                await self.demo.tick()
                if self.running and self.phase not in ('turning', 'gesturing', 'demo_action') and not self._demo_scan_task and self.clock() >= self._next_scan:
                    if not self.demo.rehearsal and self.vision._api_key and self.vision.camera_fresh():
                        self._demo_scan_signature = self.scan_signature()
                        if self.observer:
                            self._demo_scan_task = asyncio.create_task(self.observer.scan(self.demo.context()))
                        elif self.phase in COUNT_PHASES:
                            self._demo_scan_task = asyncio.create_task(self.vision.scan())
                        self._next_scan = self.clock() + 2
                    else:
                        self.observer_status = {'status':'waiting', 'stage':'uncertain', 'reason':'Camera or OpenAI unavailable; presenter overrides still work'}
                        self._next_scan = self.clock() + 2
                await asyncio.sleep(0.05)
        except Exception as exc:
            if self.running and self.session_id == session_id:
                self.stop_robot(str(exc.detail) if isinstance(exc, HTTPException) else 'Demo stopped after an interrupted operation')
        finally:
            if self.demo and self.demo.motion == 'robot_gestures' and self.phase == 'complete' and self.session_id == session_id:
                self.finish(self._context)

    def answer(self, data):
        if not self.demo:
            return super().answer(data)
        self.validate_event(data)
        event_id = data.get('event_id')
        if event_id in self.seen_events:
            return
        text = data.get('text')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 300 or not text.isprintable():
            raise HTTPException(400, 'Enter a short answer')
        if re.fullmatch(r'\s*(stop|stop please|please stop|goodbye|bye|take a break)[.!?]*\s*', text, re.I):
            self.stop_robot('Learner requested a stop')
            return
        if not self.question_id or data.get('question_id') != self.question_id:
            raise HTTPException(409, 'This answer belongs to an old question')
        self.demo.answer(text, number_answer(text))
        self._demo_revision += 1
        self.seen_events.append(event_id)
        self.log('learner', text)

    def validate_event(self, data):
        if not self.running or data.get('session_id') != self.session_id:
            raise HTTPException(409, 'Demo stopped or replaced')
        if not isinstance(data.get('event_id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', data['event_id']):
            raise HTTPException(400, 'Provide a unique event ID')
        self.check(self.session_id)

    async def event_api(self, request: Request):
        data = await body(request)
        if not self.demo:
            raise HTTPException(409, 'Start a HARE demo first')
        self.validate_event(data)
        if data['event_id'] not in self.seen_events:
            outcome = self.demo.presenter_event(data.get('event'), {key:value for key,value in data.items() if key != 'source'})
            if outcome != 'ignored':
                self._demo_revision += 1
            self.seen_events.append(data['event_id'])
        return self.status()

    async def audio_call_api(self, request: Request):
        data = await body(request)
        name, args, run_id = data.get('name'), data.get('arguments'), data.get('run_id')
        if name not in AUDIO_TOOLS or not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', run_id):
            raise HTTPException(400, 'Choose speak/listen and a unique run_id of 16–80 characters')
        try:
            validate_call(name, args)
        except AgentError as exc:
            raise HTTPException(400, str(exc)) from None
        if run_id in self._io_seen:
            return {**self.status(), 'duplicate': True, 'requested_run_id': run_id}
        if self.running or self.busy:
            raise HTTPException(409, 'An activity or audio tool is already active')
        context = self.audio_acquire(data.get('control_id'), data.get('control_epoch'))
        self._io_seen.append(run_id); self._io_seen = self._io_seen[-64:]
        self.io_result = {'status': 'running', 'run_id': run_id, 'result': None}
        async def execute():
            try:
                result = await self.call_audio(name, args, lambda **kw: self.audio_check(context))
                self.io_result.update(status='complete', result=result)
            except Exception as exc:
                self.io_result.update(status='stopped', result=str(exc.detail) if isinstance(exc, HTTPException) else 'Audio tool stopped')
        self._io_task = asyncio.create_task(execute())
        return self.status()

    async def call_audio(self, name, args, check):
        validate_call(name, args)
        if name not in AUDIO_TOOLS or self.running or self._io or self._test_id:
            raise HTTPException(409, 'Audio is owned by another operation')
        check()
        role = 'speaker' if name == 'speak' else 'mic'
        if not self.online(role):
            raise HTTPException(409, f'Enable the {role} device first')
        if name == 'speak' and not (self.audio.elevenlabs and self.audio.voice_id):
            raise HTTPException(409, 'Configure ElevenLabs first')
        if name == 'listen' and not self.audio.deepgram:
            raise HTTPException(409, 'Configure Deepgram first')
        self.demo = None
        operation = self._io = {'cancelled': False}
        test_id = self._test_id = secrets.token_hex(16)
        self.test = {'kind': 'voice' if name == 'speak' else 'microphone', 'status': 'running', 'message': 'AI '+name}
        deadline = self.clock() + (self.SPEECH_TIMEOUT if name == 'speak' else args['seconds'])
        self._test_playback = asyncio.Event()
        if name == 'speak':
            self.speech = {'id': secrets.token_hex(12), 'kind': 'voice', 'status': 'queued', 'text': args['text']}
        else:
            self._mic_until = deadline
        try:
            while True:
                check()
                if operation['cancelled'] or self._test_id != test_id:
                    raise HTTPException(409, 'Audio tool stopped')
                if not self.online(role):
                    raise HTTPException(409, f'{role.capitalize()} disconnected')
                if name == 'speak' and self._test_playback.is_set():
                    result = {'played': True, 'audibility_verified': False, 'text': args['text']}
                    break
                if name == 'listen' and self.test.get('transcript'):
                    result = {'heard': True, 'transcript': self.test['transcript']}
                    break
                if self.clock() >= deadline:
                    if name == 'speak':
                        raise HTTPException(409, 'Speech playback timed out')
                    result = {'heard': False, 'transcript': '', 'timed_out': True}
                    break
                await asyncio.sleep(0.05)
            self.test.update(status='complete', message='AI audio tool completed')
            return result
        finally:
            self._test_id, self._mic_until = '', 0
            self.speech = None
            self._io = None
            if self.test['status'] == 'running':
                self.test.update(status='stopped', message='AI audio tool stopped')

    async def transcript_api(self, request: Request):
        if self._io and self.mic_testing():
            await request.body()
            data = await body(request)
            if re.fullmatch(r'\s*(stop|stop please|please stop|goodbye|bye|take a break)[.!?]*\s*', str(data.get('text', '')), re.I):
                self.device(request, 'mic')
                if data.get('session_id') != self._test_id:
                    raise HTTPException(409, 'Listening window changed')
                self.stop_robot('Learner requested a stop')
                return {'accepted': True}
        return await super().transcript_api(request)

    async def close(self):
        await super().close()
        for task in (self._io_task, self._demo_scan_task):
            if task:
                try:
                    await task
                except (HTTPException, asyncio.CancelledError):
                    pass
