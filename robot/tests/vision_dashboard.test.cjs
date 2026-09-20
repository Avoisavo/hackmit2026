// Execute the real page script with isolated browser/network boundaries; never contact hardware.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const htmlPath = `${__dirname}/../vision.html`;

function dashboard() {
  assert.ok(fs.existsSync(htmlPath), 'The vision dashboard must exist');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script, 'The vision dashboard must provide its interactive script');
  class Element {
    constructor(attrs = {}) {
      this.attrs = attrs; this.value = attrs.value || ''; this.hidden = 'hidden' in attrs;
      this.checked = 'checked' in attrs; this.disabled = 'disabled' in attrs; this.children = []; this.events = {}; this.dataset = {};
      this.srcAssignments = [];
      this.classList = {toggle() {}, add() {}, remove() {}};
    }
    set src(value) {this.source = value;this.srcAssignments.push(value);}
    get src() {return this.source || '';}
    set textContent(value) {this.text = String(value); this.children = [];}
    get textContent() {return (this.text || '') + this.children.map(c => c.textContent).join('');}
    set innerHTML(_) {throw new Error('Model content must never be inserted as HTML');}
    append(...nodes) {this.children.push(...nodes);}
    appendChild(node) {this.append(node); return node;}
    replaceChildren(...nodes) {this.text = ''; this.children = nodes;}
    setAttribute(key, value) {this.attrs[key] = String(value);}
    getAttribute(key) {return this.attrs[key] ?? null;}
    removeAttribute(key) {delete this.attrs[key]; if(key === 'src') this.src = '';}
    addEventListener(name, fn) {this.events[name] = fn;}
    focus() {this.focused = true;}
  }
  const elements = new Map();
  for(const match of html.matchAll(/<[\w-]+\b[^>]*\bid="[^"]+"[^>]*>/g)) {
    const attrs = Object.fromEntries([...match[0].matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1],m[2]]));
    if(/\sdisabled\b/.test(match[0])) attrs.disabled = '';
    if(/\schecked\b/.test(match[0])) attrs.checked = '';
    if(/\shidden\b/.test(match[0])) attrs.hidden = '';
    elements.set(attrs.id, new Element(attrs));
  }
  const requests = [], timers = [], events = {}, docEvents = {};
  const document = {hidden:false, querySelector:sel=>elements.get(sel.slice(1)), createElement:()=>new Element(), addEventListener:(name,fn)=>docEvents[name]=fn};
  let now = Date.now();
  class BrowserDate extends Date {static now() {return now;}}
  const context = vm.createContext({document, window:{addEventListener:(name,fn)=>events[name]=fn}, Date:BrowserDate, AbortSignal, console,
    fetch:(path,options={})=>new Promise((resolve,reject)=>requests.push({path,options,resolve(body,ok=true){resolve({ok,status:ok?200:502,json:async()=>body});},reject})),
    setInterval:(fn,ms)=>timers.push({fn,ms}), clearInterval(){}, setTimeout(){}, clearTimeout(){},
    localStorage:{setItem(){throw new Error('API keys must never enter browser storage');},getItem(){throw new Error('No stored API keys');}},
    WebSocket:class{constructor(){throw new Error('Vision must not open a motion control socket');}},
    location:{host:'mock.invalid'},
  });
  vm.runInContext(script.replace('__TOKEN__','test-control-token'),context);
  const flush = async()=>{for(let i=0;i<12;i++) await Promise.resolve();};
  const el = id=>{const node=elements.get(id);assert.ok(node,`element ${id}`);return node;};
  const fire = async(id,name='click')=>{const node=el(id);if(!node.disabled){const fn=node.events[name]||node[`on${name}`];assert.ok(fn,`${id} has ${name} handler`);fn({preventDefault(){}});await flush();}};
  const respond = async(path,body,ok=true)=>{const req=requests.find(r=>r.path===path&&!r.done);assert.ok(req,`request ${path}`);req.done=true;req.resolve(body,ok);await flush();return req;};
  const tick = async()=>{for(const t of timers.filter(t=>t.ms===1000)) t.fn();await flush();};
  return {el,fire,respond,tick,requests,events,docEvents,document,flush,elements,advance(ms){now+=ms;}};
}
const status = overrides=>({configured:true,model:'gpt-4.1-mini',running:false,busy:false,error:null,camera_fresh:true,connected:true,scans_remaining:30,interval_seconds:8,round_id:'round-3',target_object:'toy cars',target_count:5,
  observation:{objects:[{label:'red toy car',count:2},{label:'blue toy car',count:1},{label:'yellow cup',count:1}],observed_count:3,stable:true,scene_clear:true,reason:'Two clear views agree.'},
  lesson:{status:'need_more',suggested_speech:'We need 5 toy cars, and I can see 3. How many more do we need?',missing_count:2,extra_count:0,target_count:5,observed_count:3},last_event:null,observation_age_seconds:1,observation_fresh:true,observation_id:11,boxes:{state:'running',error:null,model:'YOLOE-26n',device:'cpu',count:4,frame_age_seconds:0.2,fps:3},...overrides});

