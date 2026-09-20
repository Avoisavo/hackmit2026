import {renderHare} from './hare.js';
import {AudioSetup} from './audio_setup.js';

const $ = selector => document.querySelector(selector);
const token = document.body.dataset.token;
const face = new TwinkleFace($('#facePreview'), {motion: !matchMedia('(prefers-reduced-motion: reduce)').matches});
face.start();
let socket, controlId = '', controlReady = false, leaving = false, retry;
let activity = {}, robot = {}, generation = 0, starting = false, pending = false, cameraSource = '', testing = false, catalog = null;
const localDevices = {};
let preparing = false, preparationMessage = '';
let cueNotice = null;
let selectedDemo = '';
const demoViews = {
  count_check: {title: 'Demo 1 · Count and Check', cues: ['count'], hint: 'Use F if the camera misses the object count. Answer the maths question by voice or use the fallback below.', plan: 'HARE stays still while objects are placed and answers are given. Completing five objects triggers one Content celebration.'},
  run_play: {title: 'Demo 2 · Come Back and Count', cues: ['count','learner_left'], hint: 'Use L to cue the learner walking away. Answer two, then five during Hello counting. F supplies the object count when the mission returns.', plan: 'After inactivity or L, HARE turns and counts exactly two plus three Hello gestures. An enabled forward jump celebrates the correct total. Completing five objects triggers one Content celebration.'},
  soft_hands: {title: 'Demo 3 · Soft Hands', cues: ['bump','gentle'], hint: 'Cover the camera or press B. Say sorry when HARE asks; then show gentle touch and press G. G can record the touch while the soft-hands prompt finishes.', plan: 'HARE stays still for the bump, apology and gentle touch. After confirmed care it asks the learner to step back, then gives one thank-you Heart.'},
};
const audioMessages = {};
const audioSetup = new AudioSetup({pair, devices: localDevices, report(role, text) {
  audioMessages[role] = text;
  $('#' + role + 'Message').textContent = text;
  if (preparing) { preparationMessage = text; $('#preparationStatus').textContent = text; }
}});
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
  audioSetup.cancel();
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
    audioSetup.cancel();
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

function renderRelevantControls(state) {
  if (state.running && state.demo) selectedDemo = state.demo.name;
  else if (!selectedDemo && state.demo) selectedDemo = state.demo.name;
  const view = demoViews[selectedDemo];
  document.querySelectorAll('[data-for-demo]').forEach(node => {
    node.hidden = selectedDemo ? !node.dataset.forDemo.split(' ').includes(selectedDemo) : node.dataset.showIdle !== 'true';
  });
  document.querySelectorAll('[data-demo]').forEach(button => {
    button.dataset.selected = String(button.dataset.demo === selectedDemo);
    button.ariaPressed = button.dataset.selected;
  });
  const legacy = state.running && !state.demo;
  $('#manualOverrides').hidden = !view && !legacy;
  $('#demoControlsTitle').textContent = view ? view.title + ' controls' : 'Answer fallback';
  $('#demoControlsHint').textContent = view?.hint || '';
  $('#movementPlan').textContent = (view?.plan || 'Movements follow the lesson.') + ' STOP / Space cancels the sequence.';
  const care = selectedDemo === 'soft_hands';
  $('#answerLabel').hidden = care;
  $('#answerLabel').textContent = care ? 'Apology fallback' : 'Maths answer fallback';
  $('#answerHint').textContent = care ? 'After HARE asks for an apology, press the button to confirm “Sorry, HARE”.' : 'If the microphone misses it, type the learner’s number when HARE asks.';
  $('#answer').hidden = care;
  $('#answer').placeholder = care ? 'Sorry, HARE' : 'Learner’s number, e.g. one';
  $('#sendAnswer').textContent = care ? 'I apologized' : 'Submit answer';
  $('#outcome').hidden = !view && !legacy;
  return selectedDemo === state.demo?.name;
}

