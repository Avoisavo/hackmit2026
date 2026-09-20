const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../plane_web');
const html = fs.readFileSync(path.join(root,'operator.html'),'utf8');
const source = fs.readFileSync(path.join(root,'operator.js'),'utf8').replace(/^import .*;\n/gm,'');
const audio = fs.readFileSync(path.join(root,'audio_setup.js'),'utf8').replace(/^import .*;\n/gm,'').replace('export class AudioSetup','class AudioSetup');
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
async function fixture({micGate,connected=false,configured=true}={}) {
  const nodes={},calls=[],listeners={},contexts=[],clients=[];
  const makeNode=(dataset={})=>({dataset,value:'',checked:false,textContent:'',hidden:false,disabled:false,
    replaceChildren(){},append(){},closest(){return null;}});
  for(const [,id] of html.matchAll(/id="([^"]+)"/g)) {assert.equal(nodes['#'+id],undefined,'duplicate ID '+id);nodes['#'+id]=makeNode();}
  nodes['#deviceOrigin'].value='http://127.0.0.1:8020';nodes['#robotIp'].value='test-robot';nodes['#demoMotion'].value='screen';
  const demos=['count_check','run_play','soft_hands','close','backup'].map(demo=>makeNode({demo}));
  const cueButtons=Object.fromEntries(['learner_left','bump','gentle'].map(name=>[name,makeNode({demoEvent:name})]));
  const scoped=[...html.matchAll(/<[a-z][^>]*\bdata-for-demo="([^"]*)"[^>]*>/g)].map(([tag,forDemo])=>{
    const id=tag.match(/\bid="([^"]+)"/)?.[1];const node=id?nodes['#'+id]:makeNode();
    Object.assign(node.dataset,{forDemo,showIdle:tag.match(/data-show-idle="([^"]+)"/)?.[1],trick:tag.match(/data-trick="([^"]+)"/)?.[1]});
    return node;
  });
  function addListener(event,fn){const previous=listeners[event];listeners[event]=value=>{previous?.(value);fn(value);};}
  const state={phase:'idle',message:'Choose a demo',target:3,face:'Ready',events:[],speaker:{ready:true},devices:{mic:{online:true},face:{online:false}},configured:{elevenlabs:configured,deepgram:configured,openai:false},test:{status:'idle',message:''}};
  const status={connected,camera:connected,ip:'test-robot',stop_epoch:1,ai:{busy:false}};
  let socket;
  class Socket {static OPEN=1;constructor(){socket=this;this.readyState=1;}send(){}close(){this.readyState=3;}}
  class Context {constructor(){contexts.push(this);this.state='suspended';}async resume(){calls.push({path:'resume'});this.state='running';}async close(){this.state='closed';}}
  class Device {
    constructor(role,key,report){Object.assign(this,{role,key,report,active:false,ready:false});clients.push(this);}
    async start(ctx,stream){this.active=true;this.audioContext=ctx;if(this.role==='mic'){this.listener={stream,ctx,paused:true,pause(){this.paused=true;}};if(micGate)await micGate.promise;}this.ready=this.active;}
    stop(){this.active=false;this.ready=false;}
    cancelAudio(){}
  }
  const track={label:'Whammo microphone',stop(){this.stopped=true;}};
  const context=vm.createContext({
    console,URL,URLSearchParams,AbortSignal,Uint8Array,Blob,AudioContext:Context,DeviceClient:Device,
    navigator:{mediaDevices:{getUserMedia(){calls.push({path:'capture'});return Promise.resolve({getTracks:()=>[track],getAudioTracks:()=>[track]});},enumerateDevices:async()=>[]}},
    location:{origin:'http://127.0.0.1:8020',protocol:'http:',host:'127.0.0.1:8020'},
    crypto:{randomUUID:()=> 'unique-event-id'},matchMedia:()=>({matches:false}),
    TwinkleFace:class{start(){}setEmote(name){this.name=name;}},renderHare(){},WebSocket:Socket,
    document:{body:{dataset:{token:'test'}},hidden:false,hasFocus:()=>true,
      querySelector(selector){assert.ok(nodes[selector],'Unknown DOM reference '+selector);return nodes[selector];},
      querySelectorAll(selector){if(selector==='[data-demo]')return demos;if(selector.startsWith('[data-demo],'))return [...demos,nodes['#toolSpeak'],nodes['#toolListen']];if(selector==='[data-for-demo]')return scoped;if(selector==='[data-demo-event]')return Object.values(cueButtons);if(selector==='[data-demo-event], #fallbackApply')return [...Object.values(cueButtons),nodes['#fallbackApply']];return [];},
      createElement:()=>makeNode(),createTextNode:t=>t,addEventListener:addListener},
    window:{addEventListener:addListener},
    setInterval(){},setTimeout(){},clearTimeout(){},
    fetch:async(url,options)=>{const path=url.replace('/api','');const payload=options.body?JSON.parse(options.body):undefined;calls.push({path,payload});
      const data=path==='/plane/status'?state:path==='/status'?status:path==='/ai/tools'?{tools:[],movements:[],dispatch:{path:'/ai/call',body:{}}}:path==='/plane/pair'?{key:'role-key',path:'/device/'+payload.role}:path==='/connect'?(status.connected=true,{}):state;
      return {ok:true,json:async()=>data};}
  });
  vm.runInContext(audio+'\n'+source,context);
  socket.onmessage({data:JSON.stringify({type:'ready',control_id:'test-control'})});await tick();
  return {nodes,calls,contexts,clients,listeners,track,state,status,scoped,cueButtons,render:context.render,
    key:code=>listeners.keydown({code,key:'',target:{closest:()=>null},preventDefault(){}}),
    demo:name=>demos.find(d=>d.dataset.demo===name).onclick()};
}
test('the selected demo shows only its controls, metrics and options while STOP stays visible',async()=>{
  const f=await fixture();
  assert.equal(f.nodes['#manualOverrides'].hidden,true);
  f.state.running=true;
  for(const [name,count,game,care] of [['count_check',true,false,false],['run_play',true,true,false],['soft_hands',false,false,true]]){
    f.state.demo={name};f.render(f.state);
    assert.equal(f.nodes['#countControls'].hidden,!count);
    assert.equal(f.nodes['#objectCounts'].hidden,!count);
    assert.equal(f.nodes['#gameControls'].hidden,!game);
    assert.equal(f.nodes['#demoTimer'].hidden,!game);
    assert.equal(f.nodes['#jumpOption'].hidden,!game);
    assert.equal(f.nodes['#timerOption'].hidden,!game);
    assert.equal(f.nodes['#careControls'].hidden,!care);
    assert.equal(f.nodes['#manualOverrides'].hidden,false);
    assert.equal(f.nodes['#stopAll'].hidden,false);
    assert.equal(f.nodes['#sendAnswer'].textContent,care?'Submit apology':'Submit answer');
    for(const node of f.scoped.filter(n=>n.dataset.trick)){
      assert.equal(node.hidden,!node.dataset.forDemo.split(' ').includes(name));
    }
  }
});
test('cue buttons follow the server step and irrelevant hotkeys send no commands',async()=>{
  const f=await fixture();f.state.running=true;f.state.phase='observing';
  f.state.demo={name:'count_check',cues:{count:{enabled:true,reason:'Fallback count'}}};f.render(f.state);
  assert.equal(f.nodes['#fallbackApply'].disabled,false);
  f.key('KeyB');f.key('KeyG');f.key('KeyL');await tick();
  assert.equal(f.calls.some(c=>c.path==='/plane/event'),false);
  f.state.demo={name:'soft_hands',next_step:'Say sorry first.',cues:{bump:{enabled:false},gentle:{enabled:false,reason:'Say sorry first.'}}};
  f.state.phase='await_apology';f.render(f.state);
  assert.equal(f.cueButtons.gentle.disabled,true);
  f.key('KeyG');await tick();assert.equal(f.calls.some(c=>c.path==='/plane/event'),false);
  assert.equal(f.nodes['#cueFeedback'].textContent,'Say sorry first.');
  assert.equal(f.nodes['#error'].textContent,'');
  f.state.phase='speaking';f.state.speech={id:'soft-hands-line'};
  f.state.demo.cues.gentle={enabled:true,reason:'Record touch after this line'};f.render(f.state);
  assert.equal(f.cueButtons.gentle.disabled,false);
  assert.equal(f.nodes['#cueFeedback'].textContent,'');
  await f.cueButtons.gentle.onclick();
  assert.equal(f.calls.filter(c=>c.path==='/plane/event').length,1);
  assert.equal(f.calls.find(c=>c.path==='/plane/event').payload.event,'gentle');
});
test('selecting a demo updates its controls during audio preparation and closes advanced settings',async()=>{
  const gate=deferred();const f=await fixture({micGate:gate});f.nodes['#setupPanel'].open=true;
  const pending=f.demo('soft_hands');
  assert.equal(f.nodes['#careControls'].hidden,false);
  assert.equal(f.nodes['#countControls'].hidden,true);
  assert.equal(f.nodes['#setupPanel'].open,false);
  gate.resolve();await pending;
});
test('Demo 3 apology enables typed fallback and displays care progress instead of maths grading',async()=>{
  const f=await fixture();
  f.state.running=true;f.state.phase='await_apology';
  f.state.demo={name:'soft_hands',apology_received:false};f.render(f.state);
  assert.equal(f.nodes['#sendAnswer'].disabled,false);
  assert.match(f.nodes['#outcome'].textContent,/Say “sorry”/);
  f.nodes['#answer'].value='sorry';await f.nodes['#answerForm'].onsubmit({preventDefault(){}});
  assert.equal(f.calls.find(c=>c.path==='/plane/answer').payload.text,'sorry');
  f.state.phase='speaking';f.state.demo.apology_received=true;f.render(f.state);
  assert.equal(f.nodes['#sendAnswer'].disabled,true);
  assert.match(f.nodes['#outcome'].textContent,/Apology received/);
});
test('Demo 3 click prepares both audio devices and waits for microphone readiness before starting',async()=>{
  const gate=deferred();const f=await fixture({micGate:gate});const pending=f.demo('soft_hands');
  assert.equal(f.contexts.length,2);assert.ok(f.calls.some(c=>c.path==='capture'));
  await tick();assert.equal(f.calls.some(c=>c.path==='/plane/start'),false);
  gate.resolve();await pending;
  assert.equal(f.calls.filter(c=>c.path==='/plane/pair').length,2);
  assert.equal(f.calls.filter(c=>c.path==='/plane/start').length,1);
  assert.equal(f.calls.find(c=>c.path==='/plane/start').payload.demo,'soft_hands');
  assert.equal(f.calls.some(c=>c.path==='/connect'),true);
  assert.match(f.nodes['#micHealth'].textContent,/Whammo microphone/);
});
test('Demo 1 prepares audio then connects camera and starts the chosen demo',async()=>{
  const f=await fixture();await f.demo('count_check');
  const paths=f.calls.map(c=>c.path);
  assert.ok(paths.indexOf('/connect')>paths.indexOf('/plane/pair'));
  assert.ok(paths.indexOf('/plane/start')>paths.indexOf('/connect'));
  assert.equal(f.calls.find(c=>c.path==='/plane/start').payload.motion,'screen');
});
for(const demo of ['count_check','soft_hands'])test(demo+' preserves real-gesture mode and does not require turn telemetry',async()=>{
  const f=await fixture({connected:true});f.nodes['#demoMotion'].value='robot_gestures';
  await f.demo(demo);
  assert.equal(f.calls.find(c=>c.path==='/plane/start').payload.motion,'robot_gestures');
  assert.equal(f.calls.find(c=>c.path==='/plane/start').payload.jump_clearance,false);
});
test('Demo 2 sends explicit jump clearance and the monitor names the forward jump',async()=>{
  const f=await fixture({connected:true});f.nodes['#demoMotion'].value='robot_gestures';
  f.status.heading={ready:true};f.nodes['#jumpClearance'].checked=true;await f.demo('run_play');
  assert.equal(f.calls.find(c=>c.path==='/plane/start').payload.jump_clearance,true);
  f.state.running=true;f.state.phase='demo_action';
  f.state.demo={name:'run_play',motion:'robot_gestures',action:'front_jump',actions_completed:['heart'],jump_enabled:true};
  f.render(f.state);
  assert.match(f.nodes['#motionHealth'].textContent,/Forward jump/);
  assert.equal(f.nodes['#jumpClearance'].disabled,true);
});
for(const reason of ['STOP','blur'])test(reason+' while microphone setup is pending prevents late demo startup',async()=>{
  const gate=deferred();const f=await fixture({micGate:gate});const pending=f.demo('soft_hands');await tick();
  if(reason==='STOP')f.nodes['#stopAll'].onclick();else f.listeners.blur();
  await pending;gate.resolve();await tick();
  assert.equal(f.calls.some(c=>c.path==='/plane/start'),false);
  assert.equal(f.calls.some(c=>c.path==='/stop'),true);
  assert.ok(f.clients.every(c=>!c.active));assert.equal(f.track.stopped,true);
});
test('caption rehearsal skips audio, credentials and robot connection',async()=>{
  const f=await fixture({configured:false});f.nodes['#rehearsal'].checked=true;await f.demo('count_check');
  assert.equal(f.contexts.length,0);assert.equal(f.calls.some(c=>c.path==='/connect'),false);
  assert.equal(f.calls.find(c=>c.path==='/plane/start').payload.rehearsal,true);
});
test('missing provider settings produce an actionable error without starting a lesson',async()=>{
  const f=await fixture({configured:false});await f.demo('soft_hands');
  assert.match(f.nodes['#error'].textContent,/\.env.local/);
  assert.equal(f.calls.some(c=>c.path==='/plane/start'),false);
});
