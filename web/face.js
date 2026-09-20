/* Robot dog face -- animated vector eyes.
 *
 * Everything is drawn in a fixed 1000x600 "design space" and scaled to fit
 * whatever panel it lands on, so the face looks right at 1024x600, 1280x800
 * or anything else without retuning a single number.
 *
 * An emote is nothing but a set of eye parameters. Switching emotes tweens
 * between parameter sets; the overshoot on the tween is what makes it read as
 * alive rather than as a slideshow of faces.
 */
(function (global) {
  'use strict';

  var DESIGN_W = 1000;
  var DESIGN_H = 600;
  var HOME_X = 172;          // each eye sits this far from center
  var DEFAULT_COLOR = '#FFC24B';

  // The full eye model. Every emote is a partial override of this.
  var BASE = {
    x: 0, y: 0,        // offset from the eye's home position
    w: 190, h: 190,    // size
    r: 70,             // corner radius
    tilt: 0,           // eye rotation, degrees
    lidU: 0,           // upper lid coverage, 0..1 of eye height
    lidL: 0,           // lower lid coverage, 0..1
    lidUTilt: 0,       // upper lid angle, degrees (+ = inner corner down = angry)
    lidLCurve: 0,      // lower lid arc height, 0..1 (the "^^" happy squint)
    glow: 1,           // glow multiplier
    shape: 0           // 0 = rounded rect, 1 = heart
  };

  var KEYS = Object.keys(BASE);

  // Mirroring an eye flips anything with a horizontal sense to it.
  function mirror(p) {
    var m = {};
    for (var i = 0; i < KEYS.length; i++) m[KEYS[i]] = p[KEYS[i]];
    m.x = -p.x;
    m.tilt = -p.tilt;
    m.lidUTilt = -p.lidUTilt;
    return m;
  }

  function build(over) {
    var p = {};
    for (var i = 0; i < KEYS.length; i++) {
      var k = KEYS[i];
      p[k] = (over && over[k] !== undefined) ? over[k] : BASE[k];
    }
    return p;
  }

  // An emote: symmetric `eye` params, optional per-side overrides, and how it
  // should arrive. `back` overshoots (perky), `soft` settles (heavy moods).
  var EMOTES = {
    neutral:   { eye: {},                                                              ease: 'back', dur: 0.32 },
    happy:     { eye: { h: 152, y: 14, r: 64, lidLCurve: 0.60 },                       ease: 'back', dur: 0.28 },
    excited:   { eye: { w: 216, h: 206, r: 96, y: -10, glow: 1.30 },                    ease: 'back', dur: 0.24 },
    curious:   { eye: {},
                 l:   { y: -36, h: 162, w: 172, tilt: 10 },
                 r:   { y: 20, h: 214, w: 214, tilt: 10 },                             ease: 'back', dur: 0.40 },
    sad:       { eye: { y: 30, w: 172, h: 150, r: 56, lidU: 0.42, lidUTilt: -16,
                       glow: 0.65 },                                                    ease: 'soft', dur: 0.55 },
    sleepy:    { eye: { y: 26, h: 172, r: 58, lidU: 0.66, glow: 0.6 },                 ease: 'soft', dur: 0.70 },
    surprised: { eye: { w: 194, h: 242, r: 86, y: -8, glow: 1.2 },                     ease: 'back', dur: 0.18 },
    angry:     { eye: { h: 188, r: 54, lidU: 0.40, lidUTilt: 22, glow: 1.1 },          ease: 'back', dur: 0.22, color: '#FF7A45' },
    love:      { eye: { shape: 1, w: 204, h: 192, glow: 1.3 },                         ease: 'back', dur: 0.30, color: '#FF5C8A' },
    boot:      { eye: { h: 10, r: 5, w: 148, glow: 0.8 },                              ease: 'soft', dur: 0.35 }
  };

  var NAMES = Object.keys(EMOTES);

  // `eye` is the symmetric pose: the right eye is its mirror. An emote that
  // wants asymmetry supplies `l`/`r`, which are taken literally -- no mirroring
  // -- so a head-tilt can lean both eyes the same way instead of splaying them.
  function resolve(name, poses) {
    var e = (poses || EMOTES)[name] || EMOTES.neutral;
    var sym = build(e.eye);
    return {
      l: e.l ? build(merge(e.eye, e.l)) : sym,
      r: e.r ? build(merge(e.eye, e.r)) : mirror(sym),
      ease: e.ease || 'back',
      dur: e.dur || 0.3,
      color: e.color || null
    };
  }

  function merge(a, b) {
    var o = {}, k;
    for (k in a) if (a.hasOwnProperty(k)) o[k] = a[k];
    for (k in b) if (b.hasOwnProperty(k)) o[k] = b[k];
    return o;
  }

  // -- easing ---------------------------------------------------------------
  function easeOutBack(t) {
    var c1 = 1.70158, c3 = c1 + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
  }
  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
  function lerp(a, b, t) { return a + (b - a) * t; }

  function lerpEye(a, b, t, shapeFromB) {
    var o = {};
    for (var i = 0; i < KEYS.length; i++) {
      var k = KEYS[i];
      o[k] = (k === 'shape') ? (shapeFromB ? b.shape : a.shape) : lerp(a[k], b[k], t);
    }
    return o;
  }

  // -- shapes ---------------------------------------------------------------
  function roundRect(ctx, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    var x = -w / 2, y = -h / 2;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  function heart(ctx, w, h) {
    var s = Math.min(w, h) / 2;
    ctx.beginPath();
    ctx.moveTo(0, s * 0.95);
    ctx.bezierCurveTo(-s * 1.55, -s * 0.15, -s * 0.72, -s * 1.30, 0, -s * 0.42);
    ctx.bezierCurveTo(s * 0.72, -s * 1.30, s * 1.55, -s * 0.15, 0, s * 0.95);
    ctx.closePath();
  }

  // -- the face -------------------------------------------------------------
  function Face(canvas, opts) {
    opts = opts || {};
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.color = opts.color || DEFAULT_COLOR;
    this.baseColor = this.color;
    this.idleOn = opts.idle !== false;
    this.bg = opts.bg || '#07080C';

    this.poses = opts.poses || EMOTES;
    var start = resolve(opts.emote || 'neutral', this.poses);
    this.from = { l: start.l, r: start.r };
    this.to = start;
    this.t = 1;
    this.name = opts.emote || 'neutral';

    this.blinkAt = 1.2 + Math.random() * 2;
    this.blinkT = -1;
    this.blinkDur = 0.14;
    this.blinkQueue = 0;
    this.lookAt = 1 + Math.random() * 2;
    this.look = { x: 0, y: 0 };
    this.lookTarget = { x: 0, y: 0 };
    this.breathe = Math.random() * 6.28;
    this.sleepy = 0;
    this.sinceEmote = 0;
    this.holdLeft = 0;

    this._off = [document.createElement('canvas'), document.createElement('canvas')];
    this._raf = null;
    this._last = 0;
  }

  Face.prototype.setEmote = function (name, hold) {
    if (!EMOTES[name]) return false;
    // Snapshot what is on screen right now so the tween starts from reality,
    // not from whatever the previous emote's resting pose was.
    var cur = this._current();
    this.from = { l: cur.l, r: cur.r };
    this.to = resolve(name, this.poses);
    this.t = 0;
    this.name = name;
    this.holdLeft = hold > 0 ? hold : 0;
    this.sinceEmote = 0;
    this.sleepy = 0;
    return true;
  };

  Face.prototype._current = function () {
    var e = this.t >= 1 ? 1 : (this.to.ease === 'soft' ? easeOutCubic(this.t) : easeOutBack(this.t));
    var half = this.t >= 0.5;
    return {
      l: lerpEye(this.from.l, this.to.l, e, half),
      r: lerpEye(this.from.r, this.to.r, e, half)
    };
  };

  // Draw exactly one settled frame with no animation loop. Used for headless
  // screenshots: an endless requestAnimationFrame loop keeps virtual time busy
  // so --virtual-time-budget never fires and the capture races.
  Face.prototype.renderStill = function () {
    this.t = 1;          // finish any in-flight tween
    this.idleOn = false; // no blink/breathe/saccade modulation
    this._draw();
  };

  Face.prototype.start = function () {
    if (this._raf) return;
    var self = this;
    this._last = performance.now();
    var tick = function (now) {
      var dt = Math.min((now - self._last) / 1000, 0.05);
      self._last = now;
      self._step(dt);
      self._draw();
      self._raf = requestAnimationFrame(tick);
    };
    this._raf = requestAnimationFrame(tick);
  };

  Face.prototype.stop = function () {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
  };

  Face.prototype._step = function (dt) {
    if (this.t < 1) this.t = Math.min(1, this.t + dt / this.to.dur);

    if (this.holdLeft > 0) {
      this.holdLeft -= dt;
      if (this.holdLeft <= 0) { this.holdLeft = 0; this.setEmote('neutral', 0); }
    }

    if (!this.idleOn) return;

    this.sinceEmote += dt;
    this.breathe += dt * 1.6;

    // Blinks, occasionally doubled -- perfectly regular blinking looks dead.
    this.blinkAt -= dt;
    if (this.blinkAt <= 0 && this.blinkT < 0) {
      this.blinkT = 0;
      this.blinkQueue = Math.random() < 0.22 ? 1 : 0;
      this.blinkAt = 2.4 + Math.random() * 4.2;
    }
    if (this.blinkT >= 0) {
      this.blinkT += dt;
      if (this.blinkT > this.blinkDur) {
        this.blinkT = this.blinkQueue > 0 ? 0 : -1;
        if (this.blinkQueue > 0) this.blinkQueue--;
      }
    }

    // Saccades: small darting glances, with a bias back toward center.
    this.lookAt -= dt;
    if (this.lookAt <= 0) {
      this.lookAt = 1.4 + Math.random() * 3.2;
      if (Math.random() < 0.35) {
        this.lookTarget.x = 0; this.lookTarget.y = 0;
      } else {
        this.lookTarget.x = (Math.random() * 2 - 1) * 26;
        this.lookTarget.y = (Math.random() * 2 - 1) * 15;
      }
    }
    var k = Math.min(1, dt * 7);
    this.look.x += (this.lookTarget.x - this.look.x) * k;
    this.look.y += (this.lookTarget.y - this.look.y) * k;

    // Nothing has happened in a while -> the dog gets drowsy on its own.
    var want = this.sinceEmote > 45 ? clamp((this.sinceEmote - 45) / 25, 0, 0.5) : 0;
    this.sleepy += (want - this.sleepy) * Math.min(1, dt * 0.6);
  };

  Face.prototype._modulate = function (p) {
    var o = {}, i;
    for (i = 0; i < KEYS.length; i++) o[KEYS[i]] = p[KEYS[i]];
    if (!this.idleOn) return o;

    var blink = this.blinkT >= 0 ? Math.sin(Math.PI * clamp(this.blinkT / this.blinkDur, 0, 1)) : 0;
    var breath = 1 + Math.sin(this.breathe) * 0.012;

    o.h = o.h * (1 - 0.94 * blink) * breath;
    o.w = o.w * breath;
    o.x += this.look.x;
    o.y += this.look.y;
    o.lidU = clamp(o.lidU + this.sleepy, 0, 0.95);
    o.r = Math.min(o.r, o.w / 2, o.h / 2);
    return o;
  };

  Face.prototype._eyeToOffscreen = function (idx, p, k, color) {
    var S = Math.max(p.w, p.h) * 1.9;              // design units, room for tilt
    var px = Math.max(8, Math.ceil((this.fixedBuffer ? 600 : S) * k));
    var off = this._off[idx];
    if (off.width !== px || off.height !== px) { off.width = px; off.height = px; }
    var c = off.getContext('2d');
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, px, px);
    c.setTransform(k, 0, 0, k, px / 2, px / 2);
    c.rotate(p.tilt * Math.PI / 180);

    c.fillStyle = color;
    if (p.shape >= 0.5) heart(c, p.w, p.h); else roundRect(c, p.w, p.h, p.r);
    c.fill();

    // A glassy highlight, clipped to the eye, before the lids cut in.
    c.save();
    c.globalCompositeOperation = 'source-atop';
    c.globalAlpha = 0.20;
    c.fillStyle = '#FFFFFF';
    c.translate(-p.w * 0.20, -p.h * 0.26);
    roundRect(c, p.w * 0.30, p.h * 0.18, p.h * 0.09);
    c.fill();
    c.restore();

    // Lids are carved out of the eye rather than painted over it, so they work
    // on any background.
    c.globalCompositeOperation = 'destination-out';
    c.fillStyle = '#000';

    if (p.lidU > 0.001) {
      c.save();
      c.translate(0, -p.h / 2 + p.lidU * p.h);
      c.rotate(p.lidUTilt * Math.PI / 180);
      c.fillRect(-S, -S, 2 * S, S);
      c.restore();
    }

    if (p.lidLCurve > 0.001) {
      var yb = p.h / 2;
      var ex = p.w * 0.72;
      c.beginPath();
      c.moveTo(-S, yb);
      c.lineTo(-ex, yb);
      c.quadraticCurveTo(0, yb - 2 * p.lidLCurve * p.h, ex, yb);
      c.lineTo(S, yb);
      c.lineTo(S, S);
      c.lineTo(-S, S);
      c.closePath();
      c.fill();
    } else if (p.lidL > 0.001) {
      c.save();
      c.translate(0, p.h / 2 - p.lidL * p.h);
      c.fillRect(-S, 0, 2 * S, S);
      c.restore();
    }

    c.globalCompositeOperation = 'source-over';
    return off;
  };

  Face.prototype._draw = function () {
    var canvas = this.canvas, ctx = this.ctx;
    var dpr = global.devicePixelRatio || 1;
    var cssW = canvas.clientWidth || canvas.width;
    var cssH = canvas.clientHeight || canvas.height;
    var w = Math.max(1, Math.round(cssW * dpr));
    var h = Math.max(1, Math.round(cssH * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }

    var k = Math.min(w / DESIGN_W, h / DESIGN_H);   // design unit -> device px
    var ox = w / 2, oy = h / 2;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    var g = ctx.createRadialGradient(ox, oy, 0, ox, oy, Math.max(w, h) * 0.75);
    g.addColorStop(0, '#12141C');
    g.addColorStop(1, this.bg);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    var cur = this._current();
    var color = this.to.color || this.baseColor;

    var sides = [['l', cur.l, -HOME_X], ['r', cur.r, HOME_X]];
    for (var i = 0; i < sides.length; i++) {
      var p = this._modulate(sides[i][1], i);
      if (p.h < 0.5 || p.w < 0.5) continue;
      var off = this._eyeToOffscreen(i, p, k, color);
      var ex = ox + (sides[i][2] + p.x) * k;
      var ey = oy + p.y * k;
      var half = off.width / 2;

      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = 30 * k * p.glow;
      ctx.drawImage(off, ex - half, ey - half);
      ctx.shadowBlur = 16 * k * p.glow;      // second pass thickens the bloom
      ctx.drawImage(off, ex - half, ey - half);
      ctx.restore();
    }
    if (this._drawDetails) this._drawDetails(ctx, k, ox, oy);
  };

  Face.EMOTES = EMOTES;
  Face.NAMES = NAMES;
  Face.DEFAULT_COLOR = DEFAULT_COLOR;
  global.Face = Face;
})(window);
