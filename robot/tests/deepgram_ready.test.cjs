const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../plane_web/deepgram.js'),'utf8').replace('export class ChildListener','class ChildListener');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
  let ws;const timers=new Map();let id=0;
  const track={stop(){this.stopped=true;}};
  const stream={getTracks:()=>[track],getAudioTracks:()=>[track]};
  const audio={async resume(){},async close(){},createAnalyser:()=>({}),createMediaStreamSource:()=>({connect(){}})};
  class Socket{static OPEN=1;constructor(){ws=this;this.readyState=0;}send(){}close(){this.readyState=3;}}
  class Recorder{static isTypeSupported(){return true;}start(){this.state='recording';}stop(){this.state='inactive';}}
  const context=vm.createContext({WebSocket:Socket,MediaRecorder:Recorder,AbortSignal,URLSearchParams,
    fetch:async()=>({ok:true,json:async()=>({access_token:'short-lived-test-token'})}),console:{log(){}},
    setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:id=>timers.delete(id)});
  const Listener=vm.runInContext(source+'\nChildListener',context);
  const listener=new Listener({onUtterance(){}},{key:'test',clientId:'mic'});
  return {listener,stream,audio,track,timers,get ws(){return ws;}};
}
test('microphone startup resolves only after Deepgram opens and recording starts',async()=>{
  const f=fixture();let ready=false;const pending=f.listener.start(f.stream,f.audio).then(()=>{ready=true;});
  await tick();assert.equal(ready,false);assert.equal(f.listener.recorder,null);
  f.ws.readyState=1;f.ws.onopen();await pending;
  assert.equal(ready,true);assert.equal(f.listener.recorder.state,'recording');assert.equal(f.timers.size,0);
  f.listener.stop();assert.equal(f.track.stopped,true);
});
test('Deepgram refusal rejects setup instead of reporting a ready microphone',async()=>{
  const f=fixture();const pending=f.listener.start(f.stream,f.audio);const rejected=assert.rejects(pending,/connection failed/);
  await tick();f.ws.onerror();await rejected;assert.equal(f.timers.size,0);f.listener.stop();
});
test('STOP during a pending Deepgram connection cannot begin recording later',async()=>{
  const f=fixture();const pending=f.listener.start(f.stream,f.audio);const rejected=assert.rejects(pending,/setup stopped/);
  await tick();const socket=f.ws;f.listener.stop();await rejected;socket.onopen();
  assert.equal(f.listener.recorder,null);assert.equal(f.track.stopped,true);assert.equal(f.timers.size,0);
});
test('a Deepgram connection that never opens reports a bounded timeout',async()=>{
  const f=fixture();const pending=f.listener.start(f.stream,f.audio);const rejected=assert.rejects(pending,/timed out/);
  await tick();[...f.timers.values()][0]();await rejected;assert.equal(f.timers.size,0);f.listener.stop();
});
