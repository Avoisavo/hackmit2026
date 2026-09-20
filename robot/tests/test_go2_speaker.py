import asyncio
import io
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from fastapi import HTTPException
from robot.go2_speaker import Go2Speaker, SpeakerTrack, decode_audio, test_tone, RATE


class SpeakerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sender = SimpleNamespace(replaceTrack=Mock())
        self.robot = SimpleNamespace(pc=SimpleNamespace(getTransceivers=lambda: [
            SimpleNamespace(kind="audio", currentDirection="sendrecv", sender=self.sender)]))
        self.link = True
        self.speaker = Go2Speaker(lambda: self.robot, lambda: self.link)
        self.speaker.attach(self.robot)

    async def asyncTearDown(self):
        self.speaker.detach()

    async def test_reuses_existing_sender_and_never_opens_a_second_connection(self):
        self.sender.replaceTrack.assert_called_once_with(self.speaker.track)
        self.assertTrue(self.speaker.ready())
        self.assertFalse(self.speaker.status()["audibility_verified"])
        self.robot = object()
        self.assertFalse(self.speaker.ready())

    async def test_stop_clears_queued_audio_and_next_frame_is_silence(self):
        track = self.speaker.track
        track.enqueue(test_tone())
        first = await track.recv()
        self.assertTrue(np.any(first.to_ndarray()))
        self.speaker.stop()
        frame = await track.recv()
        self.assertFalse(np.any(frame.to_ndarray()))
        self.assertEqual(frame.pts - first.pts, 960)
        self.assertTrue(track.drained.is_set())

    async def test_audio_drains_before_reporting_sent(self):
        task = asyncio.create_task(self.speaker.play(None, lambda: None, tone=True))
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        while self.speaker.track.queue:
            await self.speaker.track.recv()
        result = await task
        self.assertTrue(result["sent"])
        self.assertFalse(result["audibility_verified"])
        self.assertFalse(self.speaker.playing)

    async def test_stop_during_decode_cannot_enqueue_late_audio(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def decode(*args):
            entered.set(); await release.wait(); return test_tone()
        with patch('robot.go2_speaker.asyncio.to_thread', side_effect=decode):
            task = asyncio.create_task(self.speaker.play(b'audio', lambda: None))
            await entered.wait()
            self.speaker.stop(); release.set()
            with self.assertRaises(HTTPException): await task
        self.assertFalse(self.speaker.track.queue)
        self.assertFalse(self.speaker.playing)

    async def test_lost_link_interrupts_playback_and_reconnect_has_no_audio(self):
        task = asyncio.create_task(self.speaker.play(None, lambda: None, tone=True))
        await asyncio.sleep(0)
        self.link = False
        with self.assertRaises(HTTPException): await task
        self.assertFalse(self.speaker.track.queue)
        self.link = True
        self.speaker.attach(self.robot)
        self.assertFalse(self.speaker.track.queue)

    async def test_second_speech_is_rejected_while_first_is_playing(self):
        task = asyncio.create_task(self.speaker.play(None, lambda: None, tone=True))
        await asyncio.sleep(0)
        with self.assertRaises(HTTPException):
            await self.speaker.play(None, lambda: None, tone=True)
        self.speaker.stop()
        with self.assertRaises(HTTPException): await task

    async def test_negotiation_without_audio_send_support_fails_explicitly(self):
        self.robot.pc.getTransceivers = lambda: [SimpleNamespace(kind='audio', currentDirection='recvonly')]
        with self.assertRaises(RuntimeError): self.speaker.attach(self.robot)
        self.assertFalse(self.speaker.ready())


class DecodeTests(unittest.TestCase):
    def test_decodes_resamples_and_bounds_duration_without_external_codec(self):
        source = io.BytesIO()
        with wave.open(source, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
            wav.writeframes(np.full(2205, 1000, dtype='<i2').tobytes())
        pcm = decode_audio(source.getvalue())
        self.assertEqual(len(pcm), 4800)
        self.assertLessEqual(np.max(pcm), 660)
        with self.assertRaises(Exception): decode_audio(b'invalid mp3')
