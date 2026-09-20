import {
  type GameState,
  type Turn,
  type Waiting,
  initialState,
  numberWord,
  plural,
} from "./gameState";

export type GameEvent =
  | { type: "START" }
  | { type: "SPEECH_END" }
  | { type: "CHILD_SAID"; text: string }
  | { type: "BLOCKS_CHANGED"; count: number }
  | { type: "RESET" };

/**
 * The result of a transition. `say` is the single robot line to speak, or null.
 *
 * THE TURN-TAKING GUARANTEE lives here: `say` is only ever non-null in response
 * to an *input* event (START, CHILD_SAID, BLOCKS_CHANGED). A bare SPEECH_END
 * never produces speech, so the robot structurally cannot take two turns in a
 * row — it always has to be answering something.
 */
export interface Step {
  state: GameState;
  say: string | null;
}

let turnId = 0;
function turn(role: Turn["role"], text: string): Turn {
  turnId += 1;
  return { id: `${role}-${turnId}`, role, text, at: Date.now() };
}

/** Enter a waiting phase, keeping the spec's boolean mirrors in sync. */
function settle(s: GameState, waiting: Waiting): GameState {
  const phase =
    waiting === "child"
      ? "waiting_for_child"
      : waiting === "blocks"
        ? "waiting_for_blocks"
        : "done";

  return {
    ...s,
    phase,
    resumeTo: "none",
    robotIsSpeaking: false,
    waitingForChildAnswer: waiting === "child",
    waitingForBlockAction: waiting === "blocks",
  };
}

/** Start speaking a line, recording what to wait for once it finishes. */
function speak(
  s: GameState,
  text: string,
  resumeTo: Waiting,
  patch: Partial<GameState> = {},
): Step {
  return {
    state: {
      ...s,
      ...patch,
      phase: "robot_speaking",
      resumeTo,
      robotIsSpeaking: true,
      waitingForChildAnswer: false,
      waitingForBlockAction: false,
      conversationHistory: [...s.conversationHistory, turn("robot", text)],
    },
    say: text,
  };
}

// ---------------------------------------------------------------------------
// Understanding the child
// ---------------------------------------------------------------------------

const WORD_NUMBERS: Record<string, number> = {
  zero: 0, oh: 0, none: 0,
  one: 1, won: 1,
  two: 2, to: 2, too: 2,
  three: 3, tree: 3, free: 3,
  four: 4, for: 4, fore: 4,
  five: 5, six: 6, seven: 7, eight: 8, ate: 8, nine: 9, ten: 10,
};

/**
 * Pull a number out of a child's answer. Handles digits (Deepgram's numerals)
 * and number words, including the homophones a recognizer commonly returns for
 * a small child ("tree" for three, "to" for two).
 */
export function parseNumber(text: string): number | null {
  const digit = text.match(/\b(\d{1,2})\b/);
  if (digit) return Number(digit[1]);

  for (const word of text.toLowerCase().split(/[^a-z]+/)) {
    if (word in WORD_NUMBERS) return WORD_NUMBERS[word];
  }
  return null;
}

