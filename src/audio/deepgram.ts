/**
 * Microphone -> Deepgram streaming STT, emitting ONLY complete child utterances.
 *
 * Every choice below was measured against the live API, not guessed:
 *
 * - MediaRecorder (WebM/Opus), NOT raw PCM. With a container you must OMIT
 *   encoding and sample_rate — Deepgram reads the container header. Declaring a
 *   sample rate the hardware did not actually honour yields empty transcripts.
 *
 * - smart_format and numerals MUST be false. With either on, a number-only
 *   answer is withheld for ~5 SECONDS while Deepgram waits to format it, and
 *   UtteranceEnd is withheld too. For a counting game that is fatal. We map
 *   "three" -> 3 ourselves in gameLogic.
 *
 * - endpointing=1000. Measured: 300-500ms splits "I think the answer is ...
 *   seven" into two turns; 1000ms absorbs a child's mid-answer hesitation and
 *   still finalizes ~1.5s after they stop.
 *
 * - Turn boundary is speech_final, never is_final. A single answer arrives as
 *   several is_final results, and silence emits is_final with empty text.
 *   UtteranceEnd is the backstop for noisy rooms, deduped by the empty-buffer
 *   check in flush().
 */

const DG_URL = "wss://api.deepgram.com/v1/listen";

const PARAMS: Record<string, string> = {
  model: "nova-3",
  language: "en-US",
  // Required by utterance_end_ms — without it the API returns HTTP 400.
  interim_results: "true",
  endpointing: "1000",
  utterance_end_ms: "1000",
  vad_events: "true",
  punctuate: "true",
  smart_format: "false",
  numerals: "false",
  // NO encoding, NO sample_rate: MediaRecorder sends a container.
};

// Words the game branches on. Keyterm prompting lifts recall on domain words,
// and small children need the help.
const KEYTERMS = [
  "yes", "no", "one", "two", "three", "four", "five",
  "blocks", "block", "more", "help", "I don't know",
];

export type UtteranceReason = "speech_final" | "utterance_end";

export interface SttHandlers {
  /** A complete child utterance. Never fires for partial speech. */
  onUtterance: (text: string, reason: UtteranceReason) => void;
  /** Live partial text, for display only. Never drive game logic from this. */
  onInterim?: (text: string) => void;
  onOpen?: () => void;
  onError?: (message: string) => void;
  onClose?: () => void;
}

interface DgResults {
  type: "Results";
  is_final: boolean;
  speech_final: boolean;
  channel?: { alternatives?: { transcript?: string }[] };
}
interface DgOther {
  type: "UtteranceEnd" | "SpeechStarted" | "Metadata" | "Error";
  code?: string;
  description?: string;
}
type DgMessage = DgResults | DgOther;

export class ChildListener {
  private ws: WebSocket | null = null;
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private analyser: AnalyserNode | null = null;
  private ctx: AudioContext | null = null;
  private segments: string[] = [];
  private paused = false;
  private stopped = false;
  private chunksSent = 0;

  constructor(private readonly handlers: SttHandlers) {}

