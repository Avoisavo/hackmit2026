// Network and DOM boundaries are simulated so these tests cannot move hardware.
// The actual dashboard script and inline click handlers run unchanged in a VM.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const html = readFileSync(`${__dirname}/../index.html`, 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function dashboard({socketState = 1} = {}) {
  const elements = [];
  for (const match of html.matchAll(/<(button|input|span|p|pre|b|img|div)[^>]*>/g)) {
    const attrs = Object.fromEntries([...match[0].matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));
    const classes = new Set((attrs.class || '').split(' '));
    elements.push({attrs, id: attrs.id, value: attrs.value || '', textContent: '', disabled: false,
      hidden: /\shidden(?:\s|>)/.test(match[0]), checked: /\schecked(?:\s|>)/.test(match[0]),
      dataset: Object.fromEntries(Object.entries(attrs).filter(([key]) => key.startsWith('data-')).map(([key,val]) => [key.slice(5),val])),
      classList: {toggle(key,on) {on ? classes.add(key) : classes.delete(key);}, contains(key) {return classes.has(key);}},
      bounds: {top:100,bottom:200}, scrolls: [],
      getBoundingClientRect() {return this.bounds;}, scrollIntoView(options) {this.scrolls.push(options);},
      setPointerCapture() {}, setAttribute(key,val) {attrs[key] = val;}, removeAttribute(key) {delete attrs[key];},
    });
  }
  const select = selector => elements.filter(el => selector.startsWith('#') ? el.id === selector.slice(1) : selector.startsWith('[data-') ? selector.slice(1,-1) in el.attrs : false);
  const events = {}, documentEvents = {}, timers = [], requests = [], sent = [], sockets = [];
  const document = {querySelector: s => select(s)[0], querySelectorAll: select, hidden: false, addEventListener: (name,fn) => documentEvents[name] = fn};
  class WebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static CLOSED = 3;
    constructor() {this.readyState=socketState;sockets.push(this);}
    send(text) {sent.push(JSON.parse(text));}
  }
  let confirmation = true, reloads = 0;
  const context = vm.createContext({document, window: {innerHeight:800,addEventListener: (name,fn) => events[name] = fn}, location: {host:'127.0.0.1:8001',reload(){reloads++;}}, WebSocket,
    fetch: (path,options) => new Promise((resolve,reject) => requests.push({path,options,fail(error){reject(error);},respond(body,ok=true,status=ok?200:502) {resolve({ok,status,json:async()=>body});}})),
    setInterval: (fn,ms) => timers.push({fn,ms}), setTimeout() {}, AbortSignal, Date, console,
    confirm: () => confirmation,
  });
  vm.runInContext(script,context);
  const evaluate = code => vm.runInContext(code,context);
  const flush = async () => {for(let i=0;i<8;i++) await Promise.resolve();};
  const click = fragment => {const el = elements.find(el => el.attrs.onclick?.includes(fragment)); assert.ok(el,`button ${fragment}`); if(!el.disabled) evaluate(el.attrs.onclick); return el;};
  const clickId = id => {const el=document.querySelector('#'+id);assert.ok(el,`button ${id}`);if(!el.disabled)evaluate(el.attrs.onclick);return el;};
  const respond = async (path,body,ok=true,status=ok?200:502) => {const req=requests.find(r=>r.path===path&&!r.done); assert.ok(req,`request ${path}`);req.done=true;req.respond(body,ok,status);await flush();};
  const tick = async ms => {for(const timer of timers.filter(t=>t.ms===ms)) timer.fn(); await flush();};
  const arm = async () => {click('arm()');await respond('/api/arm',{armed:true});};
  return {context,evaluate,events,documentEvents,document,elements,requests,sent,sockets,click,clickId,respond,tick,arm,flush,get reloads(){return reloads;},nextSocketState(value){socketState=value;},confirm(value){confirmation=value;}};
}

