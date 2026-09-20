import math
import unittest
from unittest.mock import Mock
from fastapi import HTTPException
from robot.demo_motion import HeadingTracker, half_turn


class HeadingTests(unittest.TestCase):
    def test_valid_imu_values_age_and_reset_are_explicit(self):
        now=[10]
        tracker=HeadingTracker(clock=lambda:now[0])
        for bad in (True,float('nan'),'1',8,None):tracker.update({'data':{'imu_state':{'rpy':[0,0,bad]}}})
        self.assertFalse(tracker.status()['ready'])
        tracker.update({'data':{'imu_state':{'rpy':[0,0,2.9]}}})
        self.assertTrue(tracker.status()['ready']);now[0]+=1
        self.assertFalse(tracker.status()['ready']);tracker.reset();self.assertIsNone(tracker.yaw)


class TurnTests(unittest.IsolatedAsyncioTestCase):
    async def test_half_turn_handles_wraparound_and_always_finishes_with_zero(self):
        now=[10];yaw=[2.9];commands=[]
        async def sleep(seconds):
            now[0]+=seconds;yaw[0]=math.atan2(math.sin(yaw[0]+.10),math.cos(yaw[0]+.10))
        result=await half_turn(lambda:(yaw[0],now[0]),lambda *args:commands.append(args),lambda:None,clock=lambda:now[0],sleep=sleep)
        self.assertTrue(result['turned']);self.assertTrue(174<=result['degrees']<=185)
        self.assertTrue(all(x==0 and y==0 for x,y,_ in commands));self.assertEqual(commands[-1],(0,0,0))

    async def test_stale_heading_and_focus_stop_cannot_leave_velocity_active(self):
        for stopped in (False,True):
            commands=[]
            check=Mock(side_effect=HTTPException(409,'STOP') if stopped else None)
            with self.assertRaises(HTTPException):
                await half_turn(lambda:(0,1),lambda *args:commands.append(args),check,clock=lambda:10)
            self.assertEqual(commands,[(0,0,0)])

    async def test_frozen_robot_cannot_turn_forever(self):
        now=[10];commands=[]
        async def sleep(seconds):now[0]+=1
        with self.assertRaisesRegex(HTTPException,'time limit'):
            await half_turn(lambda:(0,now[0]),lambda *args:commands.append(args),lambda:None,clock=lambda:now[0],sleep=sleep)
        self.assertEqual(commands[-1],(0,0,0));self.assertLessEqual(now[0],30)
