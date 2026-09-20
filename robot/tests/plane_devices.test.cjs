const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../plane_web/device.js'), 'utf8')
  .replace(/^import .*;\n/, '').replace('export class DeviceClient', 'class DeviceClient');

function client() {
  const messages = [], sources = [], requests = [], timers = new Map();
  let i = 0;
  const context = vm.createContext({
    crypto: {getRandomValues: array => array.fill(1)}, Uint8Array, URLSearchParams,
    document: {body: {dataset: {}}},
    fetch: async (url, options) => { requests.push({url, options}); return {ok: true}; },
    AbortSignal, setTimeout: fn => { timers.set(++i, fn); return i; }, clearTimeout: id => timers.delete(id),
  });
  vm.runInContext(source, context);
  const DeviceClient = vm.runInContext('DeviceClient', context);
  const device = new DeviceClient('speaker', 'role-secret', message => messages.push(message));
  device.active = true;
  device.state = {running: true, session_id: 'session-a', speech: {id: 'speech-a', text: 'Put three blocks'}};
  device.audioContext = {
    decodeAudioData: async () => ({}), close: async () => {},
    createBufferSource() {
      const source = {connect() {}, start() { this.started = true; }, stop() { this.stopped = true; }};
      sources.push(source); return source;
    },
  };
  const calls = [];
  device.request = async (path, payload) => {
    calls.push({path, payload});
    return path === 'audio' ? new ArrayBuffer(8) : path === 'state' ? device.state : {accepted: true};
  };
  return {device, messages, sources, requests, calls, timers};
}

test('speech playback acknowledges actual start and end, and STOP cannot generate ended', async () => {
  const ui = client();
  await ui.device.play(ui.device.state);
  assert.equal(ui.sources[0].started, true);
  assert.deepEqual(ui.calls.map(c => c.payload?.status).filter(Boolean), ['started']);
  ui.device.stop();
  assert.equal(ui.sources[0].stopped, true);
  assert.equal(ui.sources[0].onended, null);
  assert.equal(ui.calls.some(c => c.payload?.status === 'ended'), false);
});

test('late generated audio after STOP is discarded without decoding or starting playback', async () => {
  const ui = client(); let resolve;
  ui.device.request = () => new Promise(done => { resolve = done; });
  const pending = ui.device.play(ui.device.state);
  ui.device.stop(); resolve(new ArrayBuffer(8)); await pending;
  assert.equal(ui.sources.length, 0);
  assert.equal(ui.device.active, false);
});

test('STOP during audio decoding prevents the delayed decoded buffer from starting', async () => {
  const ui = client(); let resolve, entered;
  const decoding = new Promise(done => { entered = done; });
  ui.device.audioContext.decodeAudioData = () => { entered(); return new Promise(done => { resolve = done; }); };
  const pending = ui.device.play(ui.device.state);
  await decoding;
  ui.device.stop(); resolve({}); await pending;
  assert.equal(ui.sources.length, 0);
  assert.equal(ui.calls.some(c => c.payload?.status === 'started'), false);
});

test('polling the same speech ID cannot play it twice', async () => {
  const ui = client(); let plays = 0;
  ui.device.play = async () => { plays++; };
  await ui.device.poll(); await ui.device.poll();
  assert.equal(plays, 1);
  ui.device.state.speech = {id: 'speech-b', text: 'How many more?'};
  await ui.device.poll(); assert.equal(plays, 2);
});

test('a canceled speech snapshot stops current output immediately', async () => {
  const ui = client();
  await ui.device.play(ui.device.state);
  ui.device.state = {running: false, speech: null};
  await ui.device.poll();
  assert.equal(ui.sources[0].stopped, true);
  assert.equal(ui.device.playing, '');
});

test('device connection loss stops audio and leaves an error without automatic resumption', async () => {
  const ui = client();
  await ui.device.play(ui.device.state);
  ui.device.request = async () => { throw new Error('Network lost'); };
  await ui.device.poll();
  assert.equal(ui.device.active, false);
  assert.equal(ui.sources[0].stopped, true);
  assert.equal(ui.messages.at(-1), 'Network lost');
  assert.equal(ui.timers.size, 0);
});

test('microphone follows the server turn and stays paused while speech is pending', async () => {
  const ui = client(); ui.device.role = 'mic';
  const changed = [];
  ui.device.listener = {pause() { changed.push('pause'); }, resume() { changed.push('resume'); }};
  ui.device.state.listen = false; await ui.device.poll();
  ui.device.state.listen = true; await ui.device.poll();
  assert.deepEqual(changed, ['pause', 'resume']);
});

test('device requests put scoped credentials in headers, never in request URLs', async () => {
  const ui = client();
  const original = Object.getPrototypeOf(ui.device).request;
  const response = {ok: true, json: async () => ({})};
  // Use audio path so the fixture only needs arrayBuffer, assigned via the context fetch replacement below.
  ui.device.request = original;
  try { await ui.device.request('state'); } catch {} // fixture's successful response has no body decoder
  assert.equal(ui.requests.length, 1);
  assert.doesNotMatch(ui.requests[0].url, /role-secret/);
  assert.equal(ui.requests[0].options.headers['X-Device-Key'], 'role-secret');
  assert.equal(ui.requests[0].options.headers['X-Control-Token'], undefined);
});
