/* Optional character direction. Shares the original renderer and emote API. */
(function (global) {
  'use strict';
  var POSES = {
    neutral: { eye: { w: 208, h: 214, r: 86, lidU: .06 }, dur: .42 },
    happy: { eye: { w: 222, h: 166, r: 82, y: 8, lidLCurve: .66 }, dur: .38 },
    excited: { eye: { w: 236, h: 220, r: 94, y: -18, lidLCurve: .30, glow: 1.15 }, dur: .28 },
    curious: { eye: {}, l: { w: 166, h: 164, y: 14, tilt: -9, lidU: .18 }, r: { w: 222, h: 246, y: -24, tilt: -9, r: 92 }, dur: .48 },
    sad: { eye: { w: 190, h: 170, y: 28, r: 65, lidU: .36, lidUTilt: -22, glow: .65 }, ease: 'soft', dur: .8 },
    sleepy: { eye: { w: 206, h: 114, y: 36, r: 52, lidU: .68, glow: .55 }, ease: 'soft', dur: 1.1 },
    surprised: { eye: { w: 146, h: 254, r: 73, y: -16, glow: 1.1 }, dur: .2 },
    angry: { eye: { w: 222, h: 170, r: 48, lidU: .36, lidUTilt: 27 }, dur: .25, color: '#FF9566' },
    love: { eye: { shape: 1, w: 226, h: 226, y: -8, glow: 1.05 }, dur: .55, color: '#FF8DA8' },
    boot: { eye: { w: 132, h: 12, r: 6, glow: .6 }, ease: 'soft', dur: .6 }
  };
  // Mouth curve, opening, brow angle, brow lift, cheek opacity.
  var ACCENTS = {
    neutral: [9, 0, 0, 0, 0], happy: [28, 0, 0, 0, .4],
    excited: [32, 24, 0, 0, .6], curious: [3, 0, -.25, 1, 0],
    sad: [-16, 0, -.30, 1, 0], sleepy: [0, 0, 0, 0, 0],
    surprised: [0, 25, 0, 1, 0], angry: [-6, 0, .32, 1, 0],
    love: [23, 0, 0, 0, .8], boot: [0, 0, 0, 0, 0]
  };
  function clamp(n, a, b) { return Math.max(a, Math.min(b, n)); }
  function ExpressiveFace(canvas, opts) {
    opts = Object.assign({}, opts, { poses: POSES });
    global.Face.call(this, canvas, opts);
    this.fixedBuffer = true;
    this.energy = opts.energy === undefined ? .65 : clamp(opts.energy, 0, 1);
    this.reducedMotion = opts.reducedMotion === undefined ? global.matchMedia('(prefers-reduced-motion: reduce)').matches : opts.reducedMotion;
    this.attention = null;
    this.accentFrom = ACCENTS[this.name];
    this.accentTo = this.accentFrom;
    this.age = 0;
  }
  ExpressiveFace.prototype = Object.create(global.Face.prototype);
  ExpressiveFace.prototype.constructor = ExpressiveFace;
  ExpressiveFace.prototype._accents = function () {
    var t = 1 - Math.pow(1 - this.t, 3);
    return this.accentTo.map(function (n, i) { return this.accentFrom[i] + (n - this.accentFrom[i]) * t; }, this);
  };
  ExpressiveFace.prototype.setEmote = function (name, hold) {
    if (!POSES[name]) return false;
    var accents = this._accents();
    global.Face.prototype.setEmote.call(this, name, hold);
    this.accentFrom = accents;
    this.accentTo = ACCENTS[name];
    this.age = 0;
    this.blinkT = -1;
    this.lookTarget = { x: 0, y: 0 };
    if (this.reducedMotion) this.t = 1;
    return true;
  };
  ExpressiveFace.prototype.setAttention = function (x, y) {
    this.attention = x === null ? null : { x: clamp(x, -1, 1) * 42, y: clamp(y, -1, 1) * 24 };
  };
  ExpressiveFace.prototype._step = function (dt) {
    var idle = this.idleOn;
    if (this.reducedMotion) this.idleOn = false;
    global.Face.prototype._step.call(this, dt);
    this.idleOn = idle;
    this.age += dt;
    // Only neutral drifts toward sleep. An explicit emotion remains legible.
    if (this.name !== 'neutral') this.sleepy = 0;
    this.blinkDur = this.name === 'sleepy' ? .65 : .16;
    if (this.attention && idle && !this.reducedMotion) {
      this.lookTarget.x = this.attention.x;
      this.lookTarget.y = this.attention.y;
      this.lookAt = 1;
      this.sinceEmote = 0;
      this.sleepy = 0;
    }
  };
  ExpressiveFace.prototype._modulate = function (pose, side) {
    if (this.reducedMotion || !this.idleOn) return Object.assign({}, pose);
    var p = global.Face.prototype._modulate.call(this, pose);
    var e = this.energy, t = this.age;
    p.x = pose.x + (p.x - pose.x) * (.25 + e * .75);
    p.y = pose.y + (p.y - pose.y) * (.25 + e * .75);
    // A short arrival gesture gives way to a quieter sustained expression.
    var arrival = Math.exp(-t * 2.4) * Math.sin(t * 13) * e;
    p.y -= arrival * 18;
    p.w *= 1 + arrival * .05;
    if (this.name === 'excited') {
      var bounce = Math.sin(t * 7.5 + side * .35) * e;
      p.y -= Math.abs(bounce) * 20;
      p.tilt += bounce * 4;
    } else if (this.name === 'happy' || this.name === 'love') {
      p.y += Math.sin(t * 2.8 + side * .45) * 7 * e;
      p.tilt += Math.sin(t * 2) * 3 * e;
    } else if (this.name === 'curious') {
      p.tilt += Math.sin(t * 1.7) * 5 * e;
      p.y += (side ? -1 : 1) * Math.sin(t * 1.7) * 5 * e;
    } else if (this.name === 'sleepy') {
      p.y += (1 + Math.sin(t * 1.1)) * 7 * e;
    } else if (this.name === 'surprised') {
      p.x -= this.look.x * .65;
      p.y -= this.look.y * .65;
    }
    return p;
  };
  ExpressiveFace.prototype._drawDetails = function (ctx, k, ox, oy) {
    var a = this._accents(), current = this._current();
    var motion = this.idleOn && !this.reducedMotion;
    var lx = motion ? this.look.x * (.25 + .75 * this.energy) : 0;
    var ly = motion ? this.look.y * (.25 + .75 * this.energy) : 0;
    var color = this.to.color || this.baseColor;
    ctx.save();
    ctx.translate(ox, oy); ctx.scale(k, k);
    ctx.strokeStyle = color; ctx.fillStyle = color;
    ctx.lineCap = 'round'; ctx.lineWidth = 7;
    // Tiny muzzle anchors the face without competing with the eyes.
    ctx.globalAlpha = this.name === 'boot' ? 0 : .8;
    ctx.beginPath();
    var my = 118 + ly * .45;
    if (a[1] > 1) {
      ctx.ellipse(lx * .5, my + 9, 17 + a[1] * .25, a[1], 0, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.moveTo(-28 + lx * .5, my);
      ctx.quadraticCurveTo(lx * .5, my + a[0], 28 + lx * .5, my);
      ctx.stroke();
    }
    ['l', 'r'].forEach(function (key, i) {
      var p = current[key], sign = i ? -1 : 1;
      var x = (i ? 172 : -172) + p.x + lx;
      var y = p.y - p.h / 2 - 31 + ly;
      ctx.globalAlpha = a[3] * .65;
      ctx.save(); ctx.translate(x, y); ctx.rotate(a[2] * sign);
      ctx.beginPath(); ctx.moveTo(-43, 0); ctx.quadraticCurveTo(0, -9, 43, 0); ctx.stroke(); ctx.restore();
      ctx.globalAlpha = a[4] * .5;
      for (var j = 0; j < 3; j++) {
        var cx = (i ? 276 : -296) + j * 10 + lx;
        ctx.beginPath(); ctx.moveTo(cx, 101 + ly); ctx.lineTo(cx - 4, 112 + ly); ctx.stroke();
      }
    });
    ctx.restore();
  };
  global.ExpressiveFace = ExpressiveFace;
})(window);
