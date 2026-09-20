"""Presenter-assisted HARE demos: observed blocks, adaptive hop counting, and care.

A fallback is always recorded as presenter evidence, never as camera evidence.
Screen hops are available without hardware. Physical hop support is deliberately
absent until a repeatable in-place motion has been validated on this Go2.
"""
import secrets
from fastapi import HTTPException

DEMOS = {
    'count_check': {'title': 'Count and Check', 'target': 3, 'color': 'blue',
        'intro': 'HARE checks a real answer, not a tap on a screen.'},
    'run_play': {'title': 'Run, Play, Teach Again', 'target': 5, 'color': 'red',
        'intro': 'Watch what happens when the learner stalls.'},
    'soft_hands': {'title': 'Soft Hands', 'target': 0, 'color': '',
        'intro': 'HARE is a creature. The learner practises care on HARE.'},
    'close': {'title': 'Same lesson, new shape', 'target': 0, 'color': '',
        'intro': 'HARE is built with ADHD learners in mind. It adapts the mission, not the learner. It does not diagnose anything.'},
    'backup': {'title': 'It sees. It moves. It cares.', 'target': 0, 'color': '',
        'intro': 'It sees: checks a real answer with a camera. It moves: turns blocks into hops. It cares: teaches soft hands, and never scolds.'},
}
NUMBERS = ('zero', 'one', 'two', 'three', 'four', 'five')


