const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../plane_web/hare.js'), 'utf8').replace('export function', 'function');
function setup(reduced=false) {
  const nodes = {}, effects = [];
  const root = {hidden:false,dataset:{},querySelector(key) {return nodes[key] ||= {textContent:'',animate:frames=>effects.push(frames)};},animate:frames=>effects.push(frames)};
  const context = vm.createContext({matchMedia:()=>({matches:reduced})});
  vm.runInContext(source,context);
  return {render:vm.runInContext('renderHare',context),root,nodes,effects};
}
test('camera equations and presenter fallback are visibly distinguished',()=>{
  const s=setup();
  s.render(s.root,{equation:'2 + 1 = 3',evidence:'presenter',motion:'screen',hellos:1});
  assert.equal(s.nodes['[data-hare-equation]'].textContent,'2 + 1 = 3');
  assert.equal(s.nodes['[data-hare-source]'].textContent,'Presenter fallback');
  assert.equal(s.nodes['[data-hare-hops]'].textContent,'1 screen hellos');
  s.render(s.root,{equation:'3',evidence:'camera',hellos:0});
  assert.equal(s.nodes['[data-hare-source]'].textContent,'Camera count');
});
test('repeated snapshots animate each hop or ear cue once',()=>{
  const s=setup();
  const demo={title:'Soft Hands',effect:{id:'a',kind:'wobble'},hellos:0};
  s.render(s.root,demo);s.render(s.root,demo);
  assert.equal(s.effects.length,1);
  s.render(s.root,{...demo,effect:{id:'b',kind:'wave'}});
  assert.equal(s.effects.length,2);
});
test('reduced motion keeps the equation and count without animation',()=>{
  const s=setup(true);
  s.render(s.root,{equation:'3 + 2 = 5',motion:'robot_gestures',hellos:5,effect:{id:'a',kind:'wave'}});
  assert.equal(s.effects.length,0);
  assert.equal(s.nodes['[data-hare-hops]'].textContent,'5 Hello gestures commanded');
  s.render(s.root,null);assert.equal(s.root.hidden,true);
});