// A stop reply arriving late must not erase the user's explicit action feedback.
test('a trackpad click sends one trick and late stop feedback cannot erase its result', async () => {
  const d=dashboard();d.click("action('hello')");
  assert.equal(d.requests.filter(r=>r.path==='/api/action/hello').length,1);
  await d.respond('/api/action/hello',{command:'Hello',status_code:0,note:'Reply received'});
  const result=d.document.querySelector('#result').textContent;
  await d.respond('/api/stop',{armed:false,note:'Stop requested'});
  assert.equal(d.document.querySelector('#result').textContent,result);
});

// A stale arm response must never reverse a newer STOP or focus loss.
for (const reason of ['stop','blur']) test(`delayed Enable reply cannot rearm after ${reason}`,async()=>{
  const d=dashboard(); d.click('arm()');
  if(reason==='blur') d.events.blur(); else d.click("halt('STOP pressed')");
  await d.respond('/api/arm',{armed:true});
  assert.equal(d.evaluate('enabled'),false);
  d.events.keydown({code:'KeyW',preventDefault(){}});await d.tick(100);
  assert.equal(d.sent.at(-1).forward,0);
});

// Fast must reach the forward output without increasing the other directions.
test('Fast preset sends 60% forward and limits reverse, strafe and turns to 30%',async()=>{
  const d=dashboard(); await d.arm(); d.click('setSpeed(0.60)');
  d.events.keydown({code:'KeyW',preventDefault(){}}); await d.tick(100);
  assert.equal(d.sent.at(-1).forward,0.6);
  d.events.keyup({code:'KeyW'});
  for(const [code,key,want] of [['KeyS','forward',-0.3],['KeyQ','left',0.3],['KeyD','turn',-0.3]]){
    d.events.keydown({code,preventDefault(){}});await d.tick(100);assert.equal(d.sent.at(-1)[key],want);d.events.keyup({code});
  }
});

// Preserve deadman releases and reject secondary clicks when editing controls.
test('held direction moves, release or cancellation sends zero, secondary click does not move',async()=>{
  const d=dashboard();await d.arm();const forward=d.elements.find(e=>e.dataset.direction==='forward');
  const event={button:0,isPrimary:true,pointerId:1,preventDefault(){}};
  for(const release of ['onpointerup','onpointercancel','onlostpointercapture']){
    forward.onpointerdown(event);await d.tick(100);assert.ok(d.sent.at(-1).forward>0);
    forward[release]();await d.tick(100);assert.equal(d.sent.at(-1).forward,0);
  }
  forward.onpointerdown({...event,button:2});await d.tick(100);assert.equal(d.sent.at(-1).forward,0);
});

// Both Space phases must be cancelled to avoid native focused-button activation.
test('Space only stops, including when a trick has keyboard focus',()=>{
  const d=dashboard();let down=false,up=false;
  d.events.keydown({code:'Space',preventDefault(){down=true;}});
  d.events.keyup({code:'Space',preventDefault(){up=true;}});
  assert.equal(down,true);assert.equal(up,true);
  assert.equal(d.requests.filter(r=>r.path.startsWith('/api/action')).length,0);
  assert.ok(d.sent.some(m=>m.type==='stop'));
});

// Rejected firmware actions should stay labelled unavailable, not invite retries.
test('status disables unavailable MCF tricks and legacy mode switches',async()=>{
  const d=dashboard();await d.tick(1000);
  await d.respond('/api/status',{ip:'mock',connected:true,armed:false,mode:'mcf',camera:false,actions:{right_flip:{available:false,reason:'Unavailable in MCF'},hello:{available:true,reason:''}}});
  const right=d.elements.find(e=>e.attrs.onclick?.includes("action('right_flip'"));
  assert.equal(right.disabled,true);
  assert.match(right.title || right.attrs.title || '',/MCF/);
  assert.equal(d.elements.find(e=>e.attrs.onclick?.includes("mode('normal')")).disabled,true);
  d.click("action('right_flip'");assert.equal(d.requests.filter(r=>r.path==='/api/action/right_flip').length,0);
});

test('risky action confirmation can cancel without sending a trick',()=>{
  const d=dashboard();d.confirm(false);d.click("action('handstand'");
  assert.equal(d.requests.filter(r=>r.path.startsWith('/api/action')).length,0);
});