class HareDemo:
    STALL_SECONDS = 10
    HOP_SECONDS = 1.1

    def __init__(self, plane, name, rehearsal=False):
        self.p = plane
        self.name = name
        self.info = DEMOS[name]
        self.rehearsal = rehearsal
        self.source = 'none'
        self.fallback = False
        self.equation = ''
        self.effect = None
        self.hops = 0
        self.hops_left = 0
        self.hop_after = ''
        self.next_hop = 0
        self.progress_at = plane.clock()
        self.observed_at = 0
        self.baseline = None
        self.adapted = False
        self.touch_source = 'presenter'
        self.note = 'Screen hops; physical hop-in-place is not configured.'
        self.cue = self.info['intro']
        self.pending_count = None

    def status(self):
        return {'name': self.name, 'title': self.info['title'], 'color': self.info['color'],
            'rehearsal': self.rehearsal, 'evidence': self.source, 'fallback_used': self.fallback,
            'equation': self.equation, 'hops': self.hops, 'effect': self.effect,
            'motion': 'screen', 'note': self.note, 'presenter_cue': self.cue,
            'adapted': self.adapted, 'touch_source': self.touch_source}

    def say(self, text, after, face='Watching'):
        self.p.say(text, after, face)

    def begin(self):
        p = self.p
        if self.name in ('count_check', 'run_play'):
            self.say(f"Put {NUMBERS[p.target]} {self.info['color']} blocks on the mat.", 'observing')
        elif self.name == 'soft_hands':
            p.phase, p.face = 'await_bump', 'Ready'
            p.message = 'Use your teammate. Press B to cue a hard bump; no force sensor is connected.'
        else:
            self.equation = ('Learner walked away → hop-counting\nSame lesson, new shape.'
                             if self.name == 'close' else 'It sees.\nIt moves.\nIt cares.')
            self.complete()

    def complete(self):
        self.p.running = False
        self.p.phase = 'complete'
        self.p.question_id = ''
        self.p.message = 'Demo complete.'
        if self.name == 'run_play':
            self.cue = 'The learner never escaped the maths. The maths changed shape. Blocks became hops.'
        elif self.name == 'soft_hands':
            self.cue = 'HARE shows the effect, then gives the learner a way to fix it at once.'

    def after_speech(self):
        p = self.p
        if p.phase in ('observing', 'return_blocks'):
            self.progress_at = p.clock()
            p._next_scan = 0
        if p.phase == 'celebrate_hop':
            self.start_hops(1, 'complete')
        elif p.phase == 'play_depart':
            self.start_hops(1, 'catch_me')
        elif p.phase == 'count_three':
            self.hops = 0
            self.start_hops(3, 'answer_three')
        elif p.phase == 'count_two_more':
            self.start_hops(2, 'answer_five')
        elif p.phase == 'empathy':
            self.say('Other people and animals feel pain too.', 'request_soft', 'Soft confused')
        elif p.phase == 'request_soft':
            self.say('Show me soft hands now.', 'await_gentle', 'Encourage')
        elif p.phase == 'complete':
            self.complete()
        if self.pending_count is not None and p.phase in ('observing', 'waiting_blocks', 'return_blocks'):
            count, source = self.pending_count
            self.pending_count = None
            if source == 'presenter':
                self.count(count, source)
            else:
                self.observe(p.vision.status())

    def start_hops(self, count, after):
        self.hops_left, self.hop_after = count, after
        self.next_hop = self.p.clock()
        self.p.phase, self.p.face = 'hopping', 'Go'

    def tick(self):
        p = self.p
        if p.speech:
            if self.rehearsal and p.clock() - p._speech_at >= min(5, max(1.5, len(p.message) / 24)):
                p.speech_ended()
            return
        if p.phase == 'hopping' and p.clock() >= self.next_hop:
            if self.hops_left:
                self.hops += 1
                self.hops_left -= 1
                self.effect = {'id': secrets.token_hex(6), 'kind': 'hop'}
                self.next_hop = p.clock() + self.HOP_SECONDS
                p.log('screen hop', f'Hop {self.hops}; no robot motion commanded')
            else:
                p.phase = self.hop_after
                if p.phase == 'complete':
                    self.complete()
                elif p.phase == 'catch_me':
                    self.say('Catch me!', 'catch_wait', 'Go')
                elif p.phase in ('answer_three', 'answer_five'):
                    p.question_id = secrets.token_hex(12)
                    p.message = 'How many hops?' if p.phase == 'answer_three' else 'How many hops altogether?'
                    self.equation = '3 + 2 = ?' if p.phase == 'answer_five' else 'How many hops?'
        elif p.phase == 'catch_wait' and p.clock() - p._speech_at >= 3:
            self.say('I hopped. Count my hops!', 'count_three', 'Thinking')
        elif self.name == 'run_play' and not self.adapted and p.phase in ('observing', 'waiting_blocks'):
            if p.clock() - self.progress_at >= self.STALL_SECONDS:
                self.adapt('No block-count progress for ten seconds')

    def adapt(self, reason):
        if self.name != 'run_play' or self.adapted or self.p.phase not in ('observing', 'waiting_blocks'):
            raise HTTPException(409, 'Wait for the red-block mission before cueing the learner leaving')
        self.adapted = True
        self.p.question_id = ''
        self.p.log('adaptation', reason)
        self.say("You need to move. Let's move together!", 'play_depart', 'Go')

    def observe(self, state):
        obs = state.get('observation')
        if not state.get('observation_fresh') or not obs or not obs.get('stable'):
            self.note = 'Camera count unavailable or uncertain. F uses the visible presenter fallback count.'
            return
        self.count(obs.get('observed_count'), 'camera')

    def count(self, count, source):
        p = self.p
        if type(count) is not int or not 0 <= count <= 20:
            raise HTTPException(400, 'Count must be a whole number from 0 to 20')
        if self.name not in ('count_check', 'run_play'):
            raise HTTPException(409, 'This demo is not counting blocks')
        if p.phase == 'speaking' and p._after_speech in ('observing', 'waiting_blocks', 'return_blocks'):
            self.pending_count = (count, source)
            return
        if p.phase not in ('observing', 'waiting_blocks', 'return_blocks'):
            raise HTTPException(409, 'Finish the current demo step before checking blocks')
        previous = p.observed
        if count != previous:
            self.progress_at = p.clock()
        p.observed, self.source, self.observed_at = count, source, p.clock()
        self.fallback = self.fallback or source == 'presenter'
        self.note = ('Presenter fallback; this is not camera verification.' if source == 'presenter'
                     else 'Two fresh camera views agree on the selected color and mat.')
        self.equation = str(count)
        p.log(source, f'{count} {self.info["color"]} blocks on the mat')
        if count == p.target:
            p.task_complete = source == 'camera'
            p.question_id = ''
            self.equation = f'{self.baseline} + {p.target - self.baseline} = {p.target}' if self.baseline is not None else str(p.target)
            self.say('You did it!', 'celebrate_hop' if self.name == 'count_check' else 'complete', 'Celebrate')
        elif count > p.target:
            if count != previous:
                self.say(f'We need {NUMBERS[p.target]}. Can you take some away?', 'waiting_blocks', 'Encourage')
        elif count > 0 and count != previous:
            self.baseline = count
            p.question_id = secrets.token_hex(12)
            self.say(f'You have {NUMBERS[count] if count < len(NUMBERS) else count}. How many more do we need?', 'waiting_blocks', 'Thinking')
        elif p.phase == 'observing':
            p.message = f'Waiting for {self.info["color"]} blocks on the mat.'

    def answer(self, text, number):
        p = self.p
        if p.phase in ('answer_three', 'answer_five'):
            expected = 3 if p.phase == 'answer_three' else 5
            if number == expected:
                p.answer_correct = True
                if expected == 3:
                    self.equation = '3 + 2 = ?'
                    self.say('Three! Now add two more.', 'count_two_more', 'Celebrate')
                else:
                    self.equation = '3 + 2 = 5'
                    p.vision.clear_observation()
                    p.observed = None
                    self.say("Five. Same as five red blocks. Let's go back.", 'return_blocks', 'Celebrate')
            else:
                self.say('Good try. How many hops did you count?', p.phase, 'Encourage')
        elif p.phase == 'waiting_blocks':
            if p.observed is None or p.observed >= p.target or p.clock() - self.observed_at > 20:
                raise HTTPException(409, 'Check the blocks again before answering')
            missing = p.target - p.observed
            p.answer_correct = number == missing
            line = (f'Yes. Add {NUMBERS[missing]} more {self.info["color"]} blocks to the mat.'
                    if number == missing else f'We have {p.observed} and need {p.target}. How many more do we need?')
            self.say(line, 'waiting_blocks', 'Encourage')
        else:
            raise HTTPException(409, 'Wait for HARE to finish the current step')
        p.question_id = secrets.token_hex(12)

    def event(self, name, data):
        p = self.p
        if name == 'count':
            self.count(data.get('count'), 'presenter')
        elif name == 'learner_left':
            self.adapt('Presenter cued learner walking away')
        elif name == 'bump' and self.name == 'soft_hands' and p.phase == 'await_bump':
            self.effect = {'id': secrets.token_hex(6), 'kind': 'wobble'}
            p.log('presenter', 'Hard-bump cue; no force sensor reading')
            self.say('Ouch, that was too hard. Softer, please.', 'empathy', 'Soft confused')
        elif name == 'gentle' and self.name == 'soft_hands' and p.phase == 'await_gentle':
            p.log('presenter', 'Gentle-touch cue; no touch sensor reading')
            self.say('Perfect. Soft hands.', 'complete', 'Celebrate')
        else:
            raise HTTPException(409, 'That cue does not match the current demo step')
