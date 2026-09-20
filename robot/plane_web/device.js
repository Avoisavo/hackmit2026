import {ChildListener} from './deepgram.js';

// Devices receive snapshots, not replayable commands. Only the current speech
// ID can be played/acknowledged; STOP invalidates it across every client.
export class DeviceClient {
  constructor(role, key, report = () => {}) {
    this.role = role; this.key = key; this.report = report;
    this.clientId = Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
    this.active = false; this.state = null; this.listener = null;
    this.source = null; this.playing = ''; this.handled = new Set();
    this.audioContext = null; this.timer = null; this.epoch = 0;
  }
  async request(path, payload, extra = '') {
    const response = await fetch(`/session/${path}?client_id=${encodeURIComponent(this.clientId)}${extra}`, {
      method: payload === undefined ? 'GET' : 'POST',
      headers: {'X-Device-Key': this.key, 'Content-Type': 'application/json'},
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: AbortSignal.timeout(path === 'audio' ? 30000 : 5000), cache: 'no-store'
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const error = new Error(body.detail || `Device request failed (${response.status})`);
      error.status = response.status; throw error;
    }
    return path === 'audio' ? response.arrayBuffer() : response.json();
  }
  async start(audioContext = null) {
    if (this.active) return;
    if (!this.key) throw new Error('Open a pairing link from the control plane.');
    this.active = true; this.epoch++;
    try {
      if (this.role === 'speaker') {
        this.audioContext = audioContext || new AudioContext();
        await this.audioContext.resume(); // called from a user click
      }
      await this.poll();
      if (!this.active) return;
      if (this.role === 'mic') {
        if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)
          throw new Error('Phone microphones require trusted HTTPS. Localhost also works on the server computer.');
        const epoch = this.epoch;
        this.listener = new ChildListener({
          onUtterance: text => {
            if (!this.active || !this.state?.listen) return;
            const state = this.state;
            this.request('transcript', {session_id: state.session_id, question_id: state.question_id,
              text, event_id: crypto.randomUUID()}).catch(error => {
                if (error.status !== 409) this.fail(error);
              });
            this.report(`Heard: ${text}`, this.state);
          },
          onError: message => this.fail(new Error(message)),
          onClose: () => { if (this.active) this.fail(new Error('Microphone connection closed')); },
        }, {key: this.key, clientId: this.clientId});
        await this.listener.start();
        if (!this.active || this.epoch !== epoch) { this.listener?.stop(); return; }
        if (!this.state?.listen) this.listener.pause();
      }
    } catch (error) { this.fail(error); throw error; }
  }
  async poll() {
    if (!this.active) return;
    const epoch = this.epoch;
    try {
      const state = await this.request('state');
      if (!this.active || epoch !== this.epoch) return;
      this.state = state;
      if (this.listener) state.listen ? this.listener.resume() : this.listener.pause();
      this.report(this.role === 'mic' ? (state.listen ? 'Listening for your answer…' : 'Microphone connected · waiting for the question.') : state.message, state);
      if (this.role === 'speaker') {
        if (this.playing && (!state.speech || state.speech.id !== this.playing)) this.cancelAudio();
        if (state.running && state.speech && !this.handled.has(state.speech.id)) {
          this.handled.add(state.speech.id);
          if (this.handled.size > 100) this.handled.delete(this.handled.values().next().value);
          void this.play(state);
        }
      }
    } catch (error) { if (this.active) this.fail(error); }
    finally { if (this.active) this.timer = setTimeout(() => this.poll(), 300); }
  }
  async play(state) {
    const id = state.speech.id;
    const epoch = this.epoch;
    this.playing = id;
    const current = () => this.active && this.epoch === epoch && this.playing === id && this.state?.speech?.id === id;
    const ack = status => this.request('speech', {session_id: state.session_id, speech_id: id, status});
    try {
      const bytes = await this.request('audio', undefined, '&speech_id=' + encodeURIComponent(id));
      if (!current()) return;
      const buffer = await this.audioContext.decodeAudioData(bytes);
      if (!current()) return;
      await ack('started');
      if (!current()) return;
      const source = this.audioContext.createBufferSource();
      source.buffer = buffer; source.connect(this.audioContext.destination);
      this.source = source;
      source.onended = () => {
        if (!current()) return;
        this.source = null; this.playing = '';
        ack('ended').catch(error => { if (error.status !== 409) this.fail(error); });
      };
      source.start();
    } catch (error) {
      if (current() && error.status !== 409) {
        await ack('error').catch(() => {});
        this.fail(error);
      }
    }
  }
  cancelAudio() {
    this.playing = '';
    if (this.source) {
      this.source.onended = null;
      try { this.source.stop(); } catch {}
      this.source = null;
    }
  }
  fail(error) { this.stop(); this.report(error.message); }
  stop() {
    if (!this.active) return;
    this.active = false; this.epoch++;
    clearTimeout(this.timer); this.timer = null;
    this.cancelAudio();
    this.listener?.stop(); this.listener = null;
    this.audioContext?.close().catch(() => {}); this.audioContext = null;
    fetch(`/session/fault?client_id=${encodeURIComponent(this.clientId)}`, {
      method: 'POST', headers: {'X-Device-Key': this.key}, keepalive: true,
    }).catch(() => {});
    this.report('Device disconnected. Join again when ready.');
  }
}

if (document.body.dataset.role) {
  const role = document.body.dataset.role;
  const key = new URLSearchParams(location.hash.slice(1)).get('key');
  history.replaceState(null, '', location.pathname);
  const message = document.querySelector('#deviceMessage');
  let face;
  if (role === 'face') {
    document.body.classList.add('face-device');
    face = new TwinkleFace(document.querySelector('#face'), {motion: !matchMedia('(prefers-reduced-motion: reduce)').matches});
    face.start();
  }
  const client = new DeviceClient(role, key, (text, state) => {
    message.textContent = text;
    if (face && state && face.name !== state.face) face.setEmote(state.face);
    document.querySelector('#deviceStop').disabled = !client.active;
    document.querySelector('#deviceStart').disabled = client.active;
  });
  document.querySelector('#deviceStart').onclick = () => client.start().catch(error => { message.textContent = error.message; });
  document.querySelector('#deviceStop').onclick = () => client.stop();
  window.addEventListener('pagehide', () => client.stop());
  document.addEventListener('visibilitychange', () => { if (document.hidden && role !== 'face') client.stop(); });
  if (role === 'face') client.start().catch(error => { message.textContent = error.message; });
}
