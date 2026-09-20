"""HARE's bounded lessons: five objects, Hello arithmetic, and staged care cues."""
import re
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

    def __init__(self, plane, name, rehearsal=False, motion='screen', stall_seconds=12, jump_clearance=False):
        self.p, self.name, self.info = plane, name, DEMOS[name]
        self.session_id = plane.session_id
        self.rehearsal, self.motion, self.stall_seconds = rehearsal, motion, stall_seconds
        self.jump_clearance = jump_clearance and name == 'run_play' and motion == 'robot_gestures'
        self._actions, self._after_actions = [], ''
        self.action, self.action_history = '', []
        self.action_reason = ''
        self.pending_gentle = False
        self.cue_feedback = None
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
        self.note = 'Movement follows the lesson: count with Hello, celebrate completion with Content, thank gentle care with Heart.' if motion == 'robot_gestures' else 'Screen rehearsal; no physical motion.'
        self.cue = self.info['intro']
        self.pending_count = None
        self.person_visible = None
        self.person_observed_at = 0
        self.last_transcript = ''
        self.apology_received = False
        if name == 'soft_hands':
            self.note = 'Cover the camera, say sorry, then show soft hands. G confirms the gentle touch.'

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
            'apology_received':self.apology_received,
            'action':self.action, 'actions_completed':list(self.action_history),
            'movement_reason':self.movement_reason(), 'cues':self.presenter_cues(),
            'next_step':self.next_step(), 'cue_feedback':self.cue_feedback,
            'jump_enabled':self.jump_clearance,
            'turn':self.turn_result, 'stall_seconds':self.stall_seconds,
            'timeout_remaining':max(0,round(self.stall_seconds-(self.p.clock()-self.progress_at),1)) if self.name=='run_play' and not self.adapted else None}

    def movement_reason(self):
        if not self.p.running:
            return ''
        if self.p.phase == 'turning':
            return 'Invite the learner back after the inactivity or presenter cue.'
        if self.p.phase == 'gesturing':
            return 'Count two Hello gestures, then three more: 2 + 3 = 5.'
        return self.action_reason if self._actions or self.action else ''

    def next_step(self):
        p = self.p
        if not p.running:
            return 'Demo complete. Choose another demo.' if p.phase == 'complete' else 'Choose a demo to begin.'
        if self.pending_gentle:
            return 'Gentle touch recorded. HARE will respond after finishing the soft-hands prompt.'
        if p.phase in ('demo_action', 'turning', 'gesturing'):
            return 'Wait for the movement to finish. ' + self.movement_reason()
        if p.speech:
            if p._after_speech == 'await_gentle':
                return 'Show gentle touch. G records it now; HARE responds after this sentence.'
            if p._after_speech == 'await_apology':
                return 'When HARE finishes speaking, say “sorry, HARE” or press “I apologized”.'
            return 'Wait for HARE to finish speaking. The next available cue will light up.'
        if p.phase == 'await_bump':
            return 'Show a clear camera view, then cover it briefly for the bump cue, or press B.'
        if p.phase == 'await_apology':
            return 'Say “sorry, HARE” or press “I apologized”. Then HARE will ask for soft hands.'
        if p.phase == 'await_gentle':
            return 'Show gentle touch, then press G to confirm it.'
        if p.phase in ANSWER_PHASES:
            return 'Answer how many Hellos: two first, then five altogether.'
        if p.phase in COUNT_PHASES:
            return 'Place five objects; F supplies the fallback count.' + (' L cues the learner walking away.' if self.name == 'run_play' and not self.adapted else '')
        return 'Follow HARE’s spoken prompt.'

    def presenter_cues(self):
        p = self.p
        after = p._after_speech if p.speech else None
        counting = self.name in ('count_check', 'run_play')
        choices = {
            'count': (counting and (p.phase in COUNT_PHASES or after in COUNT_PHASES), 'Apply the fallback object count.' if not p.speech else 'Queue the count until the current sentence finishes.'),
            'learner_left': (self.name == 'run_play' and not self.adapted and p.phase in COUNT_PHASES[:2], 'Invite the learner back and begin Hello counting.'),
            'bump': (self.name == 'soft_hands' and p.phase == 'await_bump', 'Trigger the staged bump response.'),
            'gentle': (self.name == 'soft_hands' and not self.pending_gentle and (p.phase == 'await_gentle' or after == 'await_gentle'), 'Confirm gentle touch.' if not p.speech else 'Record gentle touch; respond after HARE finishes the prompt.'),
        }
        return {name: {'enabled': bool(p.running and allowed), 'reason': reason if p.running and allowed else self.next_step()}
                for name, (allowed, reason) in choices.items()}

    def presenter_event(self, name, data):
        cues = self.presenter_cues()
        if not isinstance(name, str) or name not in cues:
            raise HTTPException(400, 'Choose count, learner_left, bump or gentle')
        cue = cues[name]
        status, reason = 'ignored', cue['reason']
        if cue['enabled']:
            queued = bool(self.p.speech)
            if name == 'gentle' and queued:
                self.pending_gentle = True
            else:
                self.event(name, data)
            status = 'queued' if queued else 'applied'
        self.cue_feedback = {'event': name, 'status': status, 'reason': reason, 'phase': self.p.phase,
                             'speech_id': self.p.speech['id'] if self.p.speech else None}
        return status

    def say(self, text, after, face='Watching', actions=(), action_reason=''):
        if actions and self.motion == 'robot_gestures':
            self._actions, self._after_actions = list(actions), after
            self.action_reason = action_reason
            after = 'demo_action'
        self.p.say(text, after, face)

    def begin(self):
        p = self.p
        if self.name in ('count_check','run_play'):
            self.say("Let's play a counting game! Can you put five objects in front of me?", 'observing')
        elif self.name == 'soft_hands':
            p.phase, p.face = 'await_bump', 'Ready'
            p.message = 'Ready for Soft Hands. Cover the camera briefly or press B for the staged bump cue.'
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
            self.say('People and animals need gentle care too.', 'request_apology', 'Soft confused')
        elif p.phase == 'request_apology':
            self.say('Can you say, sorry HARE? Then we can try again together.', 'await_apology', 'Encourage')
        elif p.phase == 'await_apology':
            p.question_id = secrets.token_hex(12)
        elif p.phase == 'request_soft':
            p.question_id = ''
            self.say('Ready for gentle paws? Show me your soft hands.', 'await_gentle', 'Encourage')
        elif p.phase == 'complete':
            self.complete()
        if self.pending_gentle and p.phase == 'await_gentle':
            self.pending_gentle = False
            self.presenter_event('gentle', {})
        if self.pending_count is not None and p.phase in COUNT_PHASES:
            count, source = self.pending_count
            self.pending_count = None
            # Queued presenter events are explicit; camera replies are never queued across phases.
            if source == 'presenter':
                self.presenter_event('count', {'count': count})

    def start_hellos(self, count, after):
        self.hellos_left, self.hello_after = count, after
        self.p.phase, self.p.face = 'gesturing', 'Go'

    def motion_guard(self, **kwargs):
        if self.p.demo is not self:
            raise HTTPException(409, 'Demo changed; robot action cancelled')
        self.p.check(self.session_id)
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
        if p.phase == 'demo_action':
            self.motion_guard()
            self.action = self._actions.pop(0)
            try:
                await p.demo_gesture(self.action, self.motion_guard)
                self.motion_guard()
                self.action_history.append(self.action)
                p.log('robot gesture', self.action + ' command completed; verify physical gesture')
            finally:
                self.action = ''
            if not self._actions:
                p.phase = self._after_actions
                self._after_actions = ''
                self.after_speech()
        elif p.phase == 'turning':
            if self.motion == 'robot_gestures':
                self.turn_result = await p.demo_turn(self.motion_guard)
                self.motion_guard()
                p.log('robot turn', self.turn_result['note'])
            else:
                self.turn_result = {'turned':False, 'note':'Screen rehearsal; no robot turn commanded'}
            self.say("Game switch! Come back! Let's count my silly hellos together!", 'hello_two', 'Go')
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
                    self.say('Your turn, counting buddy! How many hellos did you count?', 'answer_two', 'Thinking')
                else:
                    self.equation = '2 + 3 = ?'
                    self.say('Two hellos, then three more! How many altogether?', 'answer_five', 'Thinking')
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
            self.say('Five objects! Woohoo! Mission complete. We did it together!', 'complete', 'Celebrate', actions=('content',), action_reason='Celebrate the completed five-object mission once.')
        elif count>p.target:
            if count!=previous:
                self.say("What a collection! Let's keep five. Can you move the extras aside?", 'waiting_blocks','Encourage')
        elif count>0 and count!=previous:
            self.baseline=count;p.question_id=secrets.token_hex(12)
            self.say(f"I spy {NUMBERS[count]}! We're aiming for five. How many more do we need?", 'waiting_blocks','Thinking')
        elif p.phase=='observing':
            p.message='Waiting for five objects in front of HARE.'

    def answer(self,text,number):
        p=self.p
        self.last_transcript=text
        self.progress_at=p.clock()
        if self.name == 'soft_hands' and p.phase == 'await_apology':
            # Accept ordinary spoken apologies without letting unrelated or
            # negated uses of "sorry" skip this step. No maths grading here.
            apology = re.match(r"^\s*(?:(?:okay|ok|yes)[,!.]?\s+)?(?:i(?:['’]m| am)\s+)?(?:(?:so|really|very)\s+)?sorry\b", text, re.I)
            if apology:
                self.apology_received = True
                self.say("Thank you for saying sorry! That was kind. We're a team!", 'request_soft', 'Celebrate')
            else:
                self.say("Let's try these words together: sorry, HARE.", 'await_apology', 'Encourage')
        elif p.phase in ANSWER_PHASES:
            expected=2 if p.phase=='answer_two' else 5
            if number==expected:
                p.answer_correct=True
                if expected==2:
                    self.equation='2 + 3 = ?'
                    self.say("Two! You got it! Two hellos means two. Ready for three more?",'hello_three_more','Celebrate')
                else:
                    self.equation='2 + 3 = 5';p.vision.clear_observation();p.observed=None
                    line = "Five! Woohoo! Two plus three is five. "
                    if self.jump_clearance:
                        line += "Give me room for one forward celebration jump! Then let's try our five-object mission again!"
                    else:
                        line += "Let's try our five-object mission again!"
                    self.say(line,'return_objects','Celebrate',actions=('front_jump',) if self.jump_clearance else (), action_reason='Celebrate the correct total after five counted Hellos; forward jump enabled by presenter.')
            else:
                p.answer_correct=False
                self.say(f"Let's work it out together. I said hello {NUMBERS[expected]} times. What number is that?",p.phase,'Encourage')
        elif p.phase=='waiting_blocks':
            if p.observed is None or p.observed>=p.target or p.clock()-self.observed_at>20:
                raise HTTPException(409,'Check the objects again before answering')
            missing=p.target-p.observed;p.answer_correct=number==missing
            line=f"Yes, {NUMBERS[missing]} more! Let's add {'it' if missing == 1 else 'them'} and see!" if number==missing else f"Let's count together. We have {p.observed} and need five. How many more do we need?"
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
            self.say("Ouch! A little softer, please. Let's practise gentle hands together.",'empathy','Soft confused')
        elif name=='gentle' and self.name=='soft_hands' and p.phase=='await_gentle':
            p.log('presenter','Gentle-touch cue; no touch sensor reading')
            line = 'Lovely soft hands! Thank you for being gentle with me.'
            if self.motion == 'robot_gestures':
                line += " Step back and I'll send you a heart!"
            self.say(line,'complete','Celebrate',actions=('heart',), action_reason='Thank the learner after the apology and confirmed gentle touch.')
        else:
            raise HTTPException(409,self.next_step())
