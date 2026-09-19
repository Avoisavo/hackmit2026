"use client";

import { useCallback, useRef, useState } from "react";
import {
  ConversationProvider,
  useConversation,
  useConversationClientTool,
} from "@elevenlabs/react";
import { AGENT_FIRST_MESSAGE, AGENT_SYSTEM_PROMPT } from "@/lib/adhd-agent";

const PUBLIC_AGENT_ID = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID;

type Line = { id: number; role: "user" | "agent"; text: string };

/** Resolves how to authenticate this session, preferring the server token route. */
async function resolveSessionAuth() {
  try {
    const response = await fetch("/api/elevenlabs/token", { cache: "no-store" });
    if (response.ok) {
      const { token } = (await response.json()) as { token: string };
      return { conversationToken: token } as const;
    }
  } catch {
    // Fall through to the public-agent path below.
  }

  if (PUBLIC_AGENT_ID) {
    return { agentId: PUBLIC_AGENT_ID } as const;
  }

  throw new Error(
    "No agent credentials found. Set ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID in .env.local, or NEXT_PUBLIC_ELEVENLABS_AGENT_ID for a public agent."
  );
}

function Tutor() {
  const [lines, setLines] = useState<Line[]>([]);
  const [stars, setStars] = useState(0);
  const [pop, setPop] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const nextId = useRef(0);

  const award = useCallback(() => {
    setStars((count) => count + 1);
    setPop(true);
    window.setTimeout(() => setPop(false), 600);
  }, []);

  const conversation = useConversation({
    onMessage: ({ message, role }) => {
      setLines((prev) => [...prev.slice(-7), { id: nextId.current++, role, text: message }]);
      // Every time the child finishes speaking they earn a star, so the reward
      // lands immediately and never depends on the agent choosing to give one.
      if (role === "user") award();
    },
    onError: (message) => setError(message),
    onDisconnect: () => setLines([]),
  });

  // Optional: if you add a client tool named "celebrate" to the agent in the
  // ElevenLabs dashboard, the agent can hand out bonus stars itself.
  useConversationClientTool("celebrate", () => {
    award();
    return "star awarded";
  });

  const { status, isSpeaking, startSession, endSession } = conversation;
  const connected = status === "connected";

  const handleStart = async () => {
    setError(null);
    setStarting(true);
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
      const auth = await resolveSessionAuth();
      startSession({
        ...auth,
        connectionType: "webrtc",
        // Only applied if "Enable overrides" is switched on for the agent.
        overrides: {
          agent: {
            prompt: { prompt: AGENT_SYSTEM_PROMPT },
            firstMessage: AGENT_FIRST_MESSAGE,
            language: "en",
          },
        },
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setStarting(false);
    }
  };

  const statusLabel = starting
    ? "Getting ready…"
    : status === "connecting"
      ? "Getting ready…"
      : !connected
        ? "Tap the mic to start"
        : isSpeaking
          ? "Buddy is talking…"
          : "Your turn — I'm listening!";

  return (
    <div className="flex w-full max-w-lg flex-col items-center gap-8">
      <div className="flex items-center gap-2 text-2xl" aria-live="polite">
        <span className="sr-only">{stars} stars earned</span>
        <span className={pop ? "scale-125 transition-transform duration-200" : "transition-transform duration-200"}>
          {"⭐".repeat(Math.min(stars, 10)) || "☆"}
        </span>
        {stars > 10 && <span className="text-lg font-bold text-amber-500">+{stars - 10}</span>}
      </div>

      <button
        type="button"
        onClick={connected ? () => endSession() : handleStart}
        disabled={starting || status === "connecting"}
        aria-label={connected ? "Stop talking to Buddy" : "Start talking to Buddy"}
        className={`relative flex h-44 w-44 items-center justify-center rounded-full text-white shadow-xl transition-all duration-300 disabled:opacity-60 ${
          connected
            ? isSpeaking
              ? "bg-violet-500"
              : "bg-emerald-500 scale-105"
            : "bg-sky-500 hover:bg-sky-600 hover:scale-105"
        }`}
      >
        {connected && !isSpeaking && (
          <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400 opacity-40" />
        )}
        <svg
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden="true"
          className="relative h-20 w-20"
        >
          <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z" />
          <path d="M18 11a1 1 0 1 0-2 0 4 4 0 0 1-8 0 1 1 0 1 0-2 0 6 6 0 0 0 5 5.91V19H9a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2h-2v-2.09A6 6 0 0 0 18 11Z" />
        </svg>
      </button>

      <p className="text-center text-xl font-semibold text-slate-700 dark:text-slate-200">
        {statusLabel}
      </p>

      {error && (
        <p className="w-full rounded-2xl bg-rose-50 px-4 py-3 text-center text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">
          {error}
        </p>
      )}

      <div className="flex w-full flex-col gap-3">
        {lines.map((line) => (
          <div
            key={line.id}
            className={`max-w-[85%] rounded-3xl px-5 py-3 text-lg leading-snug ${
              line.role === "user"
                ? "self-end bg-sky-100 text-sky-900 dark:bg-sky-900 dark:text-sky-100"
                : "self-start bg-violet-100 text-violet-900 dark:bg-violet-900 dark:text-violet-100"
            }`}
          >
            {line.text}
          </div>
        ))}
      </div>
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
