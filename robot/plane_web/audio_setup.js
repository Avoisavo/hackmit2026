import {DeviceClient} from './device.js';

// Called directly from a demo click: unlock Web Audio before awaiting a request.
// STOP invalidates the attempt, including a microphone permission result that
// arrives later. A connected device is reused across demos, never re-paired.
export class AudioSetup {
  constructor({pair, devices, report = () => {}, createContext = () => new AudioContext(),
    getMedia = () => navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}}),
    makeClient = (role, key, report) => new DeviceClient(role, key, report)}) {
    Object.assign(this, {pair, devices, report, createContext, getMedia, makeClient});
    this.attempt = null;
    this.outputLabel = 'Mac system output';
  }
  prepare({microphone = true, check = () => {}} = {}) {
    if (this.attempt) return this.attempt.promise;
    const attempt = {cancelled:false,contexts:[],streams:[],clients:[]};
    this.attempt = attempt;
    const valid = () => {
      if (attempt.cancelled) throw new Error('Audio setup stopped. Select a demo when ready.');
      check();
    };
    const cancelled = new Promise((_, reject) => { attempt.reject = reject; });
    const prepareRole = async role => {
      const existing = this.devices[role];
      if (existing?.active && existing.ready) {
        await (existing.audioContext || existing.listener?.ctx)?.resume();
        valid(); return existing;
      }
      existing?.stop();
      this.report(role, role === 'speaker' ? 'Preparing speaker…' : 'Waiting for microphone access…');
      const context = this.createContext();
      attempt.contexts.push(context);
      const resume = context.resume();
      // Request the selected/default microphone from the original user click.
      let media;
      try { media = role === 'mic' ? this.getMedia() : null; }
      catch (error) { media = Promise.reject(error); }
      const capture = Promise.resolve(media).then(stream => {
        if (!stream) return null;
        attempt.streams.push(stream);
        if (attempt.cancelled) { stream.getTracks().forEach(track => track.stop()); valid(); }
        return stream;
      });
      return Promise.all([resume, capture]).then(async ([, stream]) => {
        valid();
        const {key} = await this.pair(role);
        valid();
        const client = this.makeClient(role, key, text => this.report(role, text));
        this.devices[role] = client;
        attempt.clients.push(client);
        this.report(role, role === 'mic' ? 'Connecting microphone to Deepgram…' : 'Connecting speaker…');
        await client.start(context, stream);
        valid();
        if (!client.active || !client.ready) throw new Error(`${role === 'mic' ? 'Microphone' : 'Speaker'} did not connect`);
        return client;
      });
    };
    try {
      valid();
      const tasks = [prepareRole('speaker')];
      if (microphone) tasks.push(prepareRole('mic'));
      const prepared = Promise.all(tasks).then(async () => {
        valid();
        if (typeof navigator !== 'undefined' && navigator.mediaDevices?.enumerateDevices) {
          const devices = await navigator.mediaDevices.enumerateDevices().catch(() => []);
          const output = devices.find(device => device.kind === 'audiooutput' && device.deviceId === 'default');
          if (output?.label) this.outputLabel = output.label;
        }
        valid();
      });
      attempt.promise = Promise.race([prepared, cancelled]).catch(error => {
        this.dispose(attempt);
        throw error;
      }).finally(() => { if (this.attempt === attempt) this.attempt = null; });
      return attempt.promise;
    } catch (error) {
      // A synchronous permissions/API error still owns any contexts already made.
      this.dispose(attempt);
      this.attempt = null;
      return Promise.reject(error);
    }
  }
  dispose(attempt) {
    attempt.cancelled = true;
    attempt.clients.forEach(client => client.stop());
    attempt.streams.forEach(stream => stream.getTracks().forEach(track => track.stop()));
    attempt.contexts.forEach(context => context.close().catch(() => {}));
  }
  cancel() {
    const attempt = this.attempt;
    if (!attempt) return;
    this.dispose(attempt);
    attempt.reject(new Error('Audio setup stopped. Select a demo when ready.'));
  }
  microphoneLabel() {
    return this.devices.mic?.listener?.stream?.getAudioTracks()[0]?.label || 'Selected microphone';
  }
}