// Cancellation should also be visible instead of showing a stale success label.
test('cancelled Enable reply does not leave misleading accepted feedback',async()=>{
  const d=dashboard();d.click('arm()');d.click("halt('STOP pressed')");
  await d.respond('/api/arm',{armed:true});
  assert.match(d.document.querySelector('#commandStatus').textContent,/cancelled/i);
});

test('explicit robot rejection stays visible after a delayed stop response',async()=>{
  const d=dashboard();d.click("action('hello')");
  await d.respond('/api/action/hello',{detail:'The robot rejected the request (status -1)'},false);
  await d.respond('/api/stop',{armed:false});
  assert.match(d.document.querySelector('#commandStatus').textContent,/rejected.*-1/);
});

// A restarted server rotates its token. The obsolete page must stop inviting actions.
test('expired status disarms held inputs and offers one explicit session refresh without reload loops',async()=>{
  const d=dashboard();await d.arm();d.events.keydown({code:'KeyW',preventDefault(){}});
  await d.tick(1000);await d.respond('/api/status',{detail:'Unauthorized'},false,403);
  assert.equal(d.evaluate('enabled'),false);assert.equal(d.evaluate('held.size'),0);
  assert.equal(d.document.querySelector('#refreshSession')?.hidden,false);
  assert.equal(d.document.querySelector('#arm').disabled,true);
  assert.match(d.document.querySelector('#status').textContent,/session.*expired/i);
  const previousRequests=d.requests.length;const previousMessages=d.sent.length;
  await d.tick(100);await d.tick(1000);d.click("action('hello')");
  assert.equal(d.requests.length,previousRequests);assert.equal(d.sent.length,previousMessages);
  assert.equal(d.reloads,0);d.click('location.reload()');assert.equal(d.reloads,1);
});

test('command authentication failure immediately offers recovery and a late Enable reply stays disarmed',async()=>{
  const d=dashboard();d.click('arm()');d.click("action('hello')");
  await d.respond('/api/action/hello',{detail:'Unauthorized'},false,403);
  await d.respond('/api/arm',{armed:true});
  assert.equal(d.evaluate('enabled'),false);
  assert.equal(d.document.querySelector('#refreshSession')?.hidden,false);
  assert.match(d.document.querySelector('#commandStatus').textContent,/session|refresh/i);
  assert.doesNotMatch(d.document.querySelector('#commandStatus').textContent,/accepted/i);
});

test('an older successful status response cannot revive the camera after session expiration',async()=>{
  const d=dashboard();await d.tick(1000);await d.tick(1000);
  const [old,newer]=d.requests.filter(r=>r.path==='/api/status');
  newer.done=true;newer.respond({detail:'Unauthorized'},false,403);await d.flush();
  old.done=true;old.respond({ip:'mock',connected:true,armed:true,mode:'mcf',camera:true,actions:{}});await d.flush();
  assert.equal(d.document.querySelector('#cam').src,'');
  assert.match(d.document.querySelector('#status').textContent,/session.*expired/i);
  assert.equal(d.evaluate('enabled'),false);
});

test('the driving page defaults to labeled camera frames and can switch to raw video without arming',async()=>{
  const d=dashboard();await d.tick(1000);
  await d.respond('/api/status',{ip:'mock',connected:true,armed:false,mode:'mcf',camera:true,actions:{},boxes:{state:'running',frame_age_seconds:.25,count:2,fps:3,error:''}});
  const toggle=d.document.querySelector('#controlBoxes');assert.equal(toggle?.checked,true);
  assert.match(d.document.querySelector('#cam').src,/^\/camera\.boxes\.mjpeg\?token=/);
  assert.match(d.document.querySelector('#boxesStatus').textContent,/2.*3/);
  toggle.checked=false;toggle.onchange();
  assert.match(d.document.querySelector('#cam').src,/^\/camera\.mjpeg\?token=/);
  toggle.checked=true;toggle.onchange();
  assert.match(d.document.querySelector('#cam').src,/^\/camera\.boxes\.mjpeg\?token=/);
  assert.equal(d.evaluate('enabled'),false);
  assert.equal(d.requests.filter(r=>r.path==='/api/arm').length,0);
});

