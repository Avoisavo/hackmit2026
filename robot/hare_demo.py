"""HARE's bounded lessons: five objects, Hello arithmetic, and staged care cues."""
import secrets
from fastapi import HTTPException
if __package__:
    from .demo_observer import camera_is_black
else:
    from demo_observer import camera_is_black

DEMOS = {
    'count_check': {'title': 'Count and Check', 'target': 5,
        'intro': 'HARE checks a real answer, not a tap on a screen.'},
    'run_play': {'title': 'Come Back and Count', 'target': 5,
        'intro': 'Watch what happens when the learner stalls.'},
    'soft_hands': {'title': 'Soft Hands', 'target': 0,
        'intro': 'HARE is a creature. The learner practises care on HARE.'},
    'close': {'title': 'Same lesson, new shape', 'target': 0,
        'intro': 'HARE is built with ADHD learners in mind. It adapts the mission, not the learner. It does not diagnose anything. We built HARE with Devin and Codex, with ElevenLabs and Deepgram for voice.'},
    'backup': {'title': 'It sees. It moves. It cares.', 'target': 0,
        'intro': 'It sees: checks real objects with a camera. It moves: teaches maths with Hello gestures. It cares: teaches soft hands, and never scolds.'},
}
NUMBERS = ('zero', 'one', 'two', 'three', 'four', 'five')
COUNT_PHASES = ('observing', 'waiting_blocks', 'return_objects')
ANSWER_PHASES = ('answer_two', 'answer_five')