  /** Chrome/Edge/Firefox get webm/opus. Safari below 18.4 has no WebM at all. */
  private static pickMimeType(): string {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/mp4",
    ];
    for (const c of candidates) {
      if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(c)) return c;
    }
    return "";
  }

  async start(): Promise<void> {
    this.stopped = false;
    this.paused = false;

    // Echo cancellation is the real defence against the robot hearing itself.
    // Pausing the track is belt-and-braces on top.
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });

    // A separate analyser purely for the on-screen level meter.
    this.ctx = new AudioContext();
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 256;
    this.ctx.createMediaStreamSource(this.stream).connect(this.analyser);

    const res = await fetch("/api/deepgram/token", { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error ?? `token route returned ${res.status}`);
    }
    const { access_token } = await res.json();

    const qs = new URLSearchParams(PARAMS);
    for (const k of KEYTERMS) qs.append("keyterm", k);

    // Browsers cannot set an Authorization header on a WebSocket, so the
    // credential rides in the subprotocol list. A /v1/auth/grant JWT needs the
    // "bearer" scheme specifically — ["token", jwt] returns 401.
    const ws = new WebSocket(`${DG_URL}?${qs.toString()}`, ["bearer", access_token]);
    this.ws = ws;

    ws.onopen = () => {
      console.log("[DG] socket open");
      this.handlers.onOpen?.();
      this.startRecorder();
    };
    ws.onmessage = (ev: MessageEvent) => {
      if (typeof ev.data !== "string") return;
      try {
        this.handle(JSON.parse(ev.data) as DgMessage);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onerror = () => {
      console.log("[DG] socket error");
      this.handlers.onError?.("Deepgram socket error");
    };
    ws.onclose = (ev) => {
      console.log(`[DG] socket closed code=${ev.code} reason=${ev.reason || "(none)"}`);
      this.stopRecorder();
      this.handlers.onClose?.();
    };
  }

  private startRecorder() {
    if (!this.stream) return;

    const mimeType = ChildListener.pickMimeType();
    console.log(`[DG] recording as ${mimeType || "(browser default)"}`);

    const rec = mimeType
      ? new MediaRecorder(this.stream, { mimeType })
      : new MediaRecorder(this.stream);

    rec.ondataavailable = (ev: BlobEvent) => {
      if (ev.data.size === 0 || this.ws?.readyState !== WebSocket.OPEN) return;
      // Keep sending even while paused: a disabled track emits silence, which
      // keeps the container valid and the socket alive. Dropping chunks
      // mid-stream would corrupt the WebM container.
      this.ws.send(ev.data);
      this.chunksSent += 1;
      if (this.chunksSent % 40 === 0) {
        console.log(`[DG] chunks sent: ${this.chunksSent}, level=${this.level.toFixed(3)}`);
      }
    };

    rec.start(250);
    this.recorder = rec;
  }

  private handle(msg: DgMessage) {
    // Switch on type FIRST: UtteranceEnd's `channel` is an array, not the
    // object Results carries, so touching it blind throws.
    switch (msg.type) {
      case "Results": {
        const text = (msg.channel?.alternatives?.[0]?.transcript ?? "").trim();

        if (!msg.is_final) {
          if (text) this.handlers.onInterim?.([...this.segments, text].join(" "));
          return;
        }

        if (text) {
          console.log(`[DG] is_final speech_final=${msg.speech_final} "${text}"`);
          this.segments.push(text);
        }
        if (msg.speech_final) this.flush("speech_final");
        return;
      }

      case "UtteranceEnd":
        this.flush("utterance_end");
        return;

      case "Error":
        console.log("[DG] error", msg.code, msg.description);
        this.handlers.onError?.(`${msg.code ?? "Deepgram"}: ${msg.description ?? ""}`);
        return;

      default:
        return;
    }
  }

  private flush(reason: UtteranceReason) {
    // The empty check is also what dedupes UtteranceEnd against the
    // speech_final that just fired for the same utterance.
    if (this.segments.length === 0) return;

    const text = this.segments.join(" ").replace(/\s+/g, " ").trim();
    this.segments = [];
    if (text && !this.stopped && !this.paused) {
      this.handlers.onUtterance(text, reason);
    }
  }

  /**
   * Robot is about to speak. Finalize FIRST so the child's trailing words are
   * emitted now — skipping this glues them onto the child's next answer.
   */
  pause() {
    if (this.paused) return;
    this.paused = true;
    this.send({ type: "Finalize" });
    this.stream?.getAudioTracks().forEach((t) => (t.enabled = false));
    console.log("[DG] paused (mic silent, socket alive)");
  }

  resume() {
    if (!this.paused) return;
    this.paused = false;
    this.segments = []; // drop anything that leaked in while the robot talked
    this.stream?.getAudioTracks().forEach((t) => (t.enabled = true));
    console.log("[DG] listening");
  }

  get level(): number {
    if (!this.analyser) return 0;
    const buf = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(1, 4 * Math.sqrt(sum / buf.length));
  }

  private send(obj: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  private stopRecorder() {
    try {
      if (this.recorder && this.recorder.state !== "inactive") this.recorder.stop();
    } catch {
      /* ignore */
    }
    this.recorder = null;
  }

  stop() {
    this.stopped = true;
    this.stopRecorder();
    this.send({ type: "CloseStream" });
    this.ws?.close();
    this.ws = null;
    this.ctx?.close().catch(() => null);
    this.ctx = null;
    this.analyser = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.segments = [];
  }
}
