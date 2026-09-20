"""HB's existing /health + /emote API, reached over its tunnel or private LAN."""
import asyncio
import contextlib
import ipaddress
import time
from urllib.parse import urlsplit

import requests

if __package__:
    from .control_plane import EMOTES
else:
    from control_plane import EMOTES


def board_origins(settings):
    candidates = [settings.get('BOARD_URL'), 'http://127.0.0.1:8080', 'http://[::1]:8080', settings.get('NEXT_PUBLIC_ROBOT_FACE_URL')]
    result = []
    for value in candidates:
        if not value:
            continue
        url = urlsplit(value)
        try:
            host_ok = url.hostname == 'localhost' or ipaddress.ip_address(url.hostname).is_private
            port = url.port
        except ValueError:
            host_ok = False
        if url.scheme not in ('http', 'https') or not host_ok or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
            continue
        origin = value.rstrip('/')
        if origin not in result:
            result.append(origin)
    return result


class FaceBridge:
    def __init__(self, settings, *, clock=time.monotonic):
        self.origins = board_origins(settings)
        self.clock = clock
        self.face = 'Ready'
        self.source = 'lesson'
        self.revision = 0
        self.endpoint = ''
        self.online = False
        self.screens = 0
        self.version = ''
        self.error = 'Checking HB face board'
        self.sent_revision = -1
        self.last_health = 0
        self._task = None
        self._wake = asyncio.Event()
        self.request = self._request

    @staticmethod
    def _request(method, url, payload=None):
        # LAN/tunnel traffic must stay local even if the shell has a web proxy.
        with requests.Session() as session:
            session.trust_env = False
            response = session.request(method, url, json=payload, timeout=(.6, 1.5), allow_redirects=False)
            response.raise_for_status()
            return response.json()

    def status(self):
        return {'online': self.online, 'screens': self.screens, 'endpoint': self.endpoint,
                'version': self.version, 'error': self.error, 'expression': self.face,
                'source': self.source, 'delivered': self.online and self.screens > 0 and self.sent_revision == self.revision}

    def select(self, face, source='lesson'):
        if face not in EMOTES:
            raise ValueError('Unknown HB expression')
        if (face, source) != (self.face, self.source):
            self.face, self.source = face, source
            self.revision += 1
            self._wake.set()

    async def sync(self, force=False):
        if force or self.clock() - self.last_health >= 4 or not self.last_health:
            self.last_health = self.clock()
            was_ready = self.online and self.screens > 0
            candidates = [self.endpoint] if self.online else self.origins
            self.online = False; self.screens = 0
            for endpoint in candidates:
                try:
                    data = await asyncio.to_thread(self.request, 'GET', endpoint+'/health')
                    if data.get('ok') is not True or type(data.get('faces')) is not int or not str(data.get('version', '')).startswith(('rabbit-', 'twinkle-')):
                        continue
                    self.online = True; self.endpoint = endpoint
                    self.screens = max(0, data['faces']); self.version = data['version']
                    self.error = '' if self.screens else 'HB server reachable; no face screen connected'
                    if not was_ready and self.screens:
                        self.sent_revision = -1
                    break
                except (requests.RequestException, ValueError, TypeError, AttributeError):
                    continue
            if not self.online:
                self.error = 'HB board unreachable; check reverse tunnel or BOARD_URL. Local preview remains available.'
        if not self.online or not self.screens or self.sent_revision == self.revision:
            return
        face, revision = self.face, self.revision
        try:
            data = await asyncio.to_thread(self.request, 'POST', self.endpoint+'/emote', {'name':face, 'hold':0})
            if data.get('ok') is not True or data.get('name') != face or not data.get('faces'):
                raise ValueError('Face not delivered')
            self.sent_revision = revision
            self.error = ''
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            self.online = False
            self.error = 'HB expression delivery failed; local preview remains available'

    def start(self):
        if not self._task:
            self._task = asyncio.create_task(self.run())

    async def run(self):
        while True:
            self._wake.clear()
            await self.sync()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=.3)
            except asyncio.TimeoutError:
                pass

    async def close(self):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
