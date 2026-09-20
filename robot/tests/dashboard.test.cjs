const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8')
  .match(/<script>([\s\S]*?)<\/script>/)[1];

function dashboard() {
  const elements = new Map();
  const listeners = {};
  const intervals = new Map();
  const timers = new Map();
  const sockets = [];
  let timerId = 0;
  const sent = [];
  const requests = [];
  const state = {connected: true, armed: false, recovering: true,
    mode: 'normal', stance: 'after_trick', error: ''};
  const ui = {state, sent, requests, timers, sockets};
  const response = body => ({ok: true, status: 200, json: async () => body});
  ui.statusResponse = async () => response({...state});
  ui.commandResponse = async url => response(url.startsWith('/api/action/')
    ? {status_code: 0, command: 'Hello', after: 'RecoveryStand, BalanceStand, movement enabled'}
    : {armed: url === '/api/arm'});
  const document = {
    hidden: false,
    hasFocus: () => true,
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, {
        textContent: '', checked: selector === '#controlBoxes', classList: {toggle() {}},
      });
      return elements.get(selector);
    },
    querySelectorAll: () => [],
    addEventListener: (name, fn) => { listeners[name] = fn; },
  };
  class WebSocket {
    static OPEN = 1;
    readyState = 1;
    constructor() { sockets.push(this); }
    send(message) { sent.push(JSON.parse(message)); }
    close() { this.readyState = 3; this.onclose?.({code: 1000}); }
  }
  const context = vm.createContext({
    document, WebSocket, AbortSignal, location: {host: 'localhost'},
    window: {addEventListener: (name, fn) => { listeners[name] = fn; }},
    setInterval: (fn, delay) => intervals.set(delay, fn),
    setTimeout: (fn, delay) => { timers.set(++timerId, {fn, delay}); return timerId; },
    clearTimeout: id => timers.delete(id),
    fetch: async url => {
      requests.push(url);
      return url === '/api/status' ? ui.statusResponse() : ui.commandResponse(url);
    },
  });
  vm.runInContext(script, context);
  vm.runInContext('socket.onmessage({data: JSON.stringify({type: "ready"})})', context);
  ui.run = code => vm.runInContext(code, context);
  ui.poll = intervals.get(1000);
  ui.move = intervals.get(100);
  ui.key = (name, code, options = {}) => listeners[name]({code, preventDefault() {}, ...options});
  ui.blur = () => listeners.blur();
  ui.closeSocket = (code = 1006) => {
    const socket = sockets.at(-1);
    socket.readyState = 3;
    socket.onclose({code, reason: code === 1008 ? 'Another dashboard owns control' : ''});
  };
  ui.retry = () => {
    const [id, {fn}] = timers.entries().next().value;
    timers.delete(id);
    fn();
  };
  ui.ready = () => sockets.at(-1).onmessage({data: JSON.stringify({type: 'ready'})});
  return ui;
}

test('socket loss reconnects with zero input and requires a fresh key after ownership is confirmed', async () => {
  const ui = dashboard();
  await ui.run('arm()');
  ui.key('keydown', 'KeyW');
  ui.closeSocket();
  assert.equal(ui.run('enabled'), false);
  assert.equal(ui.run('held.size'), 0);
  assert.equal(ui.timers.size, 1);
  assert.equal([...ui.timers.values()][0].delay, 1000);
  const armsBefore = ui.requests.filter(url => url === '/api/arm').length;
  ui.retry();
  assert.equal(ui.sockets.length, 2);
  await ui.run('arm()');
  assert.equal(ui.requests.filter(url => url === '/api/arm').length, armsBefore);
  ui.ready();
  ui.key('keydown', 'KeyW', {repeat: true});
  ui.move();
  assert.equal(ui.sent.at(-1).forward, 0);
  assert.equal(ui.requests.filter(url => url === '/api/arm').length, armsBefore);
  ui.key('keydown', 'KeyW', {repeat: false});
  assert.equal(ui.requests.filter(url => url === '/api/arm').length, armsBefore + 1);
});