// Wrong field selection can silently mix scene inventory with the chosen activity category.
test('specific scene inventory and selected-category count stay separate and use safe text',async()=>{
  const d=dashboard();const s=status();s.observation.objects.push({label:'<img src=x onerror=alert(1)>',count:1});
  await d.respond('/api/vision/status',s);
  assert.match(d.el('inventory').textContent,/red toy car/);assert.match(d.el('inventory').textContent,/yellow cup/);
  assert.match(d.el('inventory').textContent,/<img src=x onerror=alert\(1\)>/);
  assert.equal(d.el('observedCount').textContent,'3');assert.equal(d.el('goalCount').textContent,'5');
  assert.equal(d.el('targetLabel').textContent,'toy cars');assert.equal(d.el('checkAnswer').disabled,false);
  assert.equal(d.requests[0].options.headers['X-Control-Token'],'test-control-token');
  assert.match(d.el('camera').src,/^\/camera\.boxes\.mjpeg\?token=test-control-token$/);
});

test('uncertain, stale, and disconnected scenes never invite grading a cached count',async()=>{
  for(const changes of [{observation_age_seconds:50},{camera_fresh:false},{connected:false},{observation:{objects:[],observed_count:null,stable:false,scene_clear:false,reason:'Move objects apart.'}}]){
    const d=dashboard();await d.respond('/api/vision/status',status(changes));
    assert.equal(d.el('observedCount').textContent,'—');assert.equal(d.el('checkAnswer').disabled,true);
    assert.match(d.el('observationStatus').textContent,/check|fresh|uncertain|clear|offline/i);
    if(changes.camera_fresh===false||changes.connected===false) assert.doesNotMatch(d.el('cameraStatus').textContent,/^Live/);
  }
});

test('key form sends the key only in authenticated JSON and clears it before the response',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status({configured:false}));
  d.el('apiKey').value='sk-private-test';await d.fire('keyForm','submit');
  const req=d.requests.find(r=>r.path==='/api/vision/key');assert.ok(req);
  assert.equal(req.options.headers['X-Control-Token'],'test-control-token');
  assert.deepEqual(JSON.parse(req.options.body),{api_key:'sk-private-test'});assert.equal(d.el('apiKey').value,'');
  await d.respond('/api/vision/key',{detail:'Rejected sk-private-test'},false);
  assert.ok([...d.elements.values()].every(el=>!el.textContent.includes('sk-private-test')));
  assert.match(d.el('actionStatus').textContent,/key.*fail|could not.*key|key.*not/i);
});

test('a new round uses a specific category and integer goal, then clears prior answer feedback',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());d.el('targetObject').value='red toy cars';d.el('targetCount').value='4';
  await d.fire('roundForm','submit');const req=d.requests.find(r=>r.path==='/api/vision/round');
  assert.deepEqual(JSON.parse(req.options.body),{target_object:'red toy cars',target_count:4});
  await d.respond('/api/vision/round',status({round_id:'round-4',target_object:'red toy cars',target_count:4,observation:null,lesson:null,last_event:null,observation_age_seconds:null}));
  assert.equal(d.el('observedCount').textContent,'—');assert.equal(d.el('checkAnswer').disabled,true);assert.equal(d.el('targetLabel').textContent,'red toy cars');
});

test('fractional goals and answers are rejected before any API call',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());d.el('targetCount').value='2.5';
  await d.fire('roundForm','submit');assert.equal(d.requests.filter(r=>r.path==='/api/vision/round').length,0);
  d.el('answer').value='1.5';await d.fire('answerForm','submit');assert.equal(d.requests.filter(r=>r.path==='/api/vision/answer').length,0);
});

test('answer submission binds to the observed round and presents feedback without completing the physical task',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());d.el('answer').value='2';await d.fire('answerForm','submit');
  const req=d.requests.find(r=>r.path==='/api/vision/answer');assert.deepEqual(JSON.parse(req.options.body),{answer:2,round_id:'round-3',observation_id:11});
  await d.respond('/api/vision/answer',status({last_event:{...status().lesson,correct:true,event:'happy',task_complete:false,suggested_speech:"That's right! Let's add 2 more and count again."}}));
  assert.match(d.el('speech').textContent,/add 2 more/);assert.equal(d.el('expression').textContent,'happy');
  assert.doesNotMatch(d.el('lessonStatus').textContent,/goal reached|task complete/i);
});

test('API failures stay visible after polling and a network failure marks the camera unverified',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());await d.fire('scan');
  await d.respond('/api/vision/scan',{detail:'Camera frames unavailable'},false);
  assert.match(d.el('actionStatus').textContent,/Camera frames unavailable/);
  await d.tick();await d.respond('/api/vision/status',status());assert.match(d.el('actionStatus').textContent,/Camera frames unavailable/);
  await d.tick();const req=d.requests.filter(r=>r.path==='/api/vision/status'&&!r.done).at(-1);req.done=true;req.reject(new Error('Network down'));await d.flush();
  assert.equal(d.el('checkAnswer').disabled,true);assert.doesNotMatch(d.el('cameraStatus').textContent,/^Live/);
});

