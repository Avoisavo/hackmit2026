"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ConversationProvider,
  useConversation,
  useConversationClientTool,
} from "@elevenlabs/react";
import { AGENT_FIRST_MESSAGE, AGENT_SYSTEM_PROMPT } from "@/lib/adhd-agent";

const PUBLIC_AGENT_ID = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID;

/**
 * "webrtc" gives better audio; "websocket" is more reliable on networks that
 * drop UDP media flows, and reports server close reasons instead of hiding them.
 */
const CONNECTION_TYPE =
  process.env.NEXT_PUBLIC_ELEVENLABS_CONNECTION === "websocket"
    ? "websocket"
    : "webrtc";

/**
 * Sending prompt overrides only works if the agent has "Enable overrides"
 * switched on for each field under Security in the ElevenLabs dashboard.
 * Otherwise the server closes the session with code 1008.
 */
const USE_OVERRIDES =
  process.env.NEXT_PUBLIC_ELEVENLABS_USE_OVERRIDES === "true";

type Line = { id: number; role: "user" | "agent"; text: string; at: string };

/**
 * Spoken words that end the session, so the conversation can be stopped
 * hands-free by a child who cannot reach or find the Stop button.
 */
const STOP_COMMAND = /\b(stop|goodbye|bye)\b/i;

/**
 * Asks for microphone permission, then immediately releases the device.
 *
 * The SDK opens its own capture stream, so holding this one would leave two
 * live captures of the same microphone and the second can fail to acquire it.
 */
async function requestMicPermission() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  stream.getTracks().forEach((track) => track.stop());
}

async function resolveSessionAuth() {
  const response = await fetch(`/api/elevenlabs/token?mode=${CONNECTION_TYPE}`, {
    cache: "no-store",
  });

  if (response.ok) {
    const data = (await response.json()) as { token?: string; signedUrl?: string };
    if (data.signedUrl) return { signedUrl: data.signedUrl } as const;
    if (data.token) return { conversationToken: data.token } as const;
  }

  if (PUBLIC_AGENT_ID) return { agentId: PUBLIC_AGENT_ID } as const;

  const { error } = (await response.json().catch(() => ({ error: null }))) as {
    error?: string;
  };
  throw new Error(error ?? "Could not get credentials from /api/elevenlabs/token");
}