test('the driving camera reports detection errors and stale frame age instead of claiming fresh boxes',async()=>{
  for(const boxes of [{state:'loading',frame_age_seconds:null,count:0,fps:0,error:''},{state:'running',frame_age_seconds:4,count:2,fps:3,error:''},{state:'failed',frame_age_seconds:null,count:0,fps:0,error:'Detector unavailable'}]){
    const d=dashboard();await d.tick(1000);
    await d.respond('/api/status',{ip:'mock',connected:true,armed:false,mode:'mcf',camera:true,actions:{},boxes});
    const text=d.document.querySelector('#boxesStatus')?.textContent || '';
    if(boxes.error) assert.match(text,/Detector unavailable/);
    else if(boxes.frame_age_seconds>2) assert.match(text,/stale|fresh frame/i);
    else assert.match(text,/loading/i);
  }
});

test('a completed trick needs explicit Resume and a fresh key press before driving again',async()=>{
  const d=dashboard();await d.arm();d.events.keydown({code:'KeyW',preventDefault(){}});
  d.click("action('hello')");await d.respond('/api/action/hello',{command:'Hello',status_code:0,note:'Reply received'});
  assert.match(d.document.querySelector('#commandStatus').textContent,/driving paused.*resume driving/i);
  d.events.keydown({code:'KeyW',repeat:true,preventDefault(){}});await d.tick(100);
  assert.equal(d.sent.at(-1).forward,0);
  assert.equal(d.requests.filter(r=>r.path==='/api/arm').length,1);
  const resume=d.clickId('resumeDriving');await d.respond('/api/arm',{armed:true});
  assert.equal(resume.disabled,true);assert.equal(resume.classList.contains('on'),true);
  d.events.keydown({code:'KeyW',repeat:true,preventDefault(){}});await d.tick(100);
  assert.equal(d.sent.at(-1).forward,0);
  d.events.keyup({code:'KeyW'});d.events.keydown({code:'KeyW',repeat:false,preventDefault(){}});await d.tick(100);
  assert.equal(d.sent.at(-1).forward,.15);
  assert.equal(d.requests.filter(r=>r.path.startsWith('/api/posture/')).length,0);
});

test('ignored movement keys highlight Resume and only scroll when that row is outside the viewport',()=>{
  const d=dashboard();const row=d.document.querySelector('#resumeRow');assert.ok(row,'Resume row is present');
  row.bounds={top:900,bottom:1000};d.events.keydown({code:'KeyW',preventDefault(){}});
  assert.equal(row.classList.contains('attention'),true);assert.equal(row.scrolls.length,1);
  assert.equal(row.scrolls[0].block,'nearest');assert.equal(d.requests.length,0);
  row.bounds={top:100,bottom:200};d.events.keydown({code:'KeyW',repeat:true,preventDefault(){}});
  assert.equal(row.scrolls.length,1);assert.equal(d.evaluate('enabled'),false);
});

test('Resume remains disabled during commands or server busy and preserves trick errors',async()=>{
  const d=dashboard();const resume=d.document.querySelector('#resumeDriving');assert.ok(resume,'Resume button is present');
  d.click("action('hello')");assert.equal(resume.disabled,true);d.clickId('resumeDriving');
  assert.equal(d.requests.filter(r=>r.path==='/api/arm').length,0);
  await d.respond('/api/action/hello',{detail:'Robot command timed out; outcome unknown'},false);
  assert.match(d.document.querySelector('#commandStatus').textContent,/timed out.*unknown/);
  assert.doesNotMatch(d.document.querySelector('#commandStatus').textContent,/accepted/);
  for(const busy of [true,false]){
    await d.tick(1000);await d.respond('/api/status',{ip:'mock',connected:true,armed:false,busy,mode:'mcf',camera:true,actions:{}});
    assert.equal(resume.disabled,busy);
  }
  await d.tick(1000);await d.respond('/api/status',{detail:'Unauthorized'},false,403);
  assert.equal(resume.disabled,true);
});

