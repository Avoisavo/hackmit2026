/* Wires the face to the outside world: the SSE channel from server.py, plus
 * keyboard shortcuts so the dog is demoable before any real brain exists. */
(function () {
  'use strict';

  var params = new URLSearchParams(location.search);
  var canvas = document.getElementById('face');

  var Renderer = params.get('design') === 'expressive' ? ExpressiveFace : Face;
  var face = new Renderer(canvas, {
    color: params.get('color') || Face.DEFAULT_COLOR,
    idle: params.get('idle') !== '0',
    energy: params.has('energy') ? Math.max(0, Math.min(1, Number(params.get('energy')) || 0)) : .65
  });

  // ?still=1 draws a single frame and stops -- for headless screenshots.
  if (params.get('still') === '1') {
    var st = params.get('emote');
    face.setEmote(st && Face.EMOTES[st] ? st : 'neutral', 0);
    face.renderStill();
    return;
  }

  face.start();

  // ?emote=angry pins one pose -- handy for checking a face on the real panel
  // without needing a keyboard or a brain attached.
  var pinned = params.get('emote');
  if (pinned && Face.EMOTES[pinned]) {
    face.setEmote(pinned, 0);
  } else {
    face.setEmote('boot', 0);
    setTimeout(function () { face.setEmote('neutral', 0); }, 900);
  }

  if (params.get('bare') === '1') document.body.classList.add('bare');

  // -- keyboard -------------------------------------------------------------
  var keys = Face.NAMES.slice(0, 10);          // 1..9 then 0
  var list = document.getElementById('keys');
  keys.forEach(function (name, i) {
    var li = document.createElement('li');
    li.innerHTML = '<b>' + ((i + 1) % 10) + '</b>' + name;
    list.appendChild(li);
  });

  var help = document.getElementById('help');
  document.addEventListener('keydown', function (ev) {
    var k = ev.key;
    if (k >= '0' && k <= '9') {
      var idx = (k === '0') ? 9 : (parseInt(k, 10) - 1);
      if (keys[idx]) face.setEmote(keys[idx], 0);
      return;
    }
    if (k === 'h') help.hidden = !help.hidden;
    if (k === 'f') {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    }
  });

  // Tapping the screen cycles emotes -- useful if the panel is a touchscreen
  // and there is no keyboard anywhere near the dog.
  var at = 0;
  canvas.addEventListener('pointerdown', function () {
    at = (at + 1) % keys.length;
    face.setEmote(keys[at], 0);
  });

  // -- control channel ------------------------------------------------------
  var link = document.getElementById('link');
  var es = null;
  var retry = 1000;

  function connect() {
    es = new EventSource('/events');

    es.onopen = function () {
      retry = 1000;
      link.textContent = 'connected';
      link.classList.add('dim');
    };

    es.onmessage = function (ev) {
      var d;
      try { d = JSON.parse(ev.data); } catch (e) { return; }
      if (d && d.name) face.setEmote(d.name, d.hold || 0);
    };

    // The dog must not go blank because the brain restarted -- keep the face
    // running on its idle loop and reconnect in the background, forever.
    es.onerror = function () {
      link.textContent = 'offline';
      es.close();
      setTimeout(connect, retry);
      retry = Math.min(retry * 2, 10000);
    };
  }

  // ?link=0 skips the control channel entirely. The face then runs purely on
  // its idle loop -- which is also the only way to screenshot this page with a
  // headless browser, since an open SSE stream never reaches network-idle.
  if (params.get('link') === '0') {
    link.textContent = 'standalone';
  } else {
    connect();
  }
})();
