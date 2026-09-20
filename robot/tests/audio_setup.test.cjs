const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../plane_web/audio_setup.js'), 'utf8')
  .replace(/^import .*;\n/gm, '').replace('export class AudioSetup', 'class AudioSetup');
const AudioSetup = vm.runInNewContext(source + '\nAudioSetup');
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => {resolve=a;reject=b;}); return {promise,resolve,reject}; };
function fixture(overrides = {}) {
  const calls = [], devices = {}, contexts = [];
  const track = {label:'Whammo microphone',stop(){this.stopped=true;}};
  const stream = {getTracks:()=>[track],getAudioTracks:()=>[track]};
  const setup = new AudioSetup({devices,
    pair:async role => {calls.push('pair '+role);return {key:'scoped-key'};},
    createContext:() => { const ctx={state:'suspended',resume(){calls.push('resume');this.state='running';return Promise.resolve();},async close(){this.state='closed';}}; contexts.push(ctx);return ctx; },
    getMedia:() => {calls.push('capture');return Promise.resolve(stream);},
    makeClient:(role) => ({async start(ctx, input){calls.push('start '+role);this.active=true;this.ready=true;this.audioContext=ctx;if(input)this.listener={ctx,stream:input};},stop(){this.active=false;this.ready=false;}}),
    ...overrides});
  return {setup,calls,devices,contexts,track,stream};
}
test('one gesture resumes audio and requests microphone before any network pairing',async()=>{
  const f=fixture();const ready=f.setup.prepare();
  assert.deepEqual(f.calls,['resume','resume','capture']);
  await ready;
  assert.deepEqual(f.calls.slice(3).sort(),['pair mic','pair speaker','start mic','start speaker']);
  assert.equal(f.setup.microphoneLabel(),'Whammo microphone');
  assert.equal(f.devices.mic.ready,true);
});
test('does not finish setup before the microphone connects',async()=>{
  const gate=deferred();
  const f=fixture({makeClient:role=>({async start(){this.active=true;if(role==='mic')await gate.promise;this.ready=true;},stop(){this.active=false;}})});
  let ready=false; const pending=f.setup.prepare().then(()=>{ready=true;});
  await tick();assert.equal(ready,false);
  gate.resolve();await pending;assert.equal(ready,true);
});
test('ready devices are reused across demos without another permission request or pairing',async()=>{
  const f=fixture();await f.setup.prepare();const count=f.calls.length;
  await f.setup.prepare();
  assert.deepEqual(f.calls.slice(count),['resume','resume']);
  assert.equal(f.contexts.length,2);
});
test('STOP cancels immediately while permission is pending and closes a late microphone stream',async()=>{
  const permission=deferred();const f=fixture({getMedia:()=>permission.promise});
  const pending=f.setup.prepare();f.setup.cancel();
  await assert.rejects(pending,/setup stopped/);
  permission.resolve(f.stream);await tick();
  assert.equal(f.track.stopped,true);
  assert.equal(f.calls.some(call=>call.startsWith('pair')),false);
  assert.ok(f.contexts.every(ctx=>ctx.state==='closed'));
});
test('a synchronous capture failure rolls back both roles without unhandled promises',async()=>{
  const f=fixture({getMedia:()=>{throw new Error('Microphone denied');}});
  await assert.rejects(f.setup.prepare(),/Microphone denied/);await tick();
  assert.ok(f.contexts.every(ctx=>ctx.state==='closed'));
  assert.ok(Object.values(f.devices).every(client=>!client.active));
});
test('STOP after pairing begins prevents the late result from joining a device',async()=>{
  const pair=deferred();const f=fixture({pair:()=>pair.promise});
  const pending=f.setup.prepare();await tick();f.setup.cancel();
  await assert.rejects(pending,/setup stopped/);pair.resolve({key:'late-key'});await tick();
  assert.equal(Object.keys(f.devices).length,0);assert.equal(f.track.stopped,true);
});
test('a device that failed to become ready cannot start a demo',async()=>{
  const f=fixture({makeClient:()=>({async start(){this.active=false;},stop(){}})});
  await assert.rejects(f.setup.prepare(),/did not connect/);
});
