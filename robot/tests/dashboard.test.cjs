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
  const sent = [];
  const requests = [];
  const state = {connected: true, armed: false, recovering: true,
    mode: 'normal', stance: 'after_trick', error: ''};
  const ui = {state, sent, requests};
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
        textContent: '', classList: {toggle() {}},
      });
      return elements.get(selector);
    },
    querySelectorAll: () => [],
    addEventListener: (name, fn) => { listeners[name] = fn; },
  };
  class WebSocket {
    static OPEN = 1;
    readyState = 1;
    send(message) { sent.push(JSON.parse(message)); }
  }
  const context = vm.createContext({
    document, WebSocket, AbortSignal, location: {host: 'localhost'},
    window: {addEventListener: (name, fn) => { listeners[name] = fn; }},
    setInterval: (fn, delay) => intervals.set(delay, fn), setTimeout,
    fetch: async url => {
      requests.push(url);
      return url === '/api/status' ? ui.statusResponse() : ui.commandResponse(url);
    },
  });
  vm.runInContext(script, context);
  ui.run = code => vm.runInContext(code, context);
  ui.poll = intervals.get(1000);
  ui.move = intervals.get(100);
  ui.key = (name, code) => listeners[name]({code, preventDefault() {}});
  ui.blur = () => listeners.blur();
  return ui;
}

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

test('an older disarmed status cannot undo completed automatic enabling', async () => {
  const ui = dashboard();
  await ui.run("action('hello')");
  const oldResponse = await ui.statusResponse();
  let finish;
  ui.statusResponse = () => new Promise(resolve => { finish = () => resolve(oldResponse); });
  const stalePoll = ui.poll();
  ui.statusResponse = async () => ({ok: true, json: async () => ({...ui.state, armed: true})});
  await ui.poll();
  finish();
  await stalePoll;
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
