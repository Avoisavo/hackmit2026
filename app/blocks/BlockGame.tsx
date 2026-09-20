"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChildListener } from "@/src/audio/deepgram";
import { RobotVoice, type TtsProvider } from "@/src/audio/tts";
import { VisionInput } from "@/src/vision/visionInput";
import { reduce, type GameEvent } from "@/src/game/gameLogic";
import { initialState, type GameState } from "@/src/game/gameState";

type LogLine = { id: number; tag: string; text: string };

export default function BlockGame() {
  const [state, setState] = useState<GameState>(() => initialState());
  const [lines, setLines] = useState<LogLine[]>([]);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [provider, setProvider] = useState<TtsProvider>("elevenlabs");

  // Refs so the async effect runner never reads stale state.
  const stateRef = useRef(state);
  const listenerRef = useRef<ChildListener | null>(null);
  const voiceRef = useRef<RobotVoice | null>(null);
  const visionRef = useRef<VisionInput | null>(null);
  const logId = useRef(0);
  const busy = useRef(false);

  const log = useCallback((tag: string, text: string) => {
    console.log(`[${tag}] ${text}`);
    logId.current += 1;
    const id = logId.current;
    setLines((l) => [...l.slice(-60), { id, tag, text }]);
  }, []);

  /**
   * The only way state changes. Applies the pure reducer, then runs the one
   * side effect it can produce: speaking. While the robot speaks the mic is
   * muted, so it can never hear itself, and SPEECH_END is dispatched only once
   * playback has actually finished.
   */
  const dispatch = useCallback(
    async (event: GameEvent) => {
      // A loop, not recursion: speaking a line always produces a SPEECH_END to
      // process next, and SPEECH_END can itself produce a line (a camera reading
      // that landed mid-sentence). The loop ends when the reducer has nothing
      // more to say — which is exactly the moment the robot's turn is over.
      let pending: GameEvent | null = event;

      while (pending) {
        const before = stateRef.current;
        const { state: next, say } = reduce(before, pending);

        stateRef.current = next;
        setState(next);

        if (next.phase !== before.phase) {
          const label =
            next.phase === "waiting_for_child" ? "waiting for child"
            : next.phase === "waiting_for_blocks" ? "waiting for blocks"
            : next.phase === "robot_speaking" ? "robot speaking"
            : next.phase;
          log("STATE", label);
        }

        if (!say) break;

        log("ROBOT", say);
        log("TTS", "speaking...");

        // Deaf while talking. Turn-taking enforced at the audio level too.
        listenerRef.current?.mute();
        setInterim("");

        await voiceRef.current?.speak(say);

        log("TTS", "finished");
        listenerRef.current?.unmute();

        pending = { type: "SPEECH_END" };
      }
    },
    [log],
  );

  // Serialize dispatches so two inputs arriving together cannot interleave.
  const send = useCallback(
    async (event: GameEvent) => {
      if (busy.current) return;
      busy.current = true;
      try {
        await dispatch(event);
      } finally {
        busy.current = false;
      }
    },
    [dispatch],
  );

  const stop = useCallback(() => {
    listenerRef.current?.stop();
    listenerRef.current = null;
    voiceRef.current?.cancel();
    voiceRef.current = null;
    visionRef.current?.stop();
    visionRef.current = null;
    setRunning(false);
    setInterim("");
    stateRef.current = initialState();
    setState(stateRef.current);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const voice = new RobotVoice(provider);
      voice.unlock(); // must happen inside this click
      voiceRef.current = voice;

      const listener = new ChildListener({
        onUtterance: (text) => {
          log("CHILD", text);
          setInterim("");
          void send({ type: "CHILD_SAID", text });
        },
        onInterim: setInterim,
        onError: setError,
      });
      await listener.start();
      listenerRef.current = listener;

      const vision = new VisionInput((count) => {
        log("GAME", `target: ${stateRef.current.targetBlocks}`);
        void send({ type: "BLOCKS_CHANGED", count });
      });
      vision.start();
      visionRef.current = vision;

      setRunning(true);
      await send({ type: "START" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      stop();
    }
  }, [log, provider, send, stop]);

  useEffect(() => stop, [stop]);

  const mock = (n: number) => {
    log("VISION", `mock detected blocks: ${n}`);
    void send({ type: "BLOCKS_CHANGED", count: n });
  };

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 font-sans">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Block counting game</h1>
        <p className="text-sm text-black/60 dark:text-white/60">
          Deepgram speech-to-text &rarr; game logic &rarr; {provider === "deepgram" ? "Deepgram Flux" : "ElevenLabs"} speech
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => (running ? stop() : void start())}
          className={`rounded-full px-6 py-3 font-medium text-white transition-colors ${
            running ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {running ? "Stop" : "Start game"}
        </button>

        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value as TtsProvider)}
          disabled={running}
          className="rounded-full border border-black/15 px-4 py-3 text-sm disabled:opacity-50 dark:border-white/20 dark:bg-transparent"
        >
          <option value="elevenlabs">Voice: ElevenLabs</option>
          <option value="deepgram">Voice: Deepgram Flux</option>
        </select>

        <Phase state={state} />
      </div>

      {error && (
        <p className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          {error}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Target" value={state.targetBlocks} />
        <Stat label="Detected" value={state.detectedBlocks} />
        <Stat label="Round" value={state.currentRound} />
        <Stat label="Speaking" value={state.robotIsSpeaking ? "yes" : "no"} />
      </div>

      <section className="rounded-xl border border-black/10 p-4 dark:border-white/10">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-black/50 dark:text-white/50">
          Mock camera &mdash; or run{" "}
          <code className="rounded bg-black/5 px-1 dark:bg-white/10">updateBlockCount(2)</code> in the console
        </p>
        <div className="flex flex-wrap gap-2">
          {[0, 1, 2, 3, 4].map((n) => (
            <button
              key={n}
              onClick={() => mock(n)}
              disabled={!running}
              className="rounded-lg border border-black/15 px-4 py-2 text-sm disabled:opacity-40 dark:border-white/20"
            >
              {n} blocks
            </button>
          ))}
        </div>
      </section>

      {interim && (
        <p className="text-sm italic text-black/40 dark:text-white/40">
          hearing: {interim}
        </p>
      )}

      <Log lines={lines} />
    </div>
  );
}

function Phase({ state }: { state: GameState }) {
  const label =
    state.phase === "waiting_for_child" ? "waiting for child"
    : state.phase === "waiting_for_blocks" ? "waiting for blocks"
    : state.phase === "robot_speaking" ? "robot speaking"
    : state.phase;

  const tone =
    state.phase === "robot_speaking"
      ? "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200"
      : state.phase === "waiting_for_child"
        ? "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-200"
        : state.phase === "waiting_for_blocks"
          ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200"
          : "bg-black/5 text-black/60 dark:bg-white/10 dark:text-white/60";

  return <span className={`rounded-full px-3 py-1 text-xs font-medium ${tone}`}>{label}</span>;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-black/10 px-4 py-3 dark:border-white/10">
      <div className="text-xs uppercase tracking-wide text-black/50 dark:text-white/50">{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

const TAG_TONE: Record<string, string> = {
  STATE: "text-blue-600 dark:text-blue-400",
  CHILD: "text-green-600 dark:text-green-400",
  ROBOT: "text-violet-600 dark:text-violet-400",
  VISION: "text-amber-600 dark:text-amber-400",
  GAME: "text-black/40 dark:text-white/40",
  TTS: "text-black/40 dark:text-white/40",
};

function Log({ lines }: { lines: LogLine[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [lines.length]);

  return (
    <div className="flex max-h-96 flex-col gap-1 overflow-y-auto rounded-xl border border-black/10 bg-black/[0.02] p-4 font-mono text-xs dark:border-white/10 dark:bg-white/[0.03]">
      {lines.length === 0 ? (
        <span className="text-black/40 dark:text-white/40">Press start.</span>
      ) : (
        lines.map((l) => (
          <div key={l.id}>
            <span className={TAG_TONE[l.tag] ?? ""}>[{l.tag}]</span>{" "}
            <span className="text-black/70 dark:text-white/70">{l.text}</span>
          </div>
        ))
      )}
      <div ref={endRef} />
    </div>
  );
}