class HareDemo:
    STALL_SECONDS = 12

    def __init__(self, plane, name, rehearsal=False, motion='screen', stall_seconds=12):
        self.p, self.name, self.info = plane, name, DEMOS[name]
        self.rehearsal, self.motion, self.stall_seconds = rehearsal, motion, stall_seconds
        self.source = 'none'
        self.fallback = False
        self.equation = ''
        self.effect = None
        self.hellos = 0
        self.hellos_left = 0
        self.hello_after = ''
        self.progress_at = plane.clock()
        self.observed_at = 0
        self.baseline = None
        self.adapted = False
        self.adaptation_source = ''
        self.touch_source = 'none'
        self.turn_result = None
        self.note = 'Go2 turn and Hello gestures.' if motion == 'robot_gestures' else 'Screen Hello gestures; no physical motion.'
        self.cue = self.info['intro']
        self.pending_count = None
        self.person_visible = None
        self.person_observed_at = 0
        self.last_transcript = ''

    @property
    def timeout_due(self):
        return self.name == 'run_play' and not self.adapted and self.p.phase in COUNT_PHASES[:2] and self.p.clock() - self.progress_at >= self.stall_seconds

    def context(self):
        return {'demo':self.name, 'phase':self.p.phase, 'after_speech':self.p._after_speech if self.p.speech else None,
            'target':self.p.target, 'observed':self.p.observed, 'hello_count':self.hellos,
            'current_line':self.p.message, 'last_transcript':self.last_transcript,
            'timeout_due':self.timeout_due, 'seconds_without_progress':round(max(0,self.p.clock()-self.progress_at),1),
            'touch_source':self.touch_source}

    def status(self):
        return {'name':self.name, 'title':self.info['title'], 'rehearsal':self.rehearsal,
            'evidence':self.source, 'fallback_used':self.fallback, 'equation':self.equation,
            'hellos':self.hellos, 'effect':self.effect, 'motion':self.motion,
            'note':self.note, 'presenter_cue':self.cue, 'adapted':self.adapted,
            'adaptation_source':self.adaptation_source, 'touch_source':self.touch_source,
            'turn':self.turn_result, 'stall_seconds':self.stall_seconds,
            'timeout_remaining':max(0,round(self.stall_seconds-(self.p.clock()-self.progress_at),1)) if self.name=='run_play' and not self.adapted else None}

    def say(self, text, after, face='Watching'):
        self.p.say(text, after, face)

    def begin(self):
        p = self.p
        if self.name in ('count_check','run_play'):
            self.say('Put five objects in front of me.', 'observing')
        elif self.name == 'soft_hands':
            p.phase, p.face = 'await_bump', 'Ready'
            p.message = 'Cover the Go2 camera briefly for the staged bump cue, or press B. No impact sensor is connected.'
        else:
            self.equation = 'Learner stalled → Hello counting\nSame lesson, new shape.' if self.name=='close' else 'It sees.\nIt moves.\nIt cares.'
            self.complete()

    def complete(self):
        self.p.running = False
        self.p.phase = 'complete'
        self.p.question_id = ''
        self.p.message = 'Demo complete.'
        if self.name == 'run_play':
            self.cue = 'The maths changed shape. Objects became Hello gestures.'
        elif self.name == 'soft_hands':
            self.cue = 'HARE shows the effect, then gives the learner a way to fix it at once.'

    def after_speech(self):
        p = self.p
        if p.phase in COUNT_PHASES:
            self.progress_at = p.clock()
            p._next_scan = 0
        if p.phase == 'hello_two':
            self.hellos = 0
            self.start_hellos(2,'answer_two')
        elif p.phase == 'hello_three_more':
            self.start_hellos(3,'answer_five')
        elif p.phase == 'next_hello':
            p.phase = 'gesturing'
        elif p.phase == 'empathy':
            self.say('Other people and animals feel pain too.', 'request_soft', 'Soft confused')
        elif p.phase == 'request_soft':
            self.say('Show me soft hands now.', 'await_gentle', 'Encourage')
        elif p.phase == 'complete':
            self.complete()
        if self.pending_count is not None and p.phase in COUNT_PHASES:
            count, source = self.pending_count
            self.pending_count = None
            # Queued presenter events are explicit; camera replies are never queued across phases.
            if source == 'presenter':
                self.count(count, source)

    def start_hellos(self, count, after):
        self.hellos_left, self.hello_after = count, after
        self.p.phase, self.p.face = 'gesturing', 'Go'

    def motion_guard(self, **kwargs):
        self.p.check(self.p.session_id)
        if not self.p.vision.camera_fresh():
            raise HTTPException(409, 'Camera stale; robot action cancelled')
        if hasattr(self.p.vision, 'get_frame') and camera_is_black(self.p.vision.get_frame()[0]) is not False:
            raise HTTPException(409, 'Camera covered or invalid; robot action cancelled')

    async def tick(self):
        p = self.p
        if p.speech:
            if self.rehearsal and p.clock()-p._speech_at >= min(5,max(1.5,len(p.message)/24)):
                p.speech_ended()
            return
        if p.phase == 'turning':
            if self.motion == 'robot_gestures':
                self.turn_result = await p.demo_turn(self.motion_guard)
                self.motion_guard()
                p.log('robot turn', self.turn_result['note'])
            else:
                self.turn_result = {'turned':False, 'note':'Screen rehearsal; no robot turn commanded'}
            self.say("Come back! Let's play a game together. Count my hellos!", 'hello_two', 'Go')
        elif p.phase == 'gesturing':
            if self.hellos_left:
                if self.motion == 'robot_gestures':
                    await p.gesture(self.motion_guard)
                    self.motion_guard()
                self.hellos += 1
                self.hellos_left -= 1
                self.effect = {'id':secrets.token_hex(6), 'kind':'wave'}
                self.equation = str(self.hellos)
                p.log('robot hello' if self.motion=='robot_gestures' else 'screen hello', f'Hello {self.hellos}; '+('command completed; verify physical gesture' if self.motion=='robot_gestures' else 'no physical motion'))
                self.say('Hello!', 'next_hello', 'Go')
            else:
                p.question_id = secrets.token_hex(12)
                if self.hello_after == 'answer_two':
                    self.say('I said hello twice. How many is that?', 'answer_two', 'Thinking')
                else:
                    self.equation = '2 + 3 = ?'
                    self.say('How many hellos altogether?', 'answer_five', 'Thinking')
        elif self.timeout_due:
            recent_absence = self.person_visible is False and p.clock()-self.person_observed_at <= 12
            self.adapt(f'No object or answer progress for {self.stall_seconds} seconds'+('; recent camera view contains no person' if recent_absence else '; learner leaving is a demo assumption'), 'camera_timeout' if recent_absence else 'timeout')

    def adapt(self, reason, source='presenter'):
        if self.name!='run_play' or self.adapted or self.p.phase not in COUNT_PHASES[:2]:
            raise HTTPException(409, 'Wait for the five-object mission before inviting the learner back')
        self.adapted, self.adaptation_source = True, source
        self.p.question_id = ''
        self.p.log('adaptation', reason)
        self.p.phase, self.p.face = 'turning', 'Go'
        self.p.message = 'Turning to invite the learner back.' if self.motion=='robot_gestures' else 'Inviting the learner back; screen mode.'

    def observe(self, state):
        obs = state.get('observation')
        if not state.get('observation_fresh') or not obs or not obs.get('stable'):
            self.note = 'Camera count uncertain. F applies the presenter override.'
            return
        self.count(obs.get('observed_count'),'camera')

    def count(self, count, source):
        p = self.p
        if type(count) is not int or not 0<=count<=20:
            raise HTTPException(400, 'Count must be a whole number from 0 to 20')
        if self.name not in ('count_check','run_play'):
            raise HTTPException(409, 'This demo is not counting objects')
        if p.phase=='speaking' and p._after_speech in COUNT_PHASES and source=='presenter':
            self.pending_count=(count,source); return
        if p.phase not in COUNT_PHASES:
            raise HTTPException(409, 'Finish the current step before checking objects')
        previous=p.observed
        if count!=previous:
            self.progress_at=p.clock()
        p.observed,self.source,self.observed_at=count,source,p.clock()
        self.fallback=self.fallback or source=='presenter'
        self.note='Presenter override; not camera verification.' if source=='presenter' else 'Two fresh Go2 views agree on the foreground object count.'
        self.equation=str(count)
        if count!=previous:
            p.log(source,f'{count} objects in front of HARE')
        if count==p.target:
            p.task_complete=source=='camera';p.question_id=''
            self.equation=f'{self.baseline} + {p.target-self.baseline} = {p.target}' if self.baseline is not None else str(p.target)
            self.say('Five objects! You did it!', 'complete', 'Celebrate')
        elif count>p.target:
            if count!=previous:
                self.say('We need five. Can you take some away?', 'waiting_blocks','Encourage')
        elif count>0 and count!=previous:
            self.baseline=count;p.question_id=secrets.token_hex(12)
            self.say(f'You have {NUMBERS[count]}. How many more do we need?', 'waiting_blocks','Thinking')
        elif p.phase=='observing':
            p.message='Waiting for five objects in front of HARE.'

    def answer(self,text,number):
        p=self.p
        self.last_transcript=text
        self.progress_at=p.clock()
        if p.phase in ANSWER_PHASES:
            expected=2 if p.phase=='answer_two' else 5
            if number==expected:
                p.answer_correct=True
                if expected==2:
                    self.equation='2 + 3 = ?'
                    self.say("Two! Two hellos means two. Let's add three more.",'hello_three_more','Celebrate')
                else:
                    self.equation='2 + 3 = 5';p.vision.clear_observation();p.observed=None
                    self.say("Five! Two plus three is five. Let's put five objects in front of me.",'return_objects','Celebrate')
            else:
                p.answer_correct=False
                self.say(f'Good try! I said hello {NUMBERS[expected]} times. How many is that?',p.phase,'Encourage')
        elif p.phase=='waiting_blocks':
            if p.observed is None or p.observed>=p.target or p.clock()-self.observed_at>20:
                raise HTTPException(409,'Check the objects again before answering')
            missing=p.target-p.observed;p.answer_correct=number==missing
            line=f'Yes. Add {NUMBERS[missing]} more objects.' if number==missing else f'We have {p.observed} and need five. How many more do we need?'
            self.say(line,'waiting_blocks','Encourage')
        else:
            raise HTTPException(409,'Wait for HARE to finish the current step')
        p.question_id=secrets.token_hex(12)

    def event(self,name,data):
        p=self.p
        if name=='count':
            self.count(data.get('count'),'presenter')
        elif name=='learner_left':
            self.adapt('Presenter cued learner walking away')
        elif name=='bump' and self.name=='soft_hands' and p.phase=='await_bump':
            self.touch_source='camera_black' if data.get('source')=='camera_black' else 'presenter'
            self.effect={'id':secrets.token_hex(6),'kind':'wobble'}
            p.log(self.touch_source,'Staged rough-touch cue; no force or impact measurement')
            self.say('Ouch, that was too hard. Softer, please.','empathy','Soft confused')
        elif name=='gentle' and self.name=='soft_hands' and p.phase=='await_gentle':
            p.log('presenter','Gentle-touch cue; no touch sensor reading')
            self.say('Perfect. Soft hands.','complete','Celebrate')
        else:
            raise HTTPException(409,'That cue does not match the current demo step')
