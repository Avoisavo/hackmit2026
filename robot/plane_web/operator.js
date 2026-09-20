import {DeviceClient} from './device.js';

const $ = selector => document.querySelector(selector);
const token = document.body.dataset.token;
const face = new TwinkleFace($('#facePreview'), {motion: !matchMedia('(prefers-reduced-motion: reduce)').matches});
face.start();
let socket, controlId = '', controlReady = false, leaving = false, retry;
let activity = {}, robot = {}, generation = 0, starting = false, pending = false, cameraSource = '', testing = false, catalog = null;
const localDevices = {};
$('#deviceOrigin').value = location.origin;

async function request(path, payload) {
  const response = await fetch('/api' + path, {
    method: payload === undefined ? 'GET' : 'POST',
    headers: {'X-Control-Token': token, 'Content-Type': 'application/json'},
    body: payload === undefined ? undefined : JSON.stringify(payload),
    signal: AbortSignal.timeout(path === '/connect' || path === '/vision/scan' ? 45000 : 5000), cache: 'no-store'
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`);
    error.status = response.status; throw error;
  }
  return data;
}
function report(error) { $('#error').textContent = error.message || String(error); }
function halt(explicit = false) {
  generation++;
  localDevices.speaker?.cancelAudio();
  localDevices.mic?.listener?.pause();
  if (controlReady) socket.send(JSON.stringify({type: 'stop'}));
  if (controlReady || explicit) request('/stop', {}).catch(report);
}
function openControl() {
  if (leaving || socket && socket.readyState < 2) return;
  const candidate = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/control?token=${encodeURIComponent(token)}`);
  socket = candidate;
  candidate.onmessage = event => {
    if (socket !== candidate) return;
    let data;
    try { data = JSON.parse(event.data); } catch { return; }
    if (data.type === 'ready') { controlReady = true; controlId = data.control_id; }
  };
  candidate.onclose = event => {
    if (socket !== candidate) return;
    generation++; controlReady = false; controlId = '';
    localDevices.speaker?.cancelAudio();
    if (!leaving && event.code !== 1008) retry = setTimeout(openControl, 1500);
    else if (event.code === 1008) report(new Error('Another dashboard owns controls. Close it, then reload this page.'));
  };
}
openControl();
setInterval(() => {
  if (controlReady && socket.readyState === WebSocket.OPEN && !document.hidden && document.hasFocus())
    socket.send(JSON.stringify({type: 'move', forward: 0, left: 0, turn: 0}));
}, 100);

function render(state) {
  activity = state;
  if (face.name !== state.face) face.setEmote(state.face || 'Ready');
  $('#activityPhase').textContent = state.phase.replaceAll('_', ' ');
  $('#activityMessage').textContent = state.message;
  $('#goalCount').textContent = state.target;
  $('#seenCount').textContent = state.observed ?? '—';
  $('#startActivity').disabled = starting || state.running || state.busy || robot.ai?.busy || !controlReady;
  $('#sendAnswer').disabled = !state.running || state.phase !== 'waiting_answer';
  $('#expression').disabled = state.running;
  $('#expression').value = state.face;
  $('#voiceHealth').textContent = `Speaker ${state.speaker.ready ? 'ready' : 'offline'} · ${state.devices.mic.online ? 'Mic online' : 'Mic offline'}`;
  $('#speakerStatus').textContent = state.speaker.message || 'Enable a speaker first.';
  $('#testResult').textContent = `${state.test.status}: ${state.test.message}`;
  $('#movementResult').textContent = robot.ai?.message || 'Movement is disarmed.';
  const locked = testing || state.running || state.busy || robot.ai?.busy || !controlReady;
  document.querySelectorAll('[data-test], [data-move], [data-posture], [data-trick], #testCamera').forEach(button => { button.disabled = locked; });
  document.querySelectorAll('[data-face]').forEach(button => { button.disabled = state.running; });
  $('#faceHealth').textContent = state.devices.face.online ? 'Display online · ' + state.face : 'Local preview · pair external display';
  $('#keyStatus').textContent = Object.entries(state.configured).map(([name, ready]) => `${name}: ${ready ? 'configured' : 'missing'}`).join(' · ') + '. Keys stay in server memory.';
  $('#outcome').textContent = state.task_complete ? 'Camera confirms the target number of blocks.' : state.answer_correct ? 'Correct spoken answer. The additional block has not been confirmed by the camera.' : 'A correct answer and physically placing the blocks are tracked separately.';
  const list = $('#events'); list.replaceChildren();
  for (const event of state.events) {
    const item = document.createElement('li'), type = document.createElement('b');
    type.textContent = event.kind; item.append(type, document.createTextNode(event.text)); list.append(item);
  }
}
async function poll() {
  if (pending || leaving) return;
  pending = true;
  try {
    const [state, status] = await Promise.all([request('/plane/status'), request('/status')]);
    robot = status; render(state);
    $('#robotHealth').textContent = !controlReady ? 'Dashboard controls unavailable' : status.connected ? `Connected · ${status.camera ? 'camera live' : 'camera starting'}` : status.reconnecting ? 'Reconnecting; activity stopped' : 'Disconnected';
    const source = status.connected ? `/camera.mjpeg?token=${encodeURIComponent(token)}` : '';
    if (source !== cameraSource) { cameraSource = source; $('#camera').src = source; }
  } catch (error) {
    if (error.status === 403) {
      leaving = true; clearTimeout(retry); socket?.close();
      report(new Error('Server restarted. Reload this page and pair devices again.'));
    } else { halt(); report(error); }
  } finally { pending = false; }
}
setInterval(poll, 800); poll();
$('#camera').onerror = () => {
  if (cameraSource) setTimeout(() => { if (cameraSource) $('#camera').src = cameraSource + '&retry=' + Date.now(); }, 2000);
};
$('#stopAll').onclick = () => halt(true);
$('#connectForm').onsubmit = async event => {
  event.preventDefault(); $('#error').textContent = '';
  const button = event.submitter; button.disabled = true;
  try { await request('/connect', {ip: $('#robotIp').value.trim()}); await poll(); }
  catch (error) { report(error); }
  finally { button.disabled = false; }
};
$('#disconnect').onclick = () => request('/disconnect', {}).then(poll).catch(report);
$('#activityForm').onsubmit = async event => {
  event.preventDefault(); $('#error').textContent = '';
  if (starting || !controlReady || document.hidden || !document.hasFocus()) return;
  const epoch = generation;
  starting = true; $('#startActivity').disabled = true;
  try {
    const status = await request('/status');
    if (epoch !== generation) return;
    const state = await request('/plane/start', {control_id: controlId, control_epoch: status.stop_epoch,
      target: Number($('#target').value), wave: $('#wave').checked});
    if (epoch === generation) render(state);
  } catch (error) { halt(); report(error); }
  finally { starting = false; $('#startActivity').disabled = activity.running || activity.busy || !controlReady; }
};
$('#answerForm').onsubmit = async event => {
  event.preventDefault();
  try {
    render(await request('/plane/answer', {session_id: activity.session_id, question_id: activity.question_id,
      event_id: crypto.randomUUID(), text: $('#answer').value.trim()}));
    $('#answer').value = '';
  } catch (error) { report(error); }
};
$('#expression').onchange = () => request('/plane/face', {name: $('#expression').value}).then(render).catch(report);
$('#keysForm').onsubmit = async event => {
  event.preventDefault(); const values = {};
  for (const input of event.target.querySelectorAll('input')) {
    if (input.value.trim()) values[input.name] = input.value.trim();
    input.value = '';
  }
  request('/plane/keys', values).then(render).catch(report);
};
async function pair(role) {
  const result = await request('/plane/pair', {role});
  const base = new URL($('#deviceOrigin').value || location.origin);
  if (!['http:', 'https:'].includes(base.protocol)) throw new Error('Use an HTTP or HTTPS server address.');
  $('#' + role + 'Link').value = base.origin + result.path;
  return result;
}
document.querySelectorAll('[data-pair]').forEach(button => {
  button.onclick = () => pair(button.dataset.pair).catch(report);
});
for (const role of ['mic', 'speaker']) {
  $('#' + (role === 'mic' ? 'localMic' : 'localSpeaker')).onclick = async () => {
    if (activity.running) { report(new Error('Stop the activity before replacing audio devices.')); return; }
    let audioContext;
    if (role === 'speaker') { audioContext = new AudioContext(); await audioContext.resume(); }
    localDevices[role]?.stop();
    try {
      const data = await pair(role);
      const client = new DeviceClient(role, data.key, text => { $('#' + role + 'Message').textContent = text; });
      localDevices[role] = client;
      await client.start(audioContext);
    } catch (error) { audioContext?.close().catch(() => {}); report(error); }
  };
}

$('#stopTest').onclick = () => halt(true);
async function withContext(path, payload) {
  if (!controlReady || document.hidden || !document.hasFocus()) throw new Error('Keep this dashboard focused and wait for controls to connect.');
  const epoch = generation;
  const status = await request('/status');
  if (epoch !== generation) throw new Error('Controls stopped; press the test again when ready.');
  return request(path, {...payload, control_id: controlId, control_epoch: status.stop_epoch});
}
async function runTest(work) {
  if (testing) return;
  testing = true; $('#error').textContent = '';
  try { await work(); } catch (error) { report(error); }
  finally { testing = false; await poll(); }
}
document.querySelectorAll('[data-test]').forEach(button => {
  button.onclick = () => runTest(async () => render(await withContext('/plane/test', {kind: button.dataset.test})));
});
document.querySelectorAll('[data-face]').forEach(button => {
  button.onclick = () => request('/plane/face', {name: button.dataset.face}).then(render).catch(report);
});
document.querySelectorAll('[data-move], [data-posture], [data-trick]').forEach(button => {
  button.onclick = () => runTest(async () => {
    const name = button.dataset.move ? 'move_robot' : button.dataset.posture ? 'set_posture' : 'perform_trick';
    const args = button.dataset.move ? {direction: button.dataset.move, seconds: 0.3, speed: 0.15} : button.dataset.posture ? {posture: button.dataset.posture} : {action: button.dataset.trick};
    await withContext('/ai/call', {name, arguments: {...args, reason: 'Operator selected this test from the control plane'}, run_id: crypto.randomUUID()});
  });
});
$('#testCamera').onclick = () => runTest(async () => {
  $('#cameraTestResult').textContent = 'Reading two Go2 camera frames…';
  const epoch = generation;
  await request('/vision/round', {target_object: 'toy blocks', target_count: Number($('#target').value)});
  if (epoch !== generation) return;
  const result = await request('/vision/scan', {});
  const obs = result.observation;
  $('#cameraTestResult').textContent = result.error || (obs ? `${obs.observed_count} blocks · ${obs.stable ? 'two views agree' : 'count uncertain'}` : 'No observation returned.');
});
setInterval(() => { $('#micLevel').value = localDevices.mic?.listener?.level || 0; }, 100);
function addRow(table, values) {
  const row = document.createElement('tr');
  for (const value of values) { const cell = document.createElement('td'); cell.textContent = value; row.append(cell); }
  table.append(row);
}
function describeParameter([name, value]) {
  if (name === 'reason') return 'reason: brief explanation';
  return name + ': ' + (value.enum ? value.enum.join(' | ') : value.type === 'number' ? `${value.minimum}–${value.maximum}` : value.type);
}
request('/ai/tools').then(data => {
  catalog = data;
  for (const tool of data.tools) addRow($('#toolsTable'), [tool.name, Object.entries(tool.parameters.properties).map(describeParameter).join('; '), tool.description]);
  for (const move of data.movements) addRow($('#movementsTable'), [move.name, move.ai_tool || 'Manual only', (move.manual_method || 'POST') + ' ' + move.manual_endpoint, [move.normal_command && 'Normal', move.ai_mode_command && 'AI'].filter(Boolean).join(' / ')]);
  $('#toolExample').textContent = 'POST ' + data.dispatch.path + '\n' + JSON.stringify(data.dispatch.body, null, 2);
}).catch(report);
$('#downloadTools').onclick = () => {
  if (!catalog) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(catalog, null, 2)], {type: 'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = 'go2-tool-map.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
window.addEventListener('keydown', event => {
  if (event.code === 'Space' && !event.target.closest('input,select,textarea,button')) { event.preventDefault(); halt(true); }
});
window.addEventListener('blur', () => halt());
document.addEventListener('visibilitychange', () => { if (document.hidden) halt(); });
window.addEventListener('pagehide', () => {
  leaving = true; halt(); clearTimeout(retry); socket?.close();
  Object.values(localDevices).forEach(device => device.stop());
});
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