function render(state) {
  activity = state;
  const matchingDemo = renderRelevantControls(state);
  $('#stopAll').hidden = false;
  $('#liveActivity').hidden = false;
  renderMonitor(state);
  renderHare($('#hareDisplay'), state.demo);
  $('#presenterCue').textContent = state.demo?.presenter_cue || '';
  $('#demoNote').textContent = state.demo?.note || '';
  const io = state.audio_tool;
  $('#audioToolResult').textContent = io ? `${io.status}: ${io.result ? JSON.stringify(io.result) : 'Ready for a speech or listening tool call.'}` : '';
  document.querySelectorAll('[data-demo], #toolSpeak, #toolListen').forEach(button => { button.disabled = testing || preparing || state.running || state.busy || robot.ai?.busy || !controlReady; });
  document.querySelectorAll('[data-demo-event], #fallbackApply').forEach(button => {
    const cue = state.demo?.cues?.[button.dataset.demoEvent || 'count'];
    button.disabled = !state.running || !matchingDemo || !controlReady || !cue?.enabled;
    button.title = cue?.reason || 'Choose a demo to begin.';
  });
  $('#nextStep').textContent = state.demo?.next_step || 'Choose a demo to begin.';
  if (cueNotice && (cueNotice.session !== state.session_id || cueNotice.phase !== state.phase || cueNotice.speechId !== state.speech?.id)) cueNotice = null;
  const feedback = state.demo?.cue_feedback;
  $('#cueFeedback').textContent = cueNotice?.text || (feedback?.phase === state.phase && feedback.speech_id === (state.speech?.id || null) ? feedback.reason : '');
  if (face.name !== state.face) face.setEmote(state.face || 'Ready');
  $('#activityPhase').textContent = state.phase.replaceAll('_', ' ');
  $('#activityMessage').textContent = state.message;
  $('#goalCount').textContent = state.target;
  $('#seenCount').textContent = state.observed ?? '—';
  $('#startActivity').disabled = starting || state.running || state.busy || robot.ai?.busy || !controlReady;
  $('#sendAnswer').disabled = !state.running || (state.demo && !matchingDemo) || !['waiting_answer','waiting_blocks','answer_two','answer_five','await_apology'].includes(state.phase);
  $('#answer').disabled = $('#sendAnswer').disabled;
  $('#expression').disabled = false;
  $('#expression').value = state.face;
  $('#voiceHealth').textContent = `Speaker ${state.speaker.ready ? 'ready' : 'offline'} · ${state.devices.mic.online ? 'Mic online' : 'Mic offline'}`;
  $('#speakerStatus').textContent = state.speaker.message || 'Starts automatically with a demo or sound test.';
  $('#testResult').textContent = `${state.test.status}: ${state.test.message}`;
  $('#movementResult').textContent = robot.ai?.message || 'Movement is disarmed.';
  const locked = testing || state.running || state.busy || robot.ai?.busy || !controlReady;
  document.querySelectorAll('[data-test], [data-move], [data-posture], [data-trick], #testCamera').forEach(button => { button.disabled = locked; });
  document.querySelectorAll('[data-face]').forEach(button => { button.disabled = false; });
  const board = state.face_board;
  health('#faceHealth', `${state.face} · ${state.face_mode === 'manual' ? 'presenter override' : state.face_source || 'lesson'} · ${board?.delivered ? 'HB screen connected' : board?.online ? 'HB server up; screen pending' : state.devices.face.online ? 'Paired display online' : 'HB offline; local preview'}`, board?.delivered || state.devices.face.online ? 'ready' : 'idle');
  $('#observerReason').textContent = state.observer?.reason || '';
  $('#autoFace').disabled = state.face_mode !== 'manual';
  $('#jumpClearance').disabled = state.running || preparing;
  $('#keyStatus').textContent = Object.entries(state.configured).map(([name, ready]) => `${name}: ${ready ? 'configured' : 'missing'}`).join(' · ') + '. Keys stay in server memory.';
  $('#outcome').textContent = state.demo?.name === 'soft_hands'
    ? state.demo.apology_received ? 'Apology received. G confirms the gentle touch.' : 'HARE will ask for an apology, then soft hands. Say “sorry” when the microphone listens.'
    : state.task_complete ? 'Camera confirms the target number of objects.' : state.answer_correct ? 'Correct spoken answer. The added objects have not been confirmed by the camera.' : 'A correct answer and physically placing the objects are tracked separately.';
  const list = $('#events'); list.replaceChildren();
  for (const event of state.events) {
    const item = document.createElement('li'), type = document.createElement('b');
    type.textContent = event.kind; item.append(type, document.createTextNode(event.text)); list.append(item);
  }
}
function health(selector, text, state = 'idle') {
  const node = $(selector); node.textContent = text; node.dataset.health = state;
}
function renderMonitor(state) {
  const speaker = localDevices.speaker, mic = localDevices.mic;
  const speakerReady = speaker ? speaker.active && speaker.ready && speaker.audioContext?.state === 'running' : state.speaker.ready;
  const micReady = mic ? mic.active && mic.ready : state.devices.mic.online;
  health('#speakerHealth', speakerReady ? `${speaker?.playing ? 'Playing' : 'Ready'} · ${speaker ? audioSetup.outputLabel : 'Paired speaker'}` : audioMessages.speaker || 'Starts with your demo', speakerReady ? 'ready' : speaker ? 'error' : 'idle');
  health('#micHealth', micReady ? `${mic?.listener?.paused ? 'Ready · waiting' : 'Listening'} · ${audioSetup.microphoneLabel()}` : preparing ? (audioMessages.mic || 'Preparing…') : audioMessages.mic || 'Starts with your demo', micReady ? 'ready' : 'idle');
  health('#cameraHealth', robot.camera ? 'Live Go2 camera' : robot.connected ? 'Waiting for camera' : 'Connects with your demo', robot.camera ? 'ready' : 'idle');
  health('#elevenHealth', state.configured.elevenlabs ? 'Settings loaded' : 'Missing in .env.local', state.configured.elevenlabs ? 'ready' : 'error');
  health('#deepgramHealth', micReady ? 'Connected' : state.configured.deepgram ? 'Settings loaded' : 'Missing in .env.local', micReady || state.configured.deepgram ? 'ready' : 'error');
  health('#visionHealth', state.configured.openai ? 'Camera AI configured' : 'No OpenAI key · manual count available', state.configured.openai ? 'ready' : 'idle');
  health('#stageHealth', state.observer ? `${state.observer.stage.replaceAll('_', ' ')} · ${state.observer.status}` : 'Starts with your demo', state.observer?.status === 'observed' ? 'ready' : 'idle');
  health('#timeoutHealth', state.demo?.name === 'run_play' ? state.demo.adapted ? `Invitation triggered · ${state.demo.adaptation_source}` : `${state.demo.timeout_remaining}s without progress` : `Demo 2 · ${$('#stallSeconds').value || 12} seconds`);
  const physical = state.demo?.motion === 'robot_gestures';
  const moving = state.running && physical && ['turning','gesturing','demo_action'].includes(state.phase);
  const actionName = state.demo?.action === 'front_jump' ? 'Forward jump' : state.demo?.action;
  const motion = moving ? state.phase === 'turning' ? 'Turning with heading feedback' : state.phase === 'demo_action' ? `${actionName || 'Preparing gesture'} · ${(state.demo.actions_completed || []).length} gestures completed` : `Hello gesture · ${state.demo.hellos} completed` : robot.ai?.busy ? robot.ai.message : robot.recovering ? 'Recovering stance' : robot.busy ? 'Robot action in progress' : robot.armed ? 'Movement enabled' : 'Disarmed';
  health('#motionHealth', `${motion} · ${robot.stance || 'posture unknown'}${state.demo?.movement_reason ? ' · ' + state.demo.movement_reason : ''}`, moving || robot.armed || robot.busy ? 'active' : 'idle');
  health('#modeHealth', `${state.demo ? physical ? 'Lesson movements' + (state.demo.jump_enabled ? ' + forward jump' : '') : 'Screen rehearsal' : $('#demoMotion').value === 'robot_gestures' ? 'Lesson movements selected' : 'Screen rehearsal'} · ${robot.heading?.ready ? 'heading live' : 'heading unavailable'}`);
  $('#preparationStatus').textContent = preparationMessage;
}

