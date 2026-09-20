import { AgentMicrophone } from "@deepgram/agents";

/**
 * Microphone -> Deepgram streaming STT, emitting ONLY complete child utterances.
 *
 * Deepgram sends three kinds of "done" signal and picking the wrong one is what
 * makes a robot talk over a child:
 *   - is_final      a chunk is settled, but the child may still be talking
 *   - speech_final  endpointing decided the child stopped  <- the one we want
 *   - UtteranceEnd  a silence gap elapsed; the backup when speech_final never
 *                   fires (it can go missing in a noisy room)
 *
 * So: accumulate is_final chunks, flush on speech_final OR UtteranceEnd.
 */

const PARAMS = new URLSearchParams({
  model: "nova-3",
  encoding: "linear16",
  sample_rate: "16000",
  channels: "1",
  punctuate: "true",
  smart_format: "true",
  numerals: "true",
  // Interim results are required for utterance_end_ms to do anything at all.
  interim_results: "true",
  // Default endpointing is 10ms, which shreds a child's speech into confetti.
  endpointing: "400",
  utterance_end_ms: "1500",
  vad_events: "true",
});

// Words the game branches on. Keyterm prompting measurably lifts recall, and
// small children need the help.
const KEYTERMS = [
  "yes", "no", "one", "two", "three", "four", "five",
  "blocks", "block", "more", "help", "I don't know",
];

export interface SttHandlers {
  /** A complete child utterance. Never fires for partial speech. */
  onUtterance: (text: string) => void;
  /** Live partial text, for display only. Never drive game logic from this. */
  onInterim?: (text: string) => void;
  onOpen?: () => void;
  onError?: (message: string) => void;
  onClose?: () => void;
}

export class ChildListener {
  private ws: WebSocket | null = null;
  private mic: AgentMicrophone | null = null;
  private chunks: string[] = [];
  private framesSent = 0;
  private stopped = false;

  constructor(private readonly handlers: SttHandlers) {}

  async start(): Promise<void> {
    this.stopped = false;

    const res = await fetch("/api/deepgram/token", { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error ?? `token route returned ${res.status}`);
    }
    const { access_token } = await res.json();

    const qs = new URLSearchParams(PARAMS);
    for (const k of KEYTERMS) qs.append("keyterm", k);

    // Browsers cannot set an Authorization header on a WebSocket, so the
    // credential rides in the subprotocol list.
    const ws = new WebSocket(
      `wss://api.deepgram.com/v1/listen?${qs.toString()}`,
      ["bearer", access_token],
    );
    ws.binaryType = "arraybuffer";
    this.ws = ws;

    ws.addEventListener("open", () => {
      console.log("[DG] socket open");
      this.handlers.onOpen?.();
    });
    ws.addEventListener("error", () => {
      console.log("[DG] socket error");
      this.handlers.onError?.("Deepgram socket error");
    });
    ws.addEventListener("close", (ev) => {
      console.log(`[DG] socket closed code=${ev.code} reason=${ev.reason || "(none)"}`);
      this.handlers.onClose?.();
    });
    ws.addEventListener("message", (ev) => this.onMessage(ev));

    await new Promise<void>((resolve, reject) => {
      const ok = () => { ws.removeEventListener("error", bad); resolve(); };
      const bad = () => { ws.removeEventListener("open", ok); reject(new Error("could not open Deepgram socket")); };
      ws.addEventListener("open", ok, { once: true });
      ws.addEventListener("error", bad, { once: true });
    });

    // AgentMicrophone is a standalone getUserMedia + AudioWorklet that emits
    // Int16 PCM at 16kHz — exactly the linear16 feed configured above.
    this.mic = new AgentMicrophone((frame) => {
      if (this.ws?.readyState !== WebSocket.OPEN) return;
      this.ws.send(frame);
      this.framesSent += 1;
      if (this.framesSent % 100 === 0) {
        console.log(`[DG] frames sent: ${this.framesSent}, level=${this.level.toFixed(3)}`);
      }
    }, { sampleRate: 16000, echoCancellation: true, noiseSuppression: true });

    await this.mic.start();
    console.log("[DG] mic started, muted =", this.mic.muted);
  }

  private onMessage(ev: MessageEvent) {
    if (typeof ev.data !== "string") return;

    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }

    if (msg.type === "UtteranceEnd") {
      console.log("[DG] UtteranceEnd");
      this.flush();
      return;
    }

    if (msg.type === "SpeechStarted") {
      console.log("[DG] SpeechStarted");
      return;
    }

    if (msg.type !== "Results") return;

    const channel = msg.channel as { alternatives?: { transcript?: string }[] } | undefined;
    const text = channel?.alternatives?.[0]?.transcript?.trim() ?? "";

    if (text || msg.is_final) {
      console.log(`[DG] is_final=${msg.is_final} speech_final=${msg.speech_final} text="${text}"`);
    }

    if (!msg.is_final) {
      if (text) this.handlers.onInterim?.(text);
      return;
    }

    if (text) this.chunks.push(text);

    // speech_final means Deepgram's endpointing believes the child stopped.
    if (msg.speech_final) this.flush();
  }

  private flush() {
    const text = this.chunks.join(" ").trim();
    this.chunks = [];
    if (text && !this.stopped) this.handlers.onUtterance(text);
  }

  /** Stop sending audio. Used while the robot is talking so it never hears itself. */
  mute() { console.log("[DG] mic MUTED"); this.mic?.mute(); this.chunks = []; }
  unmute() { console.log("[DG] mic live"); this.mic?.unmute(); this.chunks = []; }
  get muted() { return this.mic?.muted ?? true; }
  get level() { return this.mic?.getInputVolume() ?? 0; }

  stop() {
    this.stopped = true;
    this.mic?.stop();
    this.mic = null;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "CloseStream" }));
      this.ws.close();
    }
    this.ws = null;
  }
}
