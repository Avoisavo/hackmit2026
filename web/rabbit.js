/* Warm white and blush rabbit screen-face. No images, packages, or network assets required.
 * Face owns timing/control; ExpressiveFace supplies living movement.
 * All geometry uses a 1000 x 600 design space. */
(function (global) {
  'use strict';
  var POSES = {
    neutral: { eye: { w: 258, h: 230, r: 90, lidLCurve: .08 }, dur: .45 },
    happy: { eye: { w: 275, h: 115, r: 57, lidLCurve: .55, y: 20 }, dur: .35 },
    excited: { eye: { w: 288, h: 262, r: 116, lidLCurve: .12, y: -10 }, dur: .28 },
    curious: { eye: {}, l: { w: 196, h: 145, r: 65, lidU: .24, tilt: -12, y: 22 }, r: { w: 275, h: 260, r: 108, tilt: -12, y: -12 }, dur: .5 },
    sad: { eye: { w: 245, h: 190, r: 80, lidU: .35, lidUTilt: -28, y: 30 }, ease: 'soft', dur: .7 },
    sleepy: { eye: { w: 255, h: 95, r: 46, lidU: .80, y: 35 }, ease: 'soft', dur: .9 },
    surprised: { eye: { w: 180, h: 278, r: 90, y: -8 }, dur: .22 },
    angry: { eye: { w: 258, h: 200, r: 70, lidU: .45, lidUTilt: 32 }, dur: .25 },
    love: { eye: { w: 282, h: 258, r: 90, shape: 1 }, dur: .5, color: '#ff7db9' },
    boot: { eye: { w: 176, h: 16, r: 8 }, ease: 'soft', dur: .5 }
  };
  // Left/right ear angle; ear droop; smile curve; mouth opening; blush; opacity.
  var FEATURES = {
    neutral: [0, 0, 0, 17, 0, .7, 1],
    happy: [.12, -.12, .05, 35, 20, 1, 1],
    excited: [.30, -.30, .18, 38, 60, 1, 1],
    curious: [.32, .15, .18, 8, 0, .5, 1],
    sad: [-.38, .38, .65, -32, 0, .15, 1],
    sleepy: [-.42, .42, .75, 4, 22, .15, 1],
    surprised: [.38, -.38, .28, 8, 64, .3, 1],
    angry: [-.28, .28, .40, -25, 0, .8, 1],
    love: [.12, -.12, .10, 24, 0, 1, 1],
    boot: [.24, -.24, .25, 7, 0, 0, .3]
  };
  function RabbitFace(canvas, opts) {
    opts = Object.assign({ color: '#39cfff', bg: '#000000' }, opts);
    global.ExpressiveFace.call(this, canvas, opts);
    this.poses = POSES;
    this.gradeFrom = 0; this.gradeTo = 0;
    this.featuresFrom = FEATURES.neutral.slice();
    this.featuresTo = FEATURES.neutral.slice();
    this.setEmote(opts.emote && POSES[opts.emote] ? opts.emote : 'neutral', 0);
    this.t = 1;
  }
  RabbitFace.prototype = Object.create(global.ExpressiveFace.prototype);
  RabbitFace.prototype.constructor = RabbitFace;
  RabbitFace.prototype._features = function () {
    var t = 1 - Math.pow(1 - this.t, 3);
    return this.featuresTo.map(function (v, i) { return this.featuresFrom[i] + (v - this.featuresFrom[i]) * t; }, this);
  };
  RabbitFace.prototype.setEmote = function (name, hold) {
    var aliases = { Ready: 'neutral', Watching: 'curious', Encourage: 'happy', Thinking: 'curious', Go: 'excited', Celebrate: 'love', Rest: 'sleepy', 'Soft confused': 'surprised' };
    if (Object.prototype.hasOwnProperty.call(aliases, name)) name = aliases[name];
    if (!POSES[name]) return false;
    var current = this._features();
    var grade = this._angerGrade();
    global.ExpressiveFace.prototype.setEmote.call(this, name, hold);
    this.gradeFrom = grade; this.gradeTo = name === 'angry' ? 1 : 0;
    this.featuresFrom = current;
    this.featuresTo = FEATURES[name];
    return true;
  };
  RabbitFace.prototype._angerGrade = function () {
    var t = 1 - Math.pow(1 - this.t, 3);
    return this.gradeFrom + (this.gradeTo - this.gradeFrom) * t;
  };
  RabbitFace.prototype._modulate = function (pose, side) {
    var p = global.ExpressiveFace.prototype._modulate.call(this, pose, side);
    if (!this.idleOn || this.reducedMotion) return p;
    if (this.name === 'excited') p.y -= Math.abs(Math.sin(this.age * 8)) * 24 * this.energy;
    if (this.name === 'angry') p.x += Math.sin(this.age * 15) * 3 * this.energy;
    if (this.name === 'love') {
      var pulse = 1 + Math.sin(this.age * 3.5) * .055 * this.energy;
      p.w *= pulse; p.h *= pulse;
    }
    return p;
  };
  function gradient(c, x, y, radius, stops) {
    var g = c.createRadialGradient(x, y, 0, x, y, radius);
    stops.forEach(function (s) { g.addColorStop(s[0], s[1]); });
    return g;
  }
  function shape(c, w, h, r, heart) {
    c.beginPath();
    if (heart) {
      c.moveTo(0, h * .47);
      c.bezierCurveTo(-w * .85, -h * .02, -w * .40, -h * .80, 0, -h * .26);
      c.bezierCurveTo(w * .40, -h * .80, w * .85, -h * .02, 0, h * .47);
      c.closePath();
    } else c.roundRect(-w / 2, -h / 2, w, h, Math.min(r, w / 2, h / 2));
  }
  function ellipse(c, x, y, rx, ry, angle, color) {
    c.fillStyle = color; c.beginPath(); c.ellipse(x, y, rx, ry, angle, 0, Math.PI * 2); c.fill();
  }
  // Elliptical area-light reflection: soft falloff instead of a flat white decal.
  function reflection(c, x, y, rx, ry, angle, strength) {
    c.save(); c.translate(x, y); c.rotate(angle); c.scale(rx, ry);
    c.fillStyle = gradient(c, 0, 0, 1, [[0, 'rgba(255,250,240,' + strength + ')'], [.35, 'rgba(237,252,255,' + strength * .8 + ')'], [.72, 'rgba(179,226,255,' + strength * .25 + ')'], [1, 'rgba(144,216,255,0)']]);
    c.beginPath(); c.arc(0, 0, 1, 0, Math.PI * 2); c.fill(); c.restore();
  }
  RabbitFace.prototype._eyeToOffscreen = function (idx, p, k, color) {
    var off = this._off[idx], px = Math.max(8, Math.ceil(440 * k));
    if (off.width !== px || off.height !== px) { off.width = px; off.height = px; }
    var c = off.getContext('2d');
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, px, px);
    c.setTransform(k, 0, 0, k, px / 2, px / 2); c.rotate(p.tilt * Math.PI / 180);
    if (p.shape >= .5) {
      // Emoji heart eyes: no eyeball or iris inside the heart silhouette.
      shape(c, p.w, p.h, p.r, true);
      c.fillStyle = gradient(c, -p.w * .18, -p.h * .24, p.w * .95,
        [[0, '#ff8b9e'], [.32, '#f45075'], [.68, '#d92858'], [1, '#9a214a']]);
      c.fill(); c.save(); c.clip();
      reflection(c, -p.w * .22, -p.h * .24, p.w * .17, p.h * .085, -.45, .65);
      c.restore(); shape(c, p.w, p.h, p.r, true); c.strokeStyle = '#c5325c'; c.lineWidth = 2; c.stroke();
      return off;
    }
    shape(c, p.w, p.h, p.r, p.shape >= .5);
    c.fillStyle = gradient(c, -p.w * .18, -p.h * .24, p.w * .85, [[0, '#fffdf7'], [.5, '#f2e9e3'], [.82, '#c8bdbe'], [1, '#8c8794']]);
    c.fill(); c.save(); c.clip();
    var iris = Math.min(p.w * .29, p.h * .39);
    var ix = idx ? -p.w * .08 : p.w * .08, iy = p.h * .035;
    ellipse(c, ix, iy, iris, iris * 1.06, 0, '#263247');
    ellipse(c, ix, iy, iris * .91, iris * .98, 0, gradient(c, ix - iris * .2, iy - iris * .3, iris * 1.6, [[0, '#83b9d8'], [.38, '#477ea7'], [.72, '#274665'], [1, '#142334']]));
    // Fine radial iris texture, kept inside the blue ring.
    c.strokeStyle = 'rgba(176,210,228,.27)'; c.lineWidth = 1;
    for (var j = 0; j < 48; j++) {
      var angle = j * Math.PI / 24;
      c.beginPath(); c.moveTo(ix + Math.cos(angle) * iris * .70, iy + Math.sin(angle) * iris * .70);
      c.lineTo(ix + Math.cos(angle) * iris * .88, iy + Math.sin(angle) * iris * .93); c.stroke();
    }
    ellipse(c, ix, iy, iris * .70, iris * .78, 0, gradient(c, ix, iy - iris * .4, iris * 1.7, [[0, '#202334'], [.5, '#0c1020'], [1, '#03050c']]));
    ellipse(c, ix - iris * .30, iy - iris * .40, Math.max(1, iris * .18), Math.max(1, iris * .21), .2, '#fff9ed');
    ellipse(c, ix + iris * .34, iy + iris * .26, Math.max(1, iris * .075), Math.max(1, iris * .08), 0, '#b2c6da');
    if (p.lidLCurve > .01) {
      c.fillStyle = gradient(c, 0, p.h * .42, p.w, [[0, '#fff7ef'], [.4, '#e9d9d3'], [1, '#ada2ac']]);
      c.beginPath(); c.moveTo(-p.w, p.h / 2);
      c.bezierCurveTo(-p.w * .5, p.h * (.5 - p.lidLCurve * 1.4), -p.w * .2, p.h * .38, 0, p.h * .38);
      c.bezierCurveTo(p.w * .2, p.h * .38, p.w * .5, p.h * (.5 - p.lidLCurve * 1.4), p.w, p.h / 2);
      c.lineTo(p.w, p.h); c.lineTo(-p.w, p.h); c.closePath(); c.fill();
    }
    c.restore();
    shape(c, p.w - 2, Math.max(1, p.h - 2), p.r, p.shape >= .5);
    c.lineWidth = 2; c.strokeStyle = '#b5a3a0'; c.stroke();
    if (p.lidU > .001) {
      c.save(); c.globalCompositeOperation = 'destination-out';
      c.translate(0, -p.h / 2 + p.lidU * p.h); c.rotate(p.lidUTilt * Math.PI / 180);
      c.fillRect(-400, -500, 800, 500); c.restore();
    }
    return off;
  };
  RabbitFace.prototype._ear = function (c, side, f, motion) {
    c.save(); c.translate(side * 248, -108);
    c.rotate(f[side < 0 ? 0 : 1] + motion * side);
    c.translate(0, Math.abs(motion) * -22);
    c.scale(side, 1);
    c.transform(1, 0, f[2] * .35, 1 - f[2] * .30, 0, 0);
    // Broad rounded fold: short inner return and a long outward-drooping tip.
    // A continuous curved underside avoids the old pointed chevron silhouette.
    c.beginPath(); c.moveTo(-46, -10);
    c.bezierCurveTo(-75, -30, -54, -105, -10, -127);
    c.bezierCurveTo(34, -151, 89, -112, 139, -67);
    c.bezierCurveTo(174, -36, 204, 5, 200, 34);
    c.bezierCurveTo(196, 78, 151, 83, 123, 58);
    c.bezierCurveTo(98, 36, 81, -1, 58, -39);
    c.bezierCurveTo(45, -61, 33, -77, 20, -77);
    c.bezierCurveTo(5, -71, 0, -27, -16, -14);
    c.bezierCurveTo(-25, -5, -36, -4, -46, -10); c.closePath();
    c.fillStyle = gradient(c, 25, -115, 225, [[0, '#fffaf1'], [.40, '#f4e9e3'], [.72, '#d4c7c6'], [1, '#a29aab']]);
    c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 4; c.fill();
    c.shadowBlur = 0; c.lineWidth = 2; c.strokeStyle = '#eadbd4'; c.stroke();
    c.save(); c.clip();
    c.beginPath(); c.moveTo(-32, -29);
    c.bezierCurveTo(-48, -55, -26, -112, 2, -109);
    c.bezierCurveTo(51, -110, 135, -33, 174, 26);
    c.bezierCurveTo(191, 57, 159, 57, 141, 36);
    c.bezierCurveTo(103, -10, 56, -98, 22, -94);
    c.bezierCurveTo(-6, -91, -9, -23, -32, -29); c.closePath();
    c.fillStyle = gradient(c, 54, -84, 173, [[0, '#d17f8d'], [.42, '#e7a0aa'], [.72, '#f5bdc1'], [1, '#cf8a9a']]); c.fill();
    // Sparse soft strands on the warm white outer rim.
    c.strokeStyle = 'rgba(255,252,245,.38)'; c.lineWidth = .7;
    for (var j = 0; j < 95; j++) {
      var x = -55 + (j * 37 % 250), y = -140 + (j * 53 % 210);
      c.beginPath(); c.moveTo(x, y); c.quadraticCurveTo(x + 3, y - 4, x + 7, y - 6); c.stroke();
    }
    c.restore();
    c.restore();
  };
  RabbitFace.prototype._furBackground = function (w, h) {
    if (this._fur && this._fur.width === w && this._fur.height === h) return this._fur;
    if (this._furFailed) return null;   // do not retry a build that already failed
    var canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h;
    var c = canvas.getContext('2d');
    if (!c) { this._furFailed = true; return null; }
    try {
      return this._paintFur(canvas, c, w, h);
    } catch (e) {
      // A small panel can refuse an offscreen canvas this large. The solid base
      // colour in _draw still shows, so the face stays readable.
      this._furFailed = true;
      return null;
    }
  };
  RabbitFace.prototype._paintFur = function (canvas, c, w, h) {
    // Cache the fur once per display size; animation does not redraw thousands of hairs.
    c.fillStyle = gradient(c, w * .38, h * .26, Math.max(w, h) * .85,
      [[0, '#fff9ed'], [.38, '#f2e7df'], [.72, '#d8cdd0'], [1, '#aaa8b8']]);
    c.fillRect(0, 0, w, h);
    var seed = 7319;
    function random() { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }
    // Capped for the robot panel's GPU. Each hair is a stroked curve, and the
    // old 28000 cap took long enough on the board that the screen sat blank.
    var density = Math.min(12000, Math.round(w * h / 35));
    var scale = Math.max(.5, Math.min(w / 1000, h / 600));
    c.lineCap = 'round';
    for (var i = 0; i < density; i++) {
      var x = random() * w, y = random() * h;
      var direction = Math.atan2(y - h * .32, (x - w * .5) * .75);
      var length = (3 + random() * 12) * scale;
      var dx = Math.cos(direction) * length, dy = Math.sin(direction) * length;
      c.strokeStyle = i % 3 ? 'rgba(255,253,246,.38)' : 'rgba(144,128,132,.085)';
      c.lineWidth = (.35 + random() * .6) * scale;
      c.beginPath(); c.moveTo(x, y);
      c.quadraticCurveTo(x + dx * .45 - dy * .12, y + dy * .45 + dx * .12, x + dx, y + dy); c.stroke();
    }
    this._fur = canvas; return canvas;
  };
  RabbitFace.prototype._draw = function () {
    var canvas = this.canvas, c = this.ctx;
    // Cap backing resolution for the small robot panel.
    var dpr = Math.min(2, global.devicePixelRatio || 1);
    var w = Math.max(1, Math.round((canvas.clientWidth || canvas.width) * dpr));
    var h = Math.max(1, Math.round((canvas.clientHeight || canvas.height) * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    // Reset every piece of canvas state before the frame, then wipe. A helper
    // that leaves globalAlpha or a composite mode behind makes the background
    // paint semi-transparent, and the previous face shows through the new one.
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalAlpha = 1;
    c.globalCompositeOperation = 'source-over';
    c.shadowBlur = 0; c.shadowColor = 'rgba(0,0,0,0)';
    if ('filter' in c) c.filter = 'none';
    c.clearRect(0, 0, w, h);
    // Paint a solid warm base FIRST. The fur is a cached offscreen canvas, and
    // building it can fail on a small panel's GPU. Without this base the panel
    // falls through to the dark page background and the rabbit looks black.
    c.fillStyle = '#f2e7df';
    c.fillRect(0, 0, w, h);
    var fur = this._furBackground(w, h);
    if (fur) c.drawImage(fur, 0, 0);
    var k = Math.min(w / 1000, h / 600), f = this._features();
    var living = this.idleOn && !this.reducedMotion;
    var tempo = { neutral: 1.7, happy: 3.2, excited: 7, curious: 2.2, sad: .9, sleepy: .65, surprised: 4, angry: 8, love: 2.4, boot: 1.2 }[this.name];
    var amplitude = { neutral: .09, happy: .17, excited: .24, curious: .20, sad: .08, sleepy: .07, surprised: .12, angry: .07, love: .15, boot: .05 }[this.name];
    var sway = living ? Math.sin(this.age * tempo) * amplitude * this.energy : 0;
    var rightSway = living ? Math.sin(this.age * tempo + .75) * amplitude * this.energy : 0;
    c.save(); c.translate(w / 2, h / 2); c.scale(k, k); c.globalAlpha = f[6];
    this._ear(c, -1, f, sway); this._ear(c, 1, f, rightSway);
    c.restore();
    var current = this._current(), color = this.to.color || this.baseColor;
    ['l', 'r'].forEach(function (side, i) {
      var p = this._modulate(current[side], i);
      var off = this._eyeToOffscreen(i, p, k, color);
      c.save(); c.shadowColor = 'rgba(0,0,0,.4)'; c.shadowBlur = 4 * k;
      c.drawImage(off, w / 2 + ((i ? 207 : -207) + p.x * .6) * k - off.width / 2,
        h / 2 + (27 + p.y * .5) * k - off.height / 2); c.restore();
    }, this);
    c.save(); c.translate(w / 2, h / 2); c.scale(k, k);
    c.lineCap = 'round'; c.lineJoin = 'round';
    c.globalAlpha = f[5] * .6;
    [-1, 1].forEach(function (side) {
      ellipse(c, side * 298, 158, 38, 18, 0, gradient(c, side * 298, 158, 40, [[0, '#d797a0'], [.45, 'rgba(219,160,166,.55)'], [1, 'rgba(219,160,166,0)']]));
    });
    c.globalAlpha = f[6]; c.shadowBlur = 0;
    var my = 185 + (living ? Math.sin(this.age * 2) * 2 * this.energy : 0);
    c.fillStyle = gradient(c, -5, my - 35, 31, [[0, '#f6b7bc'], [.55, '#e399a4'], [1, '#b66b7d']]);
    c.beginPath(); c.moveTo(-21, my - 36); c.bezierCurveTo(-13, my - 47, 13, my - 47, 21, my - 36);
    c.quadraticCurveTo(0, my - 15, -21, my - 36); c.fill();
    c.strokeStyle = '#b68c88'; c.lineWidth = 3; c.beginPath(); c.moveTo(0, my - 22); c.lineTo(0, my - 7); c.stroke();
    // One clean mouth silhouette; small incisors meet the upper lip.
    var opening = Math.min(34, f[4] * .52);
    var lipY = my - 7;
    var roundMouth = this.name === 'surprised' || this.name === 'sleepy';
    var width = roundMouth ? 17 : 34;
    c.shadowBlur = 0; c.lineWidth = 3; c.strokeStyle = '#a8797d';
    if (opening > 2) {
      c.beginPath(); c.moveTo(-width, lipY);
      c.bezierCurveTo(-width, lipY + opening * 1.35, width, lipY + opening * 1.35, width, lipY);
      c.quadraticCurveTo(0, lipY + 4, -width, lipY);
      c.fillStyle = '#77505a'; c.fill(); c.stroke();
      // Teeth are clipped inside open mouths, never crossing the lower lip.
      c.save(); c.clip();
    }
    var toothHeight = opening > 2 ? Math.min(13, opening * .65) : 15;
    var tooth = c.createLinearGradient(0, lipY, 0, lipY + toothHeight);
    tooth.addColorStop(0, '#e6d8c9'); tooth.addColorStop(.45, '#fffaf0'); tooth.addColorStop(1, '#f2e7d8');
    c.fillStyle = tooth;
    [-1, 1].forEach(function (side) {
      c.beginPath(); c.roundRect(side < 0 ? -12 : 1, lipY + 1, 11, toothHeight, [1, 1, 4, 4]); c.fill();
    });
    if (opening > 2) c.restore();
    // Quiet bunny muzzle, with a shallow frown for downcast expressions.
    c.strokeStyle = '#b48d87'; c.lineWidth = 3.5;
    c.beginPath();
    if (f[3] < 0) {
      c.moveTo(-31, lipY + 6); c.quadraticCurveTo(0, lipY - 8, 31, lipY + 6);
    } else if (opening <= 2) {
      c.moveTo(-35, lipY - 5);
      c.bezierCurveTo(-30, lipY + 10, -10, lipY + 10, 0, lipY);
      c.bezierCurveTo(10, lipY + 10, 30, lipY + 10, 35, lipY - 5);
    } else {
      c.moveTo(-width, lipY); c.quadraticCurveTo(0, lipY + 4, width, lipY);
    }
    c.stroke();
    c.restore();
    var anger = this._angerGrade();
    if (anger > .001) {
      c.save(); c.setTransform(1, 0, 0, 1, 0, 0);
      // Warm the white fur and pink ears while retaining eye and mouth contrast.
      c.globalCompositeOperation = 'multiply'; c.globalAlpha = anger * .48;
      c.fillStyle = '#ee7662'; c.fillRect(0, 0, w, h);
      c.globalCompositeOperation = 'source-over'; c.globalAlpha = anger;
      c.fillStyle = gradient(c, w * .5, h * .46, Math.max(w, h) * .65,
        [[0, 'rgba(167,38,35,0)'], [.45, 'rgba(167,38,35,.02)'], [1, 'rgba(126,28,37,.30)']]);
      c.fillRect(0, 0, w, h); c.restore();
    }
  };
  RabbitFace.EMOTES = POSES;
  global.RabbitFace = RabbitFace;
})(window);