async function poll() {
  if (pending || leaving) return;
  pending = true;
  try {
    const [state, status] = await Promise.all([request('/plane/status'), request('/status')]);
    robot = status; render(state);
    health('#robotHealth', !controlReady ? 'Dashboard controls unavailable' : status.connected ? `Connected · ${status.ip}` : status.reconnecting ? 'Reconnecting; activity stopped' : 'Disconnected', controlReady && status.connected ? 'ready' : 'idle');
    $('#camera').hidden = !status.connected;
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
  if ($('#sendAnswer').disabled) return;
  try {
    render(await request('/plane/answer', {session_id: activity.session_id, question_id: activity.question_id,
      event_id: crypto.randomUUID(), text: activity.demo?.name === 'soft_hands' ? 'Sorry, HARE' : $('#answer').value.trim()}));
    $('#answer').value = '';
  } catch (error) { report(error); }
};
$('#expression').onchange = () => request('/plane/face', {name: $('#expression').value}).then(render).catch(report);
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
  $('#' + (role === 'mic' ? 'localMic' : 'localSpeaker')).onclick = () => runTest(() => {
    localDevices[role]?.stop();
    return audioSetup.prepare({microphone: role === 'mic', check: preparationGuard(generation)});
  });
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
  button.onclick = () => runTest(async () => {
    const check = preparationGuard(generation);
    await audioSetup.prepare({microphone: button.dataset.test === 'microphone', check});
    check();
    render(await withContext('/plane/test', {kind: button.dataset.test}));
  });
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
  if (event.code === 'Space' && !event.target.closest('input,select,textarea')) { event.preventDefault(); halt(true); }
});
window.addEventListener('blur', () => halt());
document.addEventListener('visibilitychange', () => { if (document.hidden) halt(); });
window.addEventListener('pagehide', () => {
  leaving = true; halt(); clearTimeout(retry); socket?.close();
  Object.values(localDevices).forEach(device => device.stop());
});
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });

