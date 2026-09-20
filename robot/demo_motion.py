"""Heading feedback for one bounded half-turn; no translation or person tracking."""
import asyncio
import math
import time
from fastapi import HTTPException


class HeadingTracker:
    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.reset()

    def reset(self):
        self.yaw = None
        self.at = 0

    def update(self, message):
        try:
            rpy = message['data']['imu_state']['rpy']
            yaw = rpy[2]
            if type(yaw) not in (int, float) or not math.isfinite(yaw) or abs(yaw) > 2*math.pi:
                return
            self.yaw, self.at = float(yaw), self.clock()
        except (KeyError, TypeError, IndexError):
            return

    def sample(self):
        return self.yaw, self.at

    def status(self):
        age = self.clock()-self.at
        return {'ready':self.yaw is not None and 0<=age<1, 'age_seconds':round(age,2) if self.yaw is not None else None}


async def half_turn(read_heading, command, check, *, clock=time.monotonic, sleep=asyncio.sleep):
    started = clock()
    previous = None
    turned = 0.0
    try:
        while True:
            check()
            now = clock()
            yaw, at = read_heading()
            if yaw is None or not 0<=now-at<1:
                raise HTTPException(409,'Heading feedback unavailable; turn stopped')
            if previous is not None:
                delta = math.atan2(math.sin(yaw-previous), math.cos(yaw-previous))
                if abs(delta)>.7:
                    raise HTTPException(409,'Heading changed unexpectedly; turn stopped')
                turned += delta
                if turned < -.35:
                    raise HTTPException(409,'Turn direction disagrees with heading feedback; stopped')
            previous = yaw
            if turned >= math.pi-.10:
                return {'turned':True,'degrees':round(math.degrees(turned),1),
                    'note':'Half-turn completed from heading feedback; verify physical orientation'}
            if now-started >= 20:
                raise HTTPException(409,'Turn time limit reached; robot stopped')
            command(0,0,.25)
            await sleep(.05)
    finally:
        command(0,0,0)
