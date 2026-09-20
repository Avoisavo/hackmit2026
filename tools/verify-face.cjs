// Dependency-free state and drawing-contract checks: node tools/verify-face.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let draws = 0;
const context = new Proxy({}, {
  get(_, key) {
    if (key === 'createRadialGradient' || key === 'createLinearGradient') return () => ({ addColorStop() {} });
    return (...args) => {
      for (const value of args) if (typeof value === 'number') assert.ok(Number.isFinite(value), `${key}: non-finite drawing argument`);
      if (key === 'drawImage') draws++;
    };
  },
  set() { return true; }
});
const canvas = () => ({ width: 1000, height: 600, clientWidth: 1000, clientHeight: 600, getContext: () => context });
const sandbox = { document: { createElement: canvas }, performance, requestAnimationFrame: () => 1, cancelAnimationFrame() {} };
sandbox.window = { devicePixelRatio: 1, matchMedia: () => ({ matches: false }) };
vm.createContext(sandbox);
for (const file of ['web/face.js', 'web/expressive.js', 'web/rabbit.js']) vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox);
const { Face, ExpressiveFace, RabbitFace } = sandbox.window;
for (const Renderer of [Face, ExpressiveFace, RabbitFace]) {
  const face = new Renderer(canvas());
  for (const name of Face.NAMES) {
    assert.equal(face.setEmote(name, 0), true);
    for (let i = 0; i < 120; i++) { face._step(1 / 60); face._draw(); }
    assert.equal(face.name, name);
    for (const p of Object.values(face._current())) for (const n of Object.values(p)) assert.ok(Number.isFinite(n));
  }
  face.setEmote('happy', 0);
  face._step(.07);
  const interrupted = face._current();
  face.setEmote('curious', 0);
  const resumed = face._current();
  for (const side of ['l', 'r']) for (const key of Object.keys(interrupted[side]))
    assert.ok(Math.abs(resumed[side][key] - interrupted[side][key]) < 1e-9, 'interruption preserves current pose');
  face._draw();
  assert.equal(face.setEmote('invalid'), false);
  face.setEmote('happy', .2);
  for (let i = 0; i < 20; i++) face._step(.02);
  assert.equal(face.name, 'neutral', 'hold expires to neutral');
  face.setEmote('sad', 0);
  for (let i = 0; i < 4000; i++) face._step(.02);
  assert.equal(face.name, 'sad', 'indefinite hold preserves mood');
  if (Renderer !== Face) assert.equal(face.sleepy, 0, 'explicit mood does not drift into sleep');
}
const face = new ExpressiveFace(canvas(), { reducedMotion: true });
face.setEmote('excited', 0);
assert.equal(face.t, 1, 'reduced motion skips arrival tween');
const before = JSON.stringify(face._modulate(face.to.l, 0));
face._step(.05);
assert.equal(JSON.stringify(face._modulate(face.to.l, 0)), before, 'reduced motion keeps geometry still');
face.setAttention(9, -9);
assert.equal(face.attention.x, 42);
assert.equal(face.attention.y, -24);
face.setAttention(null);
assert.equal(face.attention, null);
face.renderStill();
assert.ok(draws > 4000);
console.log('PASS: ten moods, interrupted transitions, finite drawing geometry, hold expiry, sustained moods, reduced motion, and attention bounds.');

const rabbit = new RabbitFace(canvas(), { reducedMotion: true });
rabbit.setEmote('excited', 0);
assert.equal(rabbit.t, 1);
const stillPose = JSON.stringify(rabbit._modulate(rabbit.to.l, 0));
rabbit._step(.05);
assert.equal(JSON.stringify(rabbit._modulate(rabbit.to.l, 0)), stillPose);
for (const [width, height] of [[1024,600],[800,480],[320,240],[600,1000]]) {
  rabbit.canvas.clientWidth = width; rabbit.canvas.clientHeight = height;
  for (const name of Face.NAMES) { rabbit.setEmote(name, 0); rabbit.renderStill(); }
}
rabbit.setEmote('happy', 0); rabbit.reducedMotion = false; rabbit._step(.08);
const accents = rabbit._features(); rabbit.setEmote('sad', 0);
assert.deepEqual(rabbit._features(), accents, 'ear and mouth transitions are continuous');
console.log('PASS: rabbit reduced motion, four display sizes, and interrupted ear/mouth transitions.');

for (const [alias, mood] of Object.entries({Ready:'neutral', Watching:'curious', Encourage:'happy', Thinking:'curious', Go:'excited', Celebrate:'love', Rest:'sleepy', 'Soft confused':'surprised'})) {
  assert.equal(rabbit.setEmote(alias, .2), true); assert.equal(rabbit.name, mood);
}
console.log('PASS: all eight existing controller names map to rabbit emotions.');