export function parseYesNo(text: string): boolean | null {
  const t = text.toLowerCase();
  if (/\b(yes|yeah|yep|yup|ok|okay|sure|please|course)\b/.test(t)) return true;
  if (/\b(no|nope|nah|don'?t)\b/.test(t)) return false;
  return null;
}

// ---------------------------------------------------------------------------
// Lines
// ---------------------------------------------------------------------------

const GREETING = "Hi! Do you wanna build some blocks with me today?";

function askForBlocks(target: number): string {
  return `Yay! Can you put ${numberWord(target)} blocks in front of me?`;
}

function reportCount(detected: number, target: number): string {
  const b = plural(detected, "block", "blocks");
  return `Hmm, I can see ${numberWord(detected)} ${b}. We need ${numberWord(target)}. How many more do we need?`;
}

function celebrate(target: number): string {
  return `Yay! Now we have ${numberWord(target)} blocks. You did it!`;
}

// ---------------------------------------------------------------------------
// The machine
// ---------------------------------------------------------------------------

export function reduce(s: GameState, e: GameEvent): Step {
  switch (e.type) {
    case "RESET":
      return { state: initialState(s.targetBlocks), say: null };

    case "START": {
      if (s.phase !== "idle") return { state: s, say: null };
      return speak(s, GREETING, "child", { question: "ready", hintCount: 0 });
    }

    case "SPEECH_END": {
      if (!s.robotIsSpeaking) return { state: s, say: null };

      const settled = settle(s, s.resumeTo);

      // A camera reading that arrived mid-sentence is applied now, not dropped.
      // This is a response to a real input, so it does not break turn-taking.
      if (settled.phase === "waiting_for_blocks" && s.pendingBlocks !== null) {
        return reduce(
          { ...settled, pendingBlocks: null },
          { type: "BLOCKS_CHANGED", count: s.pendingBlocks },
        );
      }

      return { state: { ...settled, pendingBlocks: null }, say: null };
    }

    case "CHILD_SAID": {
      // Ignored unless we are actually waiting on the child. This is what stops
      // the robot reacting to its own voice or to chatter during a block action.
      if (s.phase !== "waiting_for_child") return { state: s, say: null };

      const said = { ...s, lastChildTranscript: e.text,
        conversationHistory: [...s.conversationHistory, turn("child", e.text)] };

      if (s.question === "ready") {
        const yes = parseYesNo(e.text);
        if (yes === false) {
          return speak(said, "That's okay! Tell me when you want to play.", "child",
            { question: "ready" });
        }
        // Anything that is not a clear no moves the game forward.
        return speak(said, askForBlocks(s.targetBlocks), "blocks",
          { question: null, hintCount: 0 });
      }

      const missing = s.targetBlocks - s.detectedBlocks;

      if (s.question === "how_many_more") {
        const n = parseNumber(e.text);

        if (n === missing) {
          const b = plural(missing, "block", "blocks");
          return speak(said,
            `Yes! So we need ${numberWord(missing)} more ${b}. Can you add ${numberWord(missing)}?`,
            "blocks", { question: null, hintCount: 0 });
        }

        // Wrong or unheard: hint, never the answer.
        if (n === null) {
          return speak(said, "I didn't quite hear that. How many more do we need?",
            "child", { question: "how_many_more" });
        }
        return speak(said,
          `Almost! We have ${numberWord(s.detectedBlocks)}. What comes after ${numberWord(s.detectedBlocks)}?`,
          "child", { question: "what_comes_after", hintCount: s.hintCount + 1 });
      }

      if (s.question === "what_comes_after") {
        const n = parseNumber(e.text);

        if (n === s.detectedBlocks + 1) {
          const b = plural(missing, "block", "blocks");
          return speak(said,
            `Yes! So we need ${numberWord(missing)} more ${b}. Can you add ${numberWord(missing)}?`,
            "blocks", { question: null, hintCount: 0 });
        }

        return speak(said,
          `Not quite. Let's count together. ${numberWord(s.detectedBlocks)}, then what?`,
          "child", { question: "what_comes_after", hintCount: s.hintCount + 1 });
      }

      return { state: said, say: null };
    }

    case "BLOCKS_CHANGED": {
      // Never interrupt the robot. Hold the reading and apply it on SPEECH_END.
      if (s.robotIsSpeaking) {
        return { state: { ...s, pendingBlocks: e.count }, say: null };
      }

      // Not waiting on blocks: record the count but say nothing.
      if (s.phase !== "waiting_for_blocks") {
        return { state: { ...s, detectedBlocks: e.count }, say: null };
      }

      // Unchanged and still wrong: keep waiting. Never nag on a timer.
      if (e.count === s.detectedBlocks && e.count !== s.targetBlocks) {
        return { state: s, say: null };
      }

      const seen = { ...s, detectedBlocks: e.count };

      if (e.count === s.targetBlocks) {
        return speak(seen, celebrate(s.targetBlocks), "none",
          { question: null, currentRound: s.currentRound + 1 });
      }

      if (e.count > s.targetBlocks) {
        const extra = e.count - s.targetBlocks;
        const b = plural(extra, "block", "blocks");
        return speak(seen,
          `Ooh, that's ${numberWord(e.count)}. That's too many! Can you take away ${numberWord(extra)} ${b}?`,
          "blocks", { question: null, hintCount: 0 });
      }

      return speak(seen, reportCount(e.count, s.targetBlocks), "child",
        { question: "how_many_more", hintCount: 0 });
    }
  }
}
