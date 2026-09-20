"use client";

import { useEffect, useRef, useState } from "react";
import { useDeepgramAgent, type AgentSessionConfig } from "@deepgram/react";
import { BUDDY_GREETING, BUDDY_KEYTERMS, BUDDY_PROMPT } from "@/lib/buddy-agent";

/**
 * Defined at module scope so its identity is stable across renders — a config
 * object rebuilt every render would churn the session.
 */
const CONFIG: AgentSessionConfig = {
  auth: {
    // Called at connect time and before every reconnect. The API key stays on
    // the server; only a 60-second bearer token reaches the browser.
    tokenFactory: async () => {
      const res = await fetch("/api/deepgram/token", { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `token route returned ${res.status}`);
      }
      const { access_token } = await res.json();
      return access_token;
    },
  },
  agent: {
    listen: {
      provider: {
        type: "deepgram",
        version: "v2",
        model: "flux-general-en",
        // How confident Flux must be that the child finished talking (0.5–0.9).
        // Lower = snappier, more likely to cut a child off mid-thought.
        eot_threshold: 0.7,
        // Hard stop: end the turn after this much silence regardless.
        eot_timeout_ms: 5000,
        keyterms: BUDDY_KEYTERMS,
      },
    },
    think: {
      provider: { type: "open_ai", model: "gpt-4o-mini", temperature: 0.7 },
      prompt: BUDDY_PROMPT,
    },
    speak: {
      provider: { type: "deepgram", version: "v2", model: "flux-gemma-en" },
    },
    greeting: BUDDY_GREETING,
  },
  // audio omitted on purpose — the SDK defaults are linear16 @ 16kHz in, 24kHz out.
};

export default function BuddyAgent() {
  const [error, setError] = useState<string | null>(null);

  const {
    state,
    mode,
    conversation,
    micMuted,
    start,
    stop,
    setMicMuted,
  } = useDeepgramAgent({
    config: CONFIG,
    onError: (m) => setError(m.description ?? "Agent error"),
    onSdkError: (e) => setError(e.message),
  });

  const isActive = state === "connected" || state === "connecting" || state === "reconnecting";

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Buddy</h1>
        <p className="text-sm text-black/60 dark:text-white/60">
          Deepgram Voice Agent smoke test. Press talk, then ask &ldquo;what is one plus one?&rdquo;
        </p>
      </header>

      <div className="flex items-center gap-3">
        <button
          onClick={() => {
            setError(null);
            if (isActive) {
              stop();
            } else {
              start().catch((e) => setError(e instanceof Error ? e.message : String(e)));
            }
          }}
          className={`rounded-full px-6 py-3 text-base font-medium text-white transition-colors ${
            isActive ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {isActive ? "Stop" : "Talk to Buddy"}
        </button>

        {isActive && (
          <button
            onClick={() => setMicMuted(!micMuted)}
            className="rounded-full border border-black/15 px-4 py-3 text-sm dark:border-white/20"
          >
            {micMuted ? "Unmute" : "Mute"}
          </button>
        )}

        <StatusPill state={state} mode={mode} />
      </div>

      {error && (
        <p className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          {error}
        </p>
      )}

      <Transcript entries={conversation} />
    </div>
  );
}

function StatusPill({ state, mode }: { state: string; mode: string }) {
  const label = state === "connected" ? mode : state;
  const tone =
    mode === "speaking"
      ? "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200"
      : mode === "thinking"
        ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200"
        : state === "connected"
          ? "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-200"
          : "bg-black/5 text-black/60 dark:bg-white/10 dark:text-white/60";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-medium capitalize ${tone}`}>
      {label}
    </span>
  );
}

function Transcript({
  entries,
}: {
  entries: { id: string; role: "user" | "assistant"; content: string; timestamp: number }[];
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length]);

  if (entries.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-black/15 px-4 py-10 text-center text-sm text-black/40 dark:border-white/15 dark:text-white/40">
        Nothing yet. Press talk and say something.
      </p>
    );
  }

  return (
    <div className="flex max-h-[28rem] flex-col gap-3 overflow-y-auto rounded-xl border border-black/10 p-4 dark:border-white/10">
      {entries.map((e) => (
        <div key={e.id} className={e.role === "user" ? "text-right" : "text-left"}>
          <span
            className={`inline-block max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
              e.role === "user"
                ? "bg-blue-600 text-white"
                : "bg-black/5 text-black dark:bg-white/10 dark:text-white"
            }`}
          >
            {e.content}
          </span>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