async function demoEvent(event, extra = {}) {
  if (!activity.running || !activity.demo) return;
  if (selectedDemo !== activity.demo.name || !demoViews[selectedDemo]?.cues.includes(event)) return;
  const cue = activity.demo.cues?.[event];
  if (!cue?.enabled) {
    cueNotice = {session: activity.session_id, phase: activity.phase, speechId: activity.speech?.id, text: cue?.reason || activity.demo.next_step || 'Wait for the next cue.'};
    render(activity);
    return;
  }
  cueNotice = null;
  render(await request('/plane/event', {event, ...extra, session_id: activity.session_id, event_id: crypto.randomUUID()}));
}
function preparationGuard(epoch) {
  return () => {
    if (epoch !== generation || leaving || document.hidden) throw new Error('Start cancelled. Select a demo when ready.');
  };
}
async function prepareDemo(name, rehearsal) {
  if (rehearsal || ['close', 'backup'].includes(name)) return;
  const check = preparationGuard(generation);
  if (!activity.configured?.elevenlabs) throw new Error('ElevenLabs settings are missing. The server loads ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID from .env.local on startup.');
  if (!activity.configured?.deepgram) throw new Error('Deepgram settings are missing. The server loads DEEPGRAM_API_KEY from .env.local on startup.');
  preparing = true;
  if (activity.phase) render(activity);
  try {
    // No await before this call: the demo click authorizes Web Audio and mic access.
    await audioSetup.prepare({microphone: true, check});
    check();
    if (!robot.connected) {
      preparationMessage = 'Connecting Go2 camera…';
      $('#preparationStatus').textContent = preparationMessage;
      try { await request('/connect', {ip: $('#robotIp').value.trim()}); }
      catch (error) {
        check();
        if ($('#demoMotion').value === 'robot_gestures') throw error;
        $('#error').textContent = 'Go2 camera unavailable. Presenter count override is available. ' + error.message;
      }
      check();
      robot = await request('/status');
    }
    if ($('#demoMotion').value === 'robot_gestures') {
      const needsHeading = name === 'run_play';
      const deadline = Date.now() + 10000;
      while ((!robot.camera || (needsHeading && !robot.heading?.ready)) && Date.now() < deadline) {
        preparationMessage = needsHeading ? 'Waiting for Go2 camera and heading feedback…' : 'Waiting for Go2 camera before gestures…';
        $('#preparationStatus').textContent = preparationMessage;
        await new Promise(resolve => setTimeout(resolve, 300));
        check(); robot = await request('/status');
      }
      if (!robot.camera || (needsHeading && !robot.heading?.ready)) throw new Error('Go2 camera or required heading feedback unavailable. Reconnect the robot or choose screen mode in advanced settings.');
    }
    check();
  } finally {
    preparing = false;
    preparationMessage = '';
    $('#preparationStatus').textContent = '';
  }
}
document.querySelectorAll('[data-demo]').forEach(button => {
  button.onclick = () => runTest(async () => {
    selectedDemo = button.dataset.demo;
    cueNotice = null;
    $('#answer').value = '';
    $('#setupPanel').open = false;
    renderRelevantControls(activity);
    const check = preparationGuard(generation);
    const rehearsal = $('#rehearsal').checked;
    await prepareDemo(button.dataset.demo, rehearsal);
    check();
    render(await withContext('/plane/start', {demo: button.dataset.demo, rehearsal,
      motion: rehearsal ? 'screen' : $('#demoMotion').value, stall_seconds: Number($('#stallSeconds').value || 12),
      jump_clearance: !rehearsal && button.dataset.demo === 'run_play' && $('#jumpClearance').checked}));
  });
});
document.querySelectorAll('[data-demo-event]').forEach(button => {
  button.onclick = () => demoEvent(button.dataset.demoEvent).catch(report);
});
$('#fallbackApply').onclick = () => demoEvent('count', {count: Number($('#fallbackCount').value)}).catch(report);
window.addEventListener('keydown', event => {
  if (event.repeat || event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input,select,textarea')) return;
  const cue = {KeyF:'count', KeyL:'learner_left', KeyB:'bump', KeyG:'gentle'}[event.code];
  if (!cue || !activity.running || !activity.demo) return;
  event.preventDefault();
  demoEvent(cue, cue === 'count' ? {count: Number($('#fallbackCount').value)} : {}).catch(report);
});
for (const [selector, name] of [['#toolSpeak','speak'], ['#toolListen','listen']]) {
  $(selector).onclick = () => runTest(async () => {
    const check = preparationGuard(generation);
    await audioSetup.prepare({microphone: name === 'listen', check});
    check();
    const args = name === 'speak' ? {text: $('#toolSpeech').value} : {seconds: 10};
    render(await withContext('/plane/call', {name, arguments: {...args, reason: 'Presenter selected the audio tool'}, run_id: crypto.randomUUID()}));
  });
}
$('#aiGoalForm').onsubmit = event => {
  event.preventDefault();
  runTest(() => withContext('/ai/start', {goal: $('#aiGoal').value, run_id: crypto.randomUUID()}));
};

$('#autoFace').onclick = () => request('/plane/face', {auto:true}).then(render).catch(report);
window.addEventListener('keydown', event => {
  if (event.repeat || event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input,select,textarea')) return;
  const names = ['Ready','Watching','Encourage','Thinking','Go','Celebrate','Rest','Soft confused'];
  if (/^[1-8]$/.test(event.key)) {
    event.preventDefault();
    request('/plane/face', {name:names[Number(event.key)-1]}).then(render).catch(report);
  }
});