for(const reason of ['stop','blur']) test(`a delayed Resume reply cannot rearm after ${reason}`,async()=>{
  const d=dashboard();d.clickId('resumeDriving');
  if(reason==='blur') d.events.blur();else d.click("halt('STOP pressed')");
  await d.respond('/api/arm',{armed:true});
  assert.equal(d.evaluate('enabled'),false);
  assert.equal(d.document.querySelector('#resumeDriving').classList.contains('on'),false);
  d.events.keydown({code:'KeyW',preventDefault(){}});await d.tick(100);assert.equal(d.sent.at(-1).forward,0);
});

function rejectControl(d) {
  const socket=d.sockets.at(-1);socket.readyState=3;
  socket.onclose({code:1008,reason:'Another dashboard owns control'});
}

test('a non-owning tab cannot Enable or Resume despite successful global robot status',async()=>{
  const d=dashboard();rejectControl(d);await d.tick(1000);
  await d.respond('/api/status',{ip:'mock',connected:true,armed:false,busy:false,mode:'mcf',camera:true,actions:{}});
  assert.equal(d.document.querySelector('#arm').disabled,true);
  assert.equal(d.document.querySelector('#resumeDriving').disabled,true);
  assert.match(d.document.querySelector('#controlStatus')?.textContent || '',/another dashboard owns control/i);
  d.click('arm()');d.clickId('resumeDriving');d.events.keydown({code:'KeyW',preventDefault(){}});
  assert.equal(d.requests.filter(r=>r.path==='/api/arm').length,0);
  assert.match(d.document.querySelector('#hint').textContent,/another dashboard|reconnect/i);
  assert.equal(d.evaluate('enabled'),false);
});

test('a rejected tab cannot disarm the owner on blur, hide or status failure but explicit STOP remains global',async()=>{
  const d=dashboard();rejectControl(d);
  d.events.blur();d.document.hidden=true;d.documentEvents.visibilitychange();
  await d.tick(1000);const poll=d.requests.find(r=>r.path==='/api/status');poll.fail(new Error('Network failure'));await d.flush();
  assert.equal(d.requests.filter(r=>r.path==='/api/stop').length,0);
  d.click("halt('STOP pressed')");assert.equal(d.requests.filter(r=>r.path==='/api/stop').length,1);
});

test('an Enable response arriving after socket loss cannot rearm or stop another owner',async()=>{
  const d=dashboard();d.click('arm()');rejectControl(d);await d.respond('/api/arm',{armed:true});
  assert.equal(d.evaluate('enabled'),false);
  assert.equal(d.requests.filter(r=>r.path==='/api/stop').length,0);
  assert.equal(d.document.querySelector('#resumeDriving').disabled,true);
});

test('explicit socket reconnect waits for an open connection and never automatically arms',async()=>{
  const d=dashboard();rejectControl(d);const old=d.sockets[0];d.nextSocketState(0);
  d.clickId('reconnectControl');assert.equal(d.sockets.length,2);
  assert.equal(d.document.querySelector('#arm').disabled,true);
  const current=d.sockets[1];current.readyState=1;current.onopen();
  assert.equal(d.document.querySelector('#arm').disabled,false);
  assert.equal(d.requests.filter(r=>r.path==='/api/arm').length,0);
  old.onclose({reason:'Old close event'});
  assert.equal(d.document.querySelector('#arm').disabled,false);
  d.click('arm()');await d.respond('/api/arm',{armed:true});
  d.events.keydown({code:'KeyW',preventDefault(){}});await d.tick(100);
  assert.equal(d.sent.at(-1).forward,.15);
});

test('initial connecting socket keeps Enable and Resume unavailable',()=>{
  const d=dashboard({socketState:0});
  assert.equal(d.document.querySelector('#arm').disabled,true);
  assert.equal(d.document.querySelector('#resumeDriving').disabled,true);
  d.click('arm()');assert.equal(d.requests.filter(r=>r.path==='/api/arm').length,0);
});
