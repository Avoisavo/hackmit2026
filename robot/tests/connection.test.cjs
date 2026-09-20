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
  const requests = [];
  const state = {ip: '172.20.10.4', connected: false, armed: false, mode: ''};
  const document = {
    hidden: false, hasFocus: () => true,
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, {
        value: '', textContent: '', disabled: false, classList: {toggle() {}},
      });
      return elements.get(selector);
    },
    querySelectorAll: () => [],
    addEventListener: (name, fn) => { listeners[name] = fn; },
  };
  class WebSocket {
    static OPEN = 1;
    readyState = 1;
    send() {}
    close() { this.readyState = 3; this.onclose?.({code: 1000}); }
  }
  const ui = {requests, state, document, elements};
  ui.connectResponse = async () => ({connected: true});
  const context = vm.createContext({
    document, WebSocket, AbortSignal, location: {host: 'localhost'},
    window: {addEventListener: (name, fn) => { listeners[name] = fn; }},
    setInterval: (fn, delay) => intervals.set(delay, fn), setTimeout, clearTimeout,
    fetch: async (url, options) => {
      requests.push({url, options});
      const body = url === '/api/status' ? {...state}
        : url === '/api/connect' ? await ui.connectResponse() : {};
      return {ok: true, status: 200, json: async () => body};
    },
  });
  vm.runInContext(script, context);
  vm.runInContext('socket.onmessage({data: JSON.stringify({type: "ready"})})', context);
  ui.run = code => vm.runInContext(code, context);
  ui.poll = intervals.get(1000);
  ui.submit = () => elements.get('#connectionForm').onsubmit({preventDefault() {}});
  ui.key = event => listeners.keydown({preventDefault() {}, ...event});
  return ui;
}

test('connect submits the edited IP and prevents duplicate connection attempts', async () => {
  const ui = dashboard();
  ui.elements.get('#robotIp').value = '10.254.159.2';
  let finish;
  ui.connectResponse = () => new Promise(resolve => { finish = resolve; });
  const pending = ui.submit();
  assert.equal(ui.elements.get('#connectButton').disabled, true);
  await ui.submit();
  const requests = ui.requests.filter(request => request.url === '/api/connect');
  assert.equal(requests.length, 1);
  assert.deepEqual(JSON.parse(requests[0].options.body), {ip: '10.254.159.2'});
  finish({connected: true});
  await pending;
  assert.equal(ui.elements.get('#connectButton').disabled, false);
  assert.equal(ui.run('enabled'), false);
  assert.equal(ui.requests.some(request => request.url === '/api/arm'), false);
});

test('status polling never overwrites an IP being edited', async () => {
  const ui = dashboard();
  await ui.poll();
  const input = ui.elements.get('#robotIp');
  assert.equal(input.value, '172.20.10.4');
  input.value = '10.254.159.2';
  input.oninput();
  await ui.poll();
  assert.equal(input.value, '10.254.159.2');
});

test('typing in the IP field cannot arm movement, and Space still stops', () => {
  const ui = dashboard();
  const target = {closest: () => ui.elements.get('#robotIp')};
  ui.key({code: 'KeyW', target});
  assert.equal(ui.requests.length, 0);
  ui.key({code: 'Space', target});
  assert.equal(ui.requests.at(-1).url, '/api/stop');
});

test('invalid addresses are rejected before a connection request', async () => {
  const ui = dashboard();
  ui.elements.get('#robotIp').value = '999.1.1.1';
  await ui.submit();
  assert.equal(ui.requests.length, 0);
  assert.match(ui.elements.get('#connectionStatus').textContent, /valid robot IPv4/);
});