function Tutor() {
  const [lines, setLines] = useState<Line[]>([]);
  const [stars, setStars] = useState(0);
  const [pop, setPop] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [heardYou, setHeardYou] = useState(false);
  const [peak, setPeak] = useState(0);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const nextId = useRef(0);
  const logRef = useRef<HTMLDivElement>(null);
  const endSessionRef = useRef<(() => void) | null>(null);

  const award = useCallback(() => {
    setStars((count) => count + 1);
    setPop(true);
    window.setTimeout(() => setPop(false), 600);
  }, []);

  const conversation = useConversation({
    onMessage: ({ message, role }) => {
      setLines((prev) => [
        ...prev,
        {
          id: nextId.current++,
          role,
          text: message,
          at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        },
      ]);
      if (role !== "user") return;

      if (STOP_COMMAND.test(message)) {
        setNotice("You said stop — see you next time! 👋");
        endSessionRef.current?.();
        return;
      }

      award();
    },
    onError: (message, context) => {
      console.error("[conversation error]", message, context);
      setError(message || "Connection error");
    },
    onDisconnect: (details) => {
      console.warn("[conversation disconnected]", details);
      if (details?.reason === "error") {
        setError(details.message || "The session ended unexpectedly");
      }
    },
  });

  useConversationClientTool("celebrate", () => {
    award();
    return "star awarded";
  });

  const {
    status,
    isSpeaking,
    startSession,
    endSession,
    getInputVolume,
    changeInputDevice,
    sendUserMessage,
  } = conversation;
  const connected = status === "connected";
  const busy = starting || status === "connecting";

  // Keep the latest endSession reachable from the onMessage callback above.
  useEffect(() => {
    endSessionRef.current = endSession;
  }, [endSession]);

  // Poll the captured input level so it is visible that the mic is live and
  // audio is actually reaching the SDK.
  useEffect(() => {
    if (!connected) return;
    let raf = 0;
    const tick = () => {
      try {
        const volume = getInputVolume();
        setMicLevel(volume);
        setPeak((prev) => (volume > prev ? volume : prev));
        if (volume > 0.02) setHeardYou(true);
      } catch {
        // Stream not ready yet; try again next frame.
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [connected, getInputVolume]);

  // Keep the newest line in view.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  const handleStart = async () => {
    setError(null);
    setNotice(null);
    setStarting(true);
    setMicLevel(0);
    setPeak(0);
    setHeardYou(false);
    try {
      await requestMicPermission();
      // Device labels are only exposed once permission has been granted.
      const found = (await navigator.mediaDevices.enumerateDevices()).filter(
        (d) => d.kind === "audioinput"
      );
      setDevices(found);
      const auth = await resolveSessionAuth();
      console.info("[session config]", {
        connectionType: CONNECTION_TYPE,
        sendingOverrides: USE_OVERRIDES,
        credential: Object.keys(auth)[0],
      });
      await startSession({
        ...auth,
        connectionType: CONNECTION_TYPE,
        ...(deviceId ? { inputDeviceId: deviceId } : {}),
        ...(USE_OVERRIDES
          ? {
              overrides: {
                agent: {
                  prompt: { prompt: AGENT_SYSTEM_PROMPT },
                  firstMessage: AGENT_FIRST_MESSAGE,
                  language: "en",
                },
              },
            }
          : {}),
      } as Parameters<typeof startSession>[0]);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      console.error("[start failed]", cause);
      setError(
        message.includes("Permission denied") || message.includes("NotAllowed")
          ? "Microphone blocked. Allow mic access in your browser and try again."
          : message
      );
    } finally {
      setStarting(false);
    }
  };

  const handleStop = () => {
    try {
      endSession();
    } catch (cause) {
      console.error("[stop failed]", cause);
    } finally {
      setStarting(false);
      setMicLevel(0);
    }
  };

  const handleSayHello = () => {
    if (!connected) return;
    sendUserMessage("Hi!");
  };

  const canStart = !connected && !busy;
  const canStop = connected || busy;

  const statusLabel = busy
    ? "Getting ready…"
    : !connected
      ? "Tap Start to begin"
      : isSpeaking
        ? "Buddy is talking…"
        : "Your turn — I'm listening!";

  const userTurns = lines.filter((l) => l.role === "user").length;

  return (
    <div className="flex w-full max-w-5xl flex-col items-center gap-10 lg:flex-row lg:items-start lg:justify-center">
      {/* Left: the thing the child interacts with */}
      <div className="flex w-full max-w-sm flex-col items-center gap-6">
        <div className="flex items-center gap-2 text-2xl" aria-live="polite">
          <span className="sr-only">{stars} stars earned</span>
          <span className={`transition-transform duration-200 ${pop ? "scale-125" : ""}`}>
            {"⭐".repeat(Math.min(stars, 10)) || "☆"}
          </span>
          {stars > 10 && <span className="text-lg font-bold text-amber-500">+{stars - 10}</span>}
        </div>

        <div className="flex items-center justify-center gap-5">
          <button
            type="button"
            onClick={handleStart}
            disabled={!canStart}
            aria-label="Start talking to Buddy"
            className={`relative flex h-40 w-40 flex-col items-center justify-center gap-1 rounded-full text-white shadow-xl transition-all duration-300 disabled:cursor-not-allowed disabled:opacity-40 ${
              connected
                ? isSpeaking
                  ? "bg-violet-500"
                  : "bg-emerald-500"
                : "bg-sky-500 enabled:hover:scale-105 enabled:hover:bg-sky-600"
            }`}
          >
            {connected && !isSpeaking && (
              <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400 opacity-40" />
            )}
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className="relative h-16 w-16">
              <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z" />
              <path d="M18 11a1 1 0 1 0-2 0 4 4 0 0 1-8 0 1 1 0 1 0-2 0 6 6 0 0 0 5 5.91V19H9a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2h-2v-2.09A6 6 0 0 0 18 11Z" />
            </svg>
            <span className="relative text-lg font-bold">
              {busy ? "Wait…" : connected ? "On" : "Start"}
            </span>
          </button>

          <button
            type="button"
            onClick={handleStop}
            disabled={!canStop}
            aria-label="Stop talking to Buddy"
            className="flex h-32 w-32 flex-col items-center justify-center gap-1 rounded-full bg-rose-500 text-white shadow-xl transition-all duration-300 enabled:hover:scale-105 enabled:hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className="h-12 w-12">
              <rect x="7" y="7" width="10" height="10" rx="2" />
            </svg>
            <span className="text-lg font-bold">Stop</span>
          </button>
        </div>

        <button
          type="button"
          onClick={handleSayHello}
          disabled={!connected}
          aria-label="Say hi to Buddy"
          className="rounded-full bg-amber-400 px-7 py-3 text-lg font-bold text-amber-950 shadow-md transition-all enabled:hover:scale-105 enabled:hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          👋 Say hi
        </button>

        <p className="text-center text-xl font-semibold text-slate-700 dark:text-slate-200">
          {statusLabel}
        </p>

        {notice && (
          <p className="w-full rounded-2xl bg-amber-50 px-4 py-3 text-center text-sm font-semibold text-amber-800 dark:bg-amber-950 dark:text-amber-200">
            {notice}
          </p>
        )}

        {error && (
          <p className="w-full rounded-2xl bg-rose-50 px-4 py-3 text-center text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">
            {error}
          </p>
        )}
      </div>

      {/* Right: the debug-friendly transcript */}
      <section className="flex w-full max-w-md flex-col rounded-3xl border border-slate-200 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/60">
        <header className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Transcript
          </h2>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
              connected
                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200"
                : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            }`}
          >
            {connected ? `connected · ${CONNECTION_TYPE}` : status}
          </span>
        </header>

        {/* Live mic level: proves audio is being captured and sent. */}
        <div className="mb-4">
          <div className="mb-1 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>Your mic</span>
            <span>
              {!connected
                ? "not connected"
                : heardYou
                  ? `heard you · ${userTurns} turn${userTurns === 1 ? "" : "s"} sent`
                  : "say something…"}
            </span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <div
              className="h-full rounded-full bg-emerald-500 transition-[width] duration-75"
              style={{
                width: connected
                  ? `${Math.min(100, Math.round(micLevel * 250))}%`
                  : "0%",
              }}
            />
          </div>
          <p className="mt-1 text-right text-[11px] tabular-nums text-slate-400">
            level {(micLevel * 100).toFixed(0)}% · peak {(peak * 100).toFixed(0)}%
          </p>

          {devices.length > 0 && (
            <label className="mt-2 flex flex-col gap-1 text-xs text-slate-500 dark:text-slate-400">
              Microphone
              <select
                value={deviceId}
                onChange={async (event) => {
                  const id = event.target.value;
                  setDeviceId(id);
                  setPeak(0);
                  if (connected && id) {
                    try {
                      await changeInputDevice({ inputDeviceId: id });
                    } catch (cause) {
                      console.error("[device switch failed]", cause);
                    }
                  }
                }}
                className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              >
                <option value="">System default</option>
                {devices.map((device) => (
                  <option key={device.deviceId} value={device.deviceId}>
                    {device.label || `Microphone ${device.deviceId.slice(0, 6)}`}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        <div
          ref={logRef}
          className="flex h-80 flex-col gap-3 overflow-y-auto pr-1"
          aria-live="polite"
        >
          {lines.length === 0 ? (
            <p className="m-auto text-center text-sm text-slate-400">
              Nothing yet. Tap the mic, then speak — your words appear here the
              moment ElevenLabs transcribes them.
            </p>
          ) : (
            lines.map((line) => (
              <div key={line.id} className="flex flex-col gap-1">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  {line.role === "user" ? "Child" : "Buddy"} · {line.at}
                </span>
                <div
                  className={`rounded-2xl px-4 py-2 text-base leading-snug ${
                    line.role === "user"
                      ? "bg-sky-100 text-sky-900 dark:bg-sky-900 dark:text-sky-100"
                      : "bg-violet-100 text-violet-900 dark:bg-violet-900 dark:text-violet-100"
                  }`}
                >
                  {line.text}
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

export default function VoiceTutor() {
  return (
    <ConversationProvider>
      <Tutor />
    </ConversationProvider>
  );
}