test('a rejected second tab cannot stop or arm the owning dashboard through background events', async () => {
  const ui = dashboard();
  ui.closeSocket(1008);
  assert.equal(ui.timers.size, 0);
  ui.blur();
  await ui.run('arm()');
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.run('reconnectControl.hidden'), false);
  ui.key('keydown', 'Space');
  assert.deepEqual(ui.requests, ['/api/stop']);
});

test('socket recovery discards an old in-flight arm result', async () => {
  const ui = dashboard();
  let finish;
  ui.commandResponse = () => new Promise(resolve => { finish = () => resolve({ok: true, json: async () => ({armed: true})}); });
  const arm = ui.run('arm()');
  ui.closeSocket();
  ui.retry();
  ui.ready();
  finish();
  await arm;
  assert.equal(ui.run('enabled'), false);
});

test('robot transport recovery never replays a held drive key', async () => {
  const ui = dashboard();
  await ui.poll();
  await ui.run('arm()');
  ui.key('keydown', 'KeyW');
  ui.state.connected = false;
  ui.state.reconnecting = true;
  await ui.poll();
  assert.equal(ui.run('enabled'), false);
  const requests = ui.requests.filter(url => url === '/api/arm').length;
  Object.assign(ui.state, {connected: true, reconnecting: false, armed: false});
  await ui.poll();
  ui.key('keydown', 'KeyW', {repeat: true});
  ui.move();
  assert.equal(ui.sent.at(-1).forward, 0);
  assert.equal(ui.requests.filter(url => url === '/api/arm').length, requests);
});

test('server restart cancels retries instead of reconnecting with an expired token', async () => {
  const ui = dashboard();
  ui.closeSocket();
  assert.equal(ui.timers.size, 1);
  ui.statusResponse = async () => ({status: 403, ok: false});
  await ui.poll();
  assert.equal(ui.timers.size, 0);
  ui.run('openControl()');
  assert.equal(ui.sockets.length, 1);
  assert.equal(ui.run('controlReady'), false);
});

test('object boxes share the driving camera and toggling never changes movement', async () => {
  const ui = dashboard();
  await ui.run('arm()');
  Object.assign(ui.state, {armed: true, camera: true, boxes: {
    state: 'running', count: 2, fps: 8, frame_age_seconds: 0.1, error: '',
  }});
  await ui.poll();
  assert.match(ui.run('cam.src'), /^\/camera.boxes.mjpeg\?token=/);
  assert.match(ui.run('boxesStatus.textContent'), /2 detections/);
  const requests = ui.requests.length;
  ui.run('controlBoxes.checked = false; controlBoxes.onchange()');
  assert.match(ui.run('cam.src'), /^\/camera.mjpeg\?token=/);
  assert.equal(ui.run('enabled'), true);
  assert.equal(ui.requests.length, requests);
  ui.key('keydown', 'KeyW');
  ui.move();
  assert.equal(ui.sent.at(-1).forward, 1);
});

test('detector failure falls back to raw video and can be retried without robot commands', async () => {
  const ui = dashboard();
  ui.state.boxes = {state: 'error', error: 'Model unavailable'};
  await ui.poll();
  assert.match(ui.run('cam.src'), /^\/camera.mjpeg\?token=/);
  assert.match(ui.run('boxesStatus.textContent'), /Model unavailable.*Showing raw camera/);
  ui.run('controlBoxes.checked = false; controlBoxes.onchange()');
  ui.run('controlBoxes.checked = true; controlBoxes.onchange()');
  assert.match(ui.run('cam.src'), /^\/camera.boxes.mjpeg\?token=/);
  assert.deepEqual(ui.requests, ['/api/status']);
});

test('expired session stops the camera and a disconnected robot clears its stream', async () => {
  const ui = dashboard();
  await ui.poll();
  ui.state.connected = false;
  await ui.poll();
  assert.equal(ui.run('cam.src'), '');
  ui.state.connected = true;
  await ui.poll();
  ui.statusResponse = async () => ({ok: false, status: 403});
  await ui.poll();
  assert.equal(ui.run('cam.src'), '');
  assert.equal(ui.run('camConnected'), false);
  assert.match(ui.run('boxesStatus.textContent'), /Reload/);
});

