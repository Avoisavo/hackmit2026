/* Production display: shared labv2 renderer, SSE control, and timed return to Ready. */
(function () {
  'use strict';
  var canvas = document.getElementById('twinkle');
  var equation = document.getElementById('equation');
  var params = new URLSearchParams(location.search);
  var media = matchMedia('(prefers-reduced-motion: reduce)');
  var face = new TwinkleFace(canvas, { motion: !media.matches && params.get('motion') !== '0' });
  var holdTimer = null;
  var aliases = {neutral:'Ready',happy:'Encourage',excited:'Go',curious:'Thinking',sad:'Encourage',sleepy:'Rest',surprised:'Soft confused',angry:'Soft confused',love:'Celebrate',boot:'Ready'};
  function apply(data) {
    var name = Object.prototype.hasOwnProperty.call(aliases,data.name) ? aliases[data.name] : data.name;
    if (!face.setEmote(name)) return false;
    clearTimeout(holdTimer);
    equation.hidden = !(name === 'Celebrate' && data.result === true);
    if (Number.isFinite(data.hold) && data.hold > 0) {
      holdTimer = setTimeout(function () { apply({name:'Ready'}); }, data.hold*1000);
    }
    return true;
  }
  apply({name:params.get('emote') || 'Ready',result:params.get('result') === '1'});
  face.start();
  new ResizeObserver(function () { face.draw(); }).observe(canvas);
  media.addEventListener('change',function (ev) { face.setMotion(!ev.matches && params.get('motion') !== '0'); });
  document.addEventListener('keydown',function (ev) {
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if (/^[1-8]$/.test(ev.key)) apply({name:TwinkleFace.NAMES[Number(ev.key)-1]});
  });
  canvas.addEventListener('pointerdown',function () {
    apply({name:TwinkleFace.NAMES[(TwinkleFace.NAMES.indexOf(face.name)+1)%TwinkleFace.NAMES.length]});
  });
  // EventSource handles reconnects. The face stays alive while the controller is offline.
  if (params.get('link') !== '0') {
    var events = new EventSource('/events');
    events.onmessage = function (event) {
      try { var data = JSON.parse(event.data); if (data && typeof data.name === 'string') apply(data); } catch (_) {}
    };
  }
})();
