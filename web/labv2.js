(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var params = new URLSearchParams(location.search);
  var media = matchMedia('(prefers-reduced-motion: reduce)');
  var motion = !media.matches && params.get('motion') !== '0';
  var face = new TwinkleFace($('twinkle'), { motion: motion });
  var names = TwinkleFace.NAMES;
  var descriptions = {
    'Ready': ['Glossy amber eyes, little glances, and an eager lift. Move near me; I’m paying attention.', 'Let’s play. I’m here.'],
    'Watching': ['The lights settle lower and gently widen toward the mat. Interested, never inspecting.', 'Following your discovery.'],
    'Encourage': ['Two gentle smiling curves and one small nod. There’s room to keep trying.', 'You’re on your way.'],
    'Thinking': ['One light perks up as the gaze shifts aside. A quiet pause to work things out.', 'Let’s find a way together.'],
    'Go': ['Both lights stretch tall and lift together. A brief eager bounce: let’s move.', 'An invitation to explore.'],
    'Celebrate': ['The widest beaming curves and one tiny sparkle. A little burst of shared joy.', 'We made a discovery!'],
    'Rest': ['Two soft, low resting curves. Slow breathing. Breaks feel welcome here.', 'It’s good to take a break.'],
    'Soft confused': ['The lights tip gently to one side, a little out of step. Twinkle needs a clearer look.', 'Could you help me see?']
  };
  var thumbs = [], sceneIndex = 0, playing = false, timer = null, overrideNext = null;
  var scenes = [
    { name:'Ready', event:'Session starts', line:'“Can you put three blue blocks on the mat?”', blocks:0, time:4200 },
    { name:'Watching', event:'The child places two blocks', line:'“I’m watching your blue blocks.”', blocks:2, time:3600 },
    { name:'Encourage', event:'Two of three — a moment to notice', line:'“You found two! How many more would make three?”', blocks:2, time:5000 },
    { name:'Thinking', event:'Twinkle offers a choice', line:'“A hint, a little more time, or a movement mission?”', blocks:2, time:5500 },
    { name:'Go', event:'The child chooses movement', line:'“Let’s go find one more blue block!”', blocks:2, time:4200 },
    { name:'Watching', event:'One more block joins the mat', line:'“Two blocks… and one more…”', blocks:3, time:3600 },
    { name:'Celebrate', event:'A discovery, together', line:'“Two plus one makes three! You kept trying.”', blocks:3, complete:true, time:5000 }
  ];
  function render() { if (motion && !document.hidden) face.start(); else face.draw(); }
  function stopStory(message) {
    clearTimeout(timer); timer = null; playing = false;
    $('play-story').innerHTML = 'Play story <span aria-hidden="true">▶</span>';
    if (message) $('story-status').textContent = message;
  }
  function chooseFace(name) {
    if (!face.setEmote(name)) return;
    $('display-equation').hidden = true;
    $('stage-name').textContent = String(names.indexOf(name)+1).padStart(2,'0') + ' — ' + name;
    $('feeling-name').textContent = name; $('feeling-description').textContent = descriptions[name][0];
    $('panel-link').href = '/labv2?panel=1&emote=' + encodeURIComponent(name) + (motion ? '' : '&motion=0');
    document.querySelectorAll('.face-card').forEach(function (button) {
      var active = button.dataset.name === name;
      button.classList.toggle('selected', active); button.setAttribute('aria-pressed', String(active));
    });
    render();
  }
  function markScene(index) {
    document.querySelectorAll('.step').forEach(function (button, i) {
      button.classList.toggle('active', i === index);
      if (i === index) button.setAttribute('aria-current','step'); else button.removeAttribute('aria-current');
    });
  }
  function mat(count, complete, hidden) {
    var el = $('block-mat'); el.replaceChildren();
    el.hidden = !!hidden; el.style.display = hidden ? 'none' : '';
    if (hidden) return;
    if (complete) {
      el.classList.add('complete-mat');
      var equation = document.createElement('div'); equation.className = 'equation'; equation.textContent = '2 + 1 = 3'; el.appendChild(equation);
      var group = document.createElement('div'); group.className = 'complete-blocks';
      for (var j=0;j<3;j++) { var b = document.createElement('span'); b.className = 'block'; group.appendChild(b); }
      el.appendChild(group); el.setAttribute('aria-label','Two blue blocks plus one blue block equals three blue blocks.');
    } else {
      el.classList.remove('complete-mat');
      for (var i=0;i<3;i++) { var block = document.createElement('span'); block.className = 'block' + (i < count ? '' : ' empty'); el.appendChild(block); }
      el.setAttribute('aria-label', count + ' blue blocks on the mat, ' + (3-count) + ' more to find.');
    }
  }
  function setScene(index) {
    sceneIndex = index; overrideNext = null;
    var s = scenes[index]; chooseFace(s.name); markScene(index);
    $('scene-event').textContent = s.event; $('scene-line').textContent = s.line;
    $('help-choices').hidden = index !== 3;
    $('next-scene').textContent = index === scenes.length-1 ? 'Play again ↺' : 'Next moment →';
    mat(s.blocks, s.complete, false);
    $('display-equation').hidden = !s.complete;
    if (s.complete) $('panel-link').href += '&result=1';
  }
  function special(name, event, line, next, count, help) {
    stopStory('Take your time. Continue whenever you’re ready.');
    sceneIndex = -1; overrideNext = next; markScene(-1); chooseFace(name);
    $('scene-event').textContent = event; $('scene-line').textContent = line;
    $('next-scene').textContent = 'Continue →'; $('help-choices').hidden = !help;
    mat(count || 0, false, count === null);
  }
  function schedule() {
    timer = setTimeout(function () {
      if (!playing) return;
      if (sceneIndex >= scenes.length-1) {
        stopStory('Discovery complete. Twinkle is ready for the next little adventure.');
        // Preserve the equation while the face returns to its welcoming baseline.
        chooseFace('Ready'); return;
      }
      setScene(sceneIndex+1); schedule();
    }, scenes[sceneIndex].time);
  }
  function keyHandler(ev) {
    if (/INPUT|TEXTAREA|SELECT/.test(ev.target.tagName) || ev.metaKey || ev.ctrlKey || ev.altKey) return;
    if (/^[1-8]$/.test(ev.key)) {
      if (params.get('panel') === '1') { face.setEmote(names[Number(ev.key)-1]); render(); }
      else previewFace(names[Number(ev.key)-1]);
    }
  }
  document.addEventListener('keydown', keyHandler);
  new ResizeObserver(function () { face.draw(); thumbs.forEach(function (f) { f.draw(); }); }).observe($('stage'));
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { face.stop(); if (playing) stopStory('Story paused while away. Use Next moment to continue.'); }
    else render();
  });
  function updateMotion(enabled) {
    var result = !$('display-equation').hidden;
    motion = enabled; $('motion').checked = motion;
    face.setMotion(motion); chooseFace(face.name);
    if (result) { $('display-equation').hidden = false; $('panel-link').href += '&result=1'; }
  }
  media.addEventListener('change', function (ev) { updateMotion(!ev.matches); });
  if (params.get('panel') === '1') {
    document.body.classList.add('panel-only');
    face.setEmote(names.indexOf(params.get('emote')) >= 0 ? params.get('emote') : 'Ready');
    $('display-equation').hidden = params.get('result') !== '1'; render();

    // ?link=0 skips the control channel, same convention as the original
    // face's kiosk page -- also the only way to screenshot this page
    // headlessly, since an open SSE stream never reaches network-idle.
    if (params.get('link') !== '0') {
      var holdTimer = null;
      var connectPanel = function () {
        var es = new EventSource('/events');
        es.onmessage = function (ev) {
          var d;
          try { d = JSON.parse(ev.data); } catch (e) { return; }
          if (!d || !d.name || names.indexOf(d.name) < 0) return;
          clearTimeout(holdTimer);
          face.setEmote(d.name);
          $('display-equation').hidden = !d.result;
          render();
          if (d.hold > 0) {
            holdTimer = setTimeout(function () {
              face.setEmote('Ready');
              $('display-equation').hidden = true;
              render();
            }, d.hold * 1000);
          }
        };
        es.onerror = function () {
          es.close();
          setTimeout(connectPanel, 2000);
        };
      };
      connectPanel();
    }
    return;
  }
  function previewFace(name) {
    special(name, 'Expression preview', descriptions[name][1], 0, null, false);
    $('story-status').textContent = 'Choose a numbered story moment to see this face in context.';
  }
  names.forEach(function (name, index) {
    var button = document.createElement('button'); button.type = 'button'; button.className = 'face-card'; button.dataset.name = name;
    button.setAttribute('aria-label', name + ' (' + (index+1) + ')');
    var canvas = document.createElement('canvas'); canvas.setAttribute('aria-hidden','true');
    var label = document.createElement('div'); label.className = 'card-caption';
    var title = document.createElement('strong'); title.textContent = name;
    var key = document.createElement('kbd'); key.textContent = String(index+1);
    label.append(title,key); var detail = document.createElement('p'); detail.textContent = descriptions[name][1];
    button.append(canvas,label,detail); $('face-pack').appendChild(button);
    var thumbnail = new TwinkleFace(canvas,{emote:name,motion:false}); thumbnail.draw(); thumbs.push(thumbnail);
    button.addEventListener('click', function () { previewFace(name); });
  });
  scenes.forEach(function (s,i) {
    var button = document.createElement('button'); button.className = 'step'; button.textContent = String(i+1).padStart(2,'0');
    button.setAttribute('aria-label','Scene '+(i+1)+': '+s.event);
    button.addEventListener('click',function () { stopStory('Explore at your own pace.'); setScene(i); });
    $('story-steps').appendChild(button);
  });
  $('play-story').addEventListener('click',function () {
    if (playing) { stopStory('Paused. Use Next moment to continue, or Play story to restart.'); return; }
    playing = true; setScene(0); this.innerHTML = 'Pause story <span aria-hidden="true">Ⅱ</span>';
    $('story-status').textContent = 'Auto demo · the child chooses movement. You can try any help choice.'; schedule();
  });
  $('next-scene').addEventListener('click', function () {
    stopStory('Explore at your own pace.');
    var next = overrideNext !== null ? overrideNext : (sceneIndex+1) % scenes.length;
    setScene(next);
  });
  document.querySelectorAll('[data-help]').forEach(function (button) {
    button.addEventListener('click', function () {
      var action = button.dataset.help;
      if (action === 'move') { stopStory('Movement mission chosen. Continue when the block is back.'); setScene(4); }
      if (action === 'hint') special('Encourage','A little hint','“Let’s count together. One, two… what comes next?”',5,2,false);
      if (action === 'time') special('Ready','Waiting patiently','“Of course. We have time. I’m right here.”',5,2,false);
    });
  });
  $('take-break').addEventListener('click',function () { special('Rest','A welcome break','“Let’s take a little rest. We can play again whenever you like.”',0,null,false); });
  $('ask-help').addEventListener('click',function () { special('Thinking','The child asks for help','“We can work it out together. What would you like to try?”',2,2,true); });
  $('blocked-view').addEventListener('click',function () { special('Soft confused','Twinkle can’t see the mat','“I can’t quite see the blocks. Could you help me look?”',1,null,false); });
  $('twinkle').addEventListener('pointermove',function (ev) {
    if (playing || !motion) return;
    var bounds = this.getBoundingClientRect();
    face.setAttention((ev.clientX-bounds.left)/bounds.width*2-1,(ev.clientY-bounds.top)/bounds.height*2-1);
  });
  $('twinkle').addEventListener('pointerleave',function () { face.setAttention(null); });
  $('motion').checked = motion;
  $('motion').addEventListener('change',function () { updateMotion(this.checked); });
  $('distance').addEventListener('change',function () { $('stage').classList.toggle('small',this.checked); });
  $('fullscreen').addEventListener('click',async function () {
    try { await $('stage').requestFullscreen(); }
    catch (_) { $('story-status').textContent = 'Fullscreen is unavailable here. Open display for a face-only view.'; }
  });
  // Observe each thumbnail as well: a breakpoint can change cards independently of the stage.
  var thumbObserver = new ResizeObserver(function () { thumbs.forEach(function (f) { f.draw(); }); });
  thumbObserver.observe($('face-pack'));
  setScene(0);
})();