test('trick recovers, enables the dashboard and drives with held WASD at 1.0', async () => {
  const ui = dashboard();
  await ui.run("action('hello')");
  ui.key('keydown', 'KeyW');
  ui.move();
  assert.equal(ui.sent.at(-1).forward, 0);
  assert.ok(!ui.requests.includes('/api/arm'));
  assert.ok(!ui.requests.includes('/api/stop'));
  await ui.poll();
  assert.equal(ui.run('enabled'), false);
  Object.assign(ui.state, {armed: true, recovering: false, stance: 'balanced'});
  await ui.poll();
  assert.equal(ui.run('enabled'), true);
  ui.move();
  assert.equal(ui.sent.at(-1).forward, 1.0);
  ui.key('keyup', 'KeyW');
  ui.move();
  assert.equal(ui.sent.at(-1).forward, 0);
});

test('STOP and blur prevent a delayed status response from enabling movement', async () => {
  for (const stop of [ui => ui.run("halt('STOP pressed')"), ui => ui.blur()]) {
    const ui = dashboard();
    await ui.run("action('hello')");
    ui.state.armed = true;
    let finish;
    const original = ui.statusResponse;
    ui.statusResponse = () => new Promise(resolve => { finish = () => resolve(original()); });
    const poll = ui.poll();
    stop(ui);
    finish();
    await poll;
    assert.equal(ui.run('enabled'), false);
    assert.equal(ui.run('autoEnable'), false);
  }
});

test('recovery failure leaves the dashboard disabled and allows a later retry', async () => {
  const ui = dashboard();
  await ui.run("action('hello')");
  Object.assign(ui.state, {recovering: false, error: 'RecoveryStand refused'});
  await ui.poll();
  assert.equal(ui.run('enabled'), false);
  assert.equal(ui.run('autoEnable'), false);
  ui.key('keydown', 'KeyW');
  assert.ok(ui.requests.includes('/api/arm'));
});

test('a refused trick cannot authorize automatic enabling', async () => {
  const ui = dashboard();
  ui.commandResponse = async () => ({ok: true,
    json: async () => ({status_code: 3202, command: 'Hello', status_text: 'refused'})});
  await ui.run("action('hello')");
  ui.state.armed = true;
  await ui.poll();
  assert.equal(ui.run('autoEnable'), false);
  assert.equal(ui.run('enabled'), false);
});

test('status polls never overlap, and the next completed poll enables after recovery', async () => {
  const ui = dashboard();
  await ui.run("action('hello')");
  const oldResponse = await ui.statusResponse();
  let finish;
  ui.statusResponse = () => new Promise(resolve => { finish = () => resolve(oldResponse); });
  const stalePoll = ui.poll();
  ui.statusResponse = async () => ({ok: true, json: async () => ({...ui.state, armed: true})});
  await ui.poll();
  assert.equal(ui.requests.filter(url => url === '/api/status').length, 1);
  finish();
  await stalePoll;
  await ui.poll();
  assert.equal(ui.run('enabled'), true);
});

test('a status reply started before arming cannot undo the new arm', async () => {
  const ui = dashboard();
  const oldResponse = await ui.statusResponse();
  let finish;
  ui.statusResponse = () => new Promise(resolve => { finish = () => resolve(oldResponse); });
  const poll = ui.poll();
  await ui.run('arm()');
  finish();
  await poll;
  assert.equal(ui.run('enabled'), true);
});

test('an old arm response cannot disable a newer trick recovery', async () => {
  const ui = dashboard();
  const original = ui.commandResponse;
  let finish;
  ui.commandResponse = url => url === '/api/arm'
    ? new Promise(resolve => { finish = () => resolve(original(url)); })
    : original(url);
  const arming = ui.run('arm()');
  await ui.run("action('hello')");
  finish();
  await arming;
  assert.equal(ui.run('autoEnable'), true);
  ui.state.armed = true;
  await ui.poll();
  assert.equal(ui.run('enabled'), true);
});