// Lifecycle stopping prevents hidden tabs from continuing paid image analysis.
test('hiding or leaving the page stops sampled vision only, with authenticated keepalive',async()=>{
  for(const kind of ['hidden','pagehide']){
    const d=dashboard();await d.respond('/api/vision/status',status({running:true}));
    if(kind==='hidden'){d.document.hidden=true;d.docEvents.visibilitychange();}else d.events.pagehide();
    const req=d.requests.find(r=>r.path==='/api/vision/stop');assert.ok(req);assert.equal(req.options.keepalive,true);
    assert.equal(req.options.headers['X-Control-Token'],'test-control-token');
    assert.ok(d.requests.every(r=>r.path.startsWith('/api/vision/')));
  }
});

test('a late status poll cannot overwrite a newly configured round',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());await d.tick();
  d.el('targetObject').value='blocks';d.el('targetCount').value='6';await d.fire('roundForm','submit');
  await d.respond('/api/vision/round',status({round_id:'round-4',target_object:'blocks',target_count:6,observation:null,lesson:null,last_event:null,observation_age_seconds:null}));
  await d.respond('/api/vision/status',status());assert.equal(d.el('targetLabel').textContent,'blocks');
});

// Hiding during a slow API call must not freeze the UI or resurrect auto-checking.
test('hide during start clears the pending action and stops a delayed start response',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());await d.fire('start');
  d.document.hidden=true;d.docEvents.visibilitychange();d.document.hidden=false;d.docEvents.visibilitychange();
  await d.respond('/api/vision/status',status());assert.equal(d.el('start').disabled,false);
  await d.respond('/api/vision/start',status({running:true}));
  assert.equal(d.requests.filter(r=>r.path==='/api/vision/stop').length,2);
});

// A drafted answer belongs to the displayed question, never a later scan.
test('a new observation clears the answer draft before it can be graded against a changed question',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());d.el('answer').value='2';
  await d.tick();await d.respond('/api/vision/status',status({observation_id:12,observation:{...status().observation,observed_count:4}}));
  assert.equal(d.el('answer').value,'');assert.match(d.el('answerUpdate').textContent,/scene changed/i);
  await d.fire('answerForm','submit');assert.equal(d.requests.filter(r=>r.path==='/api/vision/answer').length,0);
});

test('an unchanged observation preserves a drafted answer',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());d.el('answer').value='2';
  await d.tick();await d.respond('/api/vision/status',status());assert.equal(d.el('answer').value,'2');
});

test('a failed camera stream retries after a delay while remaining visibly unverified',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());const camera=d.el('camera');
  await d.fire('camera','error');assert.doesNotMatch(d.el('cameraStatus').textContent,/^Live/);
  await d.tick();await d.respond('/api/vision/status',status());assert.equal(camera.srcAssignments.length,1);
  d.advance(5000);await d.tick();await d.respond('/api/vision/status',status());assert.equal(camera.srcAssignments.length,2);
  await d.fire('camera','load');assert.match(d.el('cameraStatus').textContent,/^Live/);
});

// Toggling changes only the view stream; no detector/class-name guesses happen in the browser.
test('object boxes are on by default and the toggle switches authenticated streams',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status());
  assert.equal(d.el('showBoxes').checked,true);assert.equal(d.el('camera').src,'/camera.boxes.mjpeg?token=test-control-token');
  d.el('showBoxes').checked=false;await d.fire('showBoxes','change');
  assert.equal(d.el('camera').src,'/camera.mjpeg?token=test-control-token');
  await d.tick();await d.respond('/api/vision/status',status());assert.equal(d.el('showBoxes').checked,false);
  d.el('showBoxes').checked=true;await d.fire('showBoxes','change');
  assert.equal(d.el('camera').src,'/camera.boxes.mjpeg?token=test-control-token');
});

test('detector startup is labelled loading rather than camera offline',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status({boxes:{state:'loading',error:null,model:'YOLOE-26n',device:null,count:0,frame_age_seconds:null,fps:0}}));
  assert.match(d.el('boxStatus').textContent,/loading.*detector/i);assert.match(d.el('cameraMessage').textContent,/loading.*detector/i);
  assert.doesNotMatch(d.el('cameraStatus').textContent,/offline/i);assert.equal(d.el('cameraPlaceholder').hidden,false);
  d.el('showBoxes').checked=false;await d.fire('showBoxes','change');assert.equal(d.el('cameraPlaceholder').hidden,true);
});

test('detector errors explain the raw camera fallback and never claim live boxes',async()=>{
  const d=dashboard();await d.respond('/api/vision/status',status({boxes:{state:'error',error:'Model could not load <script>',model:'YOLOE-26n',device:null,count:0,frame_age_seconds:null,fps:0}}));
  assert.match(d.el('boxStatus').textContent,/Model could not load <script>/);assert.match(d.el('cameraHelp').textContent,/turn off.*object boxes/i);
  assert.doesNotMatch(d.el('cameraStatus').textContent,/^Live/);
  d.el('showBoxes').checked=false;await d.fire('showBoxes','change');assert.match(d.el('cameraStatus').textContent,/^Live/);
});
