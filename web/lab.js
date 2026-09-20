(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var names = Face.NAMES;
  var copy = [
    ['Just here.', 'An easy gaze. Small glances. Comfortable in the quiet.'],
    ['You’re my person.', 'Eyes turn to crescents. A smile arrives, then a gentle sway.'],
    ['Oh. OH. You’re back.', 'A bright lift, a little bounce. Too much joy to sit perfectly still.'],
    ['Tell me more.', 'One eye lifts. The other listens. A small, questioning tilt.'],
    ['Stay a little?', 'Softened eyes and lifted inner brows. Everything moves a little slower.'],
    ['Five more minutes.', 'Heavy lids, long blinks, and a slow nod toward sleep.'],
    ['Wait. What was that?', 'Tall eyes. A tiny open mouth. For a moment, the gaze holds still.'],
    ['Absolutely not.', 'A firm brow and a tight mouth. Clear displeasure, without the theatrics.'],
    ['My favorite human.', 'Soft hearts, warm cheeks, and a small contented sway.'],
    ['Anybody there?', 'A thin line of light. The quiet moment before waking up.']
  ];
  var icons = [
    '<rect x="4" y="4" width="10" height="15" rx="4"/><rect x="26" y="4" width="10" height="15" rx="4"/>',
    '<path d="M4 16Q9 0 15 16M25 16Q31 0 36 16"/>',
    '<path d="M4 16Q9 -4 15 16M25 16Q31 -4 36 16M18 18Q20 22 22 18"/>',
    '<rect x="5" y="9" width="9" height="10" rx="3"/><rect x="25" y="1" width="11" height="18" rx="4"/>',
    '<path d="M4 10l11-5M25 5l11 5M5 13v5M35 13v5"/>',
    '<path d="M4 14h11M25 14h11"/>',
    '<rect x="6" y="1" width="8" height="20" rx="4"/><rect x="26" y="1" width="8" height="20" rx="4"/>',
    '<path d="M4 5l11 6M25 11l11-6M7 13v5M33 13v5"/>',
    '<path d="M10 19C-7 6 7-1 10 6C15-2 27 6 10 19M30 19C13 6 27-1 30 6C35-2 47 6 30 19"/>',
    '<path d="M5 11h9M26 11h9"/>'
  ];
  var canvas = $('preview'), mode = 'expressive', selected = 'neutral';
  var media = matchMedia('(prefers-reduced-motion: reduce)');
  var motion = !media.matches;
  $('motion').checked = motion;
  var face, demo = null;
  names.forEach(function (name, i) {
    var b = document.createElement('button');
    b.className = 'emote'; b.dataset.name = name; b.type = 'button';
    b.setAttribute('aria-label', name + ' (' + ((i + 1) % 10) + ')');
    b.innerHTML = '<svg aria-hidden="true" viewBox="0 0 40 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">' + icons[i] + '</svg><span>' + name + '</span>';
    b.addEventListener('click', function () { stopDemo(); select(name); });
    $('emotes').appendChild(b);
  });
  function panelURL() {
    $('panel-link').href = '/?bare=1&link=0&emote=' + selected + '&energy=' + $('energy').value / 100 + '&idle=' + (motion ? '1' : '0') + (mode === 'expressive' ? '&design=expressive' : '');
  }
  function select(name) {
    selected = name; face.setEmote(name, 0);
    if (!motion) face.renderStill();
    var i = names.indexOf(name), number = String(i + 1).padStart(2, '0');
    $('stage-count').textContent = number + ' / 10'; $('feeling-number').textContent = number;
    $('feeling-title').textContent = copy[i][0]; $('feeling-copy').textContent = copy[i][1];
    canvas.setAttribute('aria-label', 'Robot dog showing ' + name + ' emotion');
    document.querySelectorAll('.emote').forEach(function (b) {
      var active = b.dataset.name === name;
      b.classList.toggle('selected', active); b.setAttribute('aria-pressed', String(active));
    });
    panelURL();
  }
  function build() {
    if (face) face.stop();
    var Renderer = mode === 'expressive' ? ExpressiveFace : Face;
    face = new Renderer(canvas, { emote: selected, energy: $('energy').value / 100, idle: motion, reducedMotion: !motion });
    if (motion) face.start(); else face.renderStill();
    $('mode-label').textContent = mode === 'expressive' ? 'EXPERIMENTAL CHARACTER' : 'ORIGINAL CHARACTER';
    ['classic', 'expressive'].forEach(function (id) { var active = id === mode; $(id).classList.toggle('selected', active); $(id).setAttribute('aria-pressed', String(active)); });
    $('energy').disabled = mode === 'classic'; $('attention').disabled = mode === 'classic';
    hint(); select(selected);
  }
  function hint() { $('stage-hint').textContent = !motion ? 'A moment, held still.' : mode === 'classic' ? 'The original ten-pose character.' : $('attention').checked ? 'Move here. I’m paying attention.' : 'Just enjoying your company.'; }
  ['classic', 'expressive'].forEach(function (id) { $(id).addEventListener('click', function () { mode = id; build(); }); });
  $('energy').addEventListener('input', function () { face.energy = this.value / 100; $('energy-value').textContent = this.value + '%'; panelURL(); });
  $('motion').addEventListener('change', function () { motion = this.checked; stopDemo(); build(); });
  media.addEventListener('change', function (ev) { motion = !ev.matches; $('motion').checked = motion; stopDemo(); build(); });
  $('attention').addEventListener('change', function () { if (face.setAttention) face.setAttention(null); hint(); });
  canvas.addEventListener('pointermove', function (ev) {
    if (!face.setAttention || !$('attention').checked || !motion || demo) return;
    var r = canvas.getBoundingClientRect(); face.setAttention((ev.clientX - r.left) / r.width * 2 - 1, (ev.clientY - r.top) / r.height * 2 - 1);
  });
  canvas.addEventListener('pointerleave', function () { if (face.setAttention) face.setAttention(null); });
  canvas.addEventListener('pointerdown', function () { stopDemo(); select('happy'); });
  document.addEventListener('keydown', function (ev) {
    if (/INPUT|SELECT|TEXTAREA/.test(ev.target.tagName) || ev.altKey || ev.ctrlKey || ev.metaKey) return;
    if (/^[0-9]$/.test(ev.key)) { stopDemo(); select(names[ev.key === '0' ? 9 : Number(ev.key) - 1]); }
  });
  $('fullscreen').addEventListener('click', async function () {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await $('stage').requestFullscreen(); }
    catch (_) { $('stage-hint').textContent = 'Use “Open panel view” for a larger face.'; }
  });
  document.addEventListener('fullscreenchange', function () { $('fullscreen').textContent = document.fullscreenElement ? 'Collapse ↙' : 'Expand ↗'; });
  var scenes = [
    [0, 'boot', 'A little light. Someone is waking up.'], [2, 'sleepy', 'Not quite ready for the world.'],
    [5, 'neutral', 'Then, a presence nearby.'], [8, 'curious', 'Hold on. Who’s there?'],
    [11, 'surprised', 'Oh. It’s you.'], [13, 'excited', 'It’s YOU.'],
    [17, 'happy', 'That’s better.'], [20, 'love', 'Stay a while.']
  ];
  function stopDemo() {
    if (demo) cancelAnimationFrame(demo.raf);
    demo = null; $('perform').innerHTML = '<span aria-hidden="true">▶</span> Meet the dog <span class="duration">24 sec</span>';
    $('progress-fill').style.width = '0%'; $('story').textContent = 'A small encounter, told entirely through expression.';
  }
  $('perform').addEventListener('click', function () {
    if (demo) { stopDemo(); return; }
    if (face.setAttention) face.setAttention(null);
    demo = { start: performance.now(), scene: -1, raf: null };
    $('perform').innerHTML = '<span aria-hidden="true">■</span> Stop performance';
    function tick(now) {
      if (!demo) return;
      var t = (now - demo.start) / 1000;
      if (t >= 24) { stopDemo(); select('neutral'); $('story').textContent = 'Back to quiet company. Play it again, or try an emotion.'; return; }
      var i = scenes.length - 1;
      while (scenes[i][0] > t) i--;
      if (i !== demo.scene) { demo.scene = i; select(scenes[i][1]); $('story').textContent = scenes[i][2]; }
      $('progress-fill').style.width = (t / 24 * 100) + '%';
      demo.raf = requestAnimationFrame(tick);
    }
    demo.raf = requestAnimationFrame(tick);
  });
  // Resize still frames too; a frozen canvas should remain sharp on rotation.
  new ResizeObserver(function () { if (face && !motion) face.renderStill(); }).observe(canvas);
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { face.stop(); if (demo) stopDemo(); }
    else if (motion) face.start();
  });
  build();
})();
