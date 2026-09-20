// node tools/verify-twinkle.cjs — renderer contract without a browser dependency.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let frames = 0;
const ctx = new Proxy({}, {
  get(_,key) { if (key === 'createRadialGradient') return () => ({addColorStop(){}}); return (...args) => {
    for (const n of args) if (typeof n === 'number') assert.ok(Number.isFinite(n), `${key} must have finite geometry`);
    if (key === 'ellipse') assert.ok(args[2] >= 0 && args[3] >= 0, 'ellipse radii must stay positive');
    if (key === 'fillRect') frames++;
  }; }, set() { return true; }
});
function canvas(w=1000,h=600) { return {clientWidth:w,clientHeight:h,setAttribute(){},getContext:()=>ctx}; }
const sandbox = {performance,requestAnimationFrame:()=>1,cancelAnimationFrame(){},window:{devicePixelRatio:1,matchMedia:()=>({matches:false})}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('web/twinkle.js','utf8'),sandbox);
const Face = sandbox.window.TwinkleFace;
assert.deepEqual(Array.from(Face.NAMES), ['Ready','Watching','Encourage','Thinking','Go','Celebrate','Rest','Soft confused']);
for (const [width,height] of [[1000,600],[1024,600],[180,108],[390,844]]) {
  const face = new Face(canvas(width,height));
  for (const name of Face.NAMES) {
    assert.equal(face.setEmote(name),true);
    for (let i=0;i<90;i++) { face.step(1/60); face.draw(); }
    assert.equal(face.name,name);
  }
  face.setEmote('Go'); face.step(.05);
  const before = face.current(); face.setEmote('Thinking');
  assert.equal(JSON.stringify(before),JSON.stringify(face.current()),'interrupted transitions preserve geometry');
  for (const unknown of ['angry','sad','toString','__proto__','']) assert.equal(face.setEmote(unknown),false);
  face.setEmote('Ready');
  for (let i=0;i<6000;i++) face.step(.05);
  assert.equal(face.name,'Ready','waiting must never become sleepy or sad');
  face.setAttention(10,-10);
  assert.equal(face.attention.x,38);
  assert.equal(face.attention.y,-23);
  face.step(.1);
  assert.ok(face.gaze.x > 0 && face.gaze.y < 0, 'gaze follows attention');
  face.setAttention(null);
  assert.equal(face.gazeTarget.x,0);
  face.setMotion(false); face.setEmote('Celebrate');
  const still = JSON.stringify(face.current()); face.step(3); face.draw();
  assert.equal(JSON.stringify(face.current()),still,'reduced motion is static');
  assert.equal(face.current().spark,1,'celebration is distinct without animation');
  assert.equal(face._raf,null);
}
assert.ok(frames>2800);
console.log('PASS: eight exact names, safe geometry at four sizes, interruptible transitions, unsupported mood rejection, patient Ready, static Celebrate.');
