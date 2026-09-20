/* Twinkle's face pack. Canvas only, no dependencies or connection to the robot.
 * Expression names are the public contract. Faces react to events, never score children.
 */
(function (global) {
  'use strict';
  // Two light shapes: size, spacing, gaze, tilt, asymmetry, and smile curvature.
  // `closed` continuously reshapes an open light into a rounded ribbon.
  var POSES = {
    'Ready':         { w:204, h:210, gap:169, closed:0, arch:0, gx:0, gy:0, tilt:0, asym:0, spark:0 },
    'Watching':      { w:214, h:146, gap:159, closed:0, arch:0, gx:0, gy:38, tilt:0, asym:0, spark:0 },
    'Encourage':     { w:202, h:150, gap:168, closed:1, arch:41, gx:0, gy:12, tilt:-3, asym:0, spark:0 },
    'Thinking':      { w:187, h:191, gap:159, closed:0, arch:0, gx:24, gy:-16, tilt:-7, asym:39, spark:0 },
    'Go':            { w:216, h:244, gap:174, closed:0, arch:0, gx:0, gy:-15, tilt:0, asym:0, spark:0 },
    'Celebrate':     { w:220, h:145, gap:166, closed:1, arch:100, gx:0, gy:5, tilt:0, asym:0, spark:1 },
    'Rest':          { w:158, h:60, gap:154, closed:1, arch:-12, gx:0, gy:26, tilt:0, asym:0, spark:0 },
    'Soft confused': { w:191, h:196, gap:175, closed:0, arch:0, gx:-8, gy:8, tilt:11, asym:-22, spark:0 }
  };
  var NAMES = Object.keys(POSES), KEYS = Object.keys(POSES.Ready);
  function blend(a, b, t) {
    var p = {};
    KEYS.forEach(function (k) { p[k] = a[k] + (b[k] - a[k]) * t; });
    return p;
  }
  function lightShape(ctx, w, h, closed, arch) {
    // Match the original lab's soft square silhouette. Both contours share
    // sampled perimeter points, so smiling ribbons morph without crossfades.
    ctx.beginPath();
    for (var i = 0; i <= 64; i++) {
      var angle = i / 64 * Math.PI * 2, c = Math.cos(angle), s = Math.sin(angle);
      var openX = Math.sign(c) * Math.pow(Math.abs(c), .54) * w/2;
      var openY = Math.sign(s) * Math.pow(Math.abs(s), .54) * h/2;
      var smileX = c*w/2, smileY = -arch*(1-c*c) + s*17;
      var x = openX*(1-closed)+smileX*closed, y = openY*(1-closed)+smileY*closed;
      if (i === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }
    ctx.closePath(); ctx.fill(); ctx.shadowBlur = 0; ctx.stroke();
  }
  function gloss(ctx, x, y, w, h) {
    var r = h/2;
    ctx.beginPath(); ctx.moveTo(x+r,y); ctx.lineTo(x+w-r,y);
    ctx.quadraticCurveTo(x+w,y,x+w,y+r); ctx.quadraticCurveTo(x+w,y+h,x+w-r,y+h);
    ctx.lineTo(x+r,y+h); ctx.quadraticCurveTo(x,y+h,x,y+r);
    ctx.quadraticCurveTo(x,y,x+r,y); ctx.fill();
  }
  function sparkle(ctx, x, y, r) {
    ctx.beginPath(); ctx.moveTo(x,y-r); ctx.quadraticCurveTo(x+3,y-3,x+r,y);
    ctx.quadraticCurveTo(x+3,y+3,x,y+r); ctx.quadraticCurveTo(x-3,y+3,x-r,y);
    ctx.quadraticCurveTo(x-3,y-3,x,y-r); ctx.fill();
  }
  function TwinkleFace(canvas, options) {
    var opts = options || {};
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.name = Object.prototype.hasOwnProperty.call(POSES, opts.emote) ? opts.emote : 'Ready';
    this.from = this.to = POSES[this.name];
    this.t = 1; this.age = 0; this.clock = 0;
    this.motion = opts.motion !== undefined ? opts.motion : !global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.energy = .75;
    this.gaze = {x:0,y:0}; this.gazeTarget = {x:0,y:0}; this.lookAt = 1.3; this.attention = null; this.blinkAt = 3.2; this.blink = -1;
    this._raf = null; this._last = 0;
  }
  TwinkleFace.NAMES = NAMES;
  TwinkleFace.prototype.current = function () {
    var t = this.t * this.t * (3 - 2 * this.t);
    return blend(this.from, this.to, t);
  };
  TwinkleFace.prototype.setEmote = function (name) {
    if (!Object.prototype.hasOwnProperty.call(POSES, name)) return false;
    this.from = this.current(); this.to = POSES[name];
    this.name = name; this.t = this.motion ? 0 : 1; this.age = 0; this.blink = -1;
    this.attention = null; this.gazeTarget = {x:0,y:0}; this.lookAt = 1.3;
    this.blinkAt = 2.8 + Math.random() * 2;
    this.canvas.setAttribute('aria-label', 'Twinkle — ' + name);
    if (!this.motion) this.draw();
    return true;
  };
  TwinkleFace.prototype.step = function (dt) {
    this.t = Math.min(1, this.t + dt / (this.name === 'Rest' ? .9 : .48));
    if (!this.motion) { this.t = 1; return; }
    this.age += dt; this.clock += dt;
    this.lookAt -= dt;
    if (this.attention) this.gazeTarget = this.attention;
    else if (this.lookAt <= 0) {
      this.lookAt = 1.6 + Math.random()*2.6;
      this.gazeTarget = Math.random() < .4 ? {x:0,y:0} : {x:(Math.random()-.5)*48,y:(Math.random()-.5)*24};
    }
    var follow = 1-Math.exp(-dt*6);
    this.gaze.x += (this.gazeTarget.x-this.gaze.x)*follow;
    this.gaze.y += (this.gazeTarget.y-this.gaze.y)*follow;
    this.blinkAt -= dt;
    if (this.blinkAt <= 0 && this.blink < 0) { this.blink = 0; this.blinkAt = 3 + Math.random() * 3; }
    if (this.blink >= 0) { this.blink += dt; if (this.blink >= .20) this.blink = -1; }
  };
  TwinkleFace.prototype.setAttention = function (x,y) {
    this.attention = x === null ? null : {x:Math.max(-1,Math.min(1,x))*38,y:Math.max(-1,Math.min(1,y))*23};
    if (x === null) { this.gazeTarget = {x:0,y:0}; this.lookAt = 1.5; }
  };
  TwinkleFace.prototype.setMotion = function (enabled) {
    this.motion = enabled; this.blink = -1;
    if (enabled) this.start(); else { this.stop(); this.t = 1; this.draw(); }
  };
  TwinkleFace.prototype.start = function () {
    if (this._raf !== null || !this.motion) { this.draw(); return; }
    var self = this; this._last = performance.now();
    function frame(now) {
      self.step(Math.min((now - self._last) / 1000, .05)); self._last = now;
      self.draw(); self._raf = requestAnimationFrame(frame);
    }
    this._raf = requestAnimationFrame(frame);
  };
  TwinkleFace.prototype.stop = function () {
    if (this._raf !== null) cancelAnimationFrame(this._raf);
    this._raf = null;
  };
  TwinkleFace.prototype.draw = function () {
    var canvas = this.canvas, ctx = this.ctx;
    var dpr = Math.min(global.devicePixelRatio || 1, 2);
    var width = Math.max(1, Math.round((canvas.clientWidth || 1000) * dpr));
    var height = Math.max(1, Math.round((canvas.clientHeight || 600) * dpr));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    ctx.setTransform(1,0,0,1,0,0);
    var backdrop = ctx.createRadialGradient(width/2,height/2,0,width/2,height/2,Math.max(width,height)*.7);
    backdrop.addColorStop(0,'#141722'); backdrop.addColorStop(1,'#080a10');
    ctx.fillStyle = backdrop; ctx.fillRect(0,0,width,height);
    var k = Math.min(width / 1000, height / 600), p = this.current();
    var time = this.motion ? this.clock : 0, age = this.motion ? this.age : 0;
    var e = this.motion ? this.energy : 0;
    var bob = Math.sin(time * 1.5) * 3 * e, tilt = p.tilt;
    // Arrival gestures settle; constant high-energy motion would compete with learning.
    var settle = Math.exp(-age / 3);
    if (this.name === 'Go') bob -= Math.abs(Math.sin(age * 6)) * 19 * e * settle;
    if (this.name === 'Celebrate') { bob -= Math.abs(Math.sin(age * 5)) * 24 * e * settle; tilt += Math.sin(age * 3) * 3 * e * settle; }
    if (this.name === 'Encourage') bob += Math.sin(Math.min(age, 1.2) / 1.2 * Math.PI) * 13 * e;
    if (this.name === 'Thinking') tilt += Math.sin(time*1.6)*3*e;
    if (this.name === 'Ready') tilt += Math.sin(time*.9)*1.8*e;
    bob -= Math.sin(age*10)*Math.exp(-age*3)*11*e;
    if (this.name === 'Rest') bob += Math.sin(time * .8) * 5 * e;
    ctx.save(); ctx.translate(width/2,height/2+bob*k); ctx.scale(k,k); ctx.rotate(tilt*Math.PI/180);
    var blink = this.motion && this.blink >= 0 ? Math.sin(this.blink/.20*Math.PI) : 0;
    var breath = 1 + Math.sin(time*1.5) * .012 * e;
    var gazeScale = !this.motion || this.name === 'Rest' || this.name === 'Watching' ? 0 : this.name === 'Thinking' ? .45 : 1;
    var gazeX = this.gaze.x*gazeScale, gazeY = this.gaze.y*gazeScale;
    [-1,1].forEach(function (side) {
      var x = side*p.gap + p.gx + gazeX, y = p.gy + side*p.asym*.3 + gazeY;
      var h = Math.max(10,(p.h + side*p.asym)*(1-blink*.94));
      var w = p.w - side*p.asym*.15;
      ctx.save(); ctx.translate(x,y);
      ctx.fillStyle = '#FFC24B'; ctx.strokeStyle = '#FFC24B'; ctx.lineWidth = 8;
      ctx.lineJoin = 'round'; ctx.lineCap = 'round';
      ctx.shadowColor = '#ffbe44'; ctx.shadowBlur = 29*k;
      lightShape(ctx,w*breath,h*breath,p.closed,p.arch*(1-blink*.75));
      ctx.save(); ctx.clip(); ctx.globalAlpha = .23*(1-p.closed);
      ctx.fillStyle = '#fff6d8';
      gloss(ctx,-w*.34,-h*.34,w*.31,Math.max(3,h*.17));
      ctx.restore();
      ctx.restore();
    });
    // A single tiny glint belongs to Celebrate; everything else is the two eyes.
    ctx.globalAlpha = p.spark; ctx.fillStyle = '#ffe7b4';
    sparkle(ctx,310,-105,18);
    ctx.restore();
  };
  global.TwinkleFace = TwinkleFace;
})(window);
