/** Where the game currently is. Exactly one of these is true at any moment. */
export type Phase =
  | "idle"
  | "robot_speaking"
  | "waiting_for_child"
  | "waiting_for_blocks"
  | "done";

/** What the robot goes back to waiting for once it finishes talking. */
export type Waiting = "child" | "blocks" | "none";

/** Which question the child is currently answering. Drives how we parse them. */
export type Question = "ready" | "how_many_more" | "what_comes_after" | null;

export interface Turn {
  id: string;
  role: "robot" | "child";
  text: string;
  at: number;
}

export interface GameState {
  phase: Phase;
  /** Phase to enter after the robot stops speaking. */
  resumeTo: Waiting;

  targetBlocks: number;
  detectedBlocks: number;
  currentRound: number;

  // Spec-required mirrors. Derived from `phase` in settle() so they cannot desync.
  waitingForChildAnswer: boolean;
  waitingForBlockAction: boolean;
  robotIsSpeaking: boolean;

  lastChildTranscript: string;
  conversationHistory: Turn[];

  question: Question;
  /** How many hints we have given on the current question. */
  hintCount: number;
  /** A camera reading that landed while the robot was still talking. */
  pendingBlocks: number | null;
}

export const TARGET_BLOCKS = 3;

export function initialState(target = TARGET_BLOCKS): GameState {
  return {
    phase: "idle",
    resumeTo: "none",
    targetBlocks: target,
    detectedBlocks: 0,
    currentRound: 1,
    waitingForChildAnswer: false,
    waitingForBlockAction: false,
    robotIsSpeaking: false,
    lastChildTranscript: "",
    conversationHistory: [],
    question: null,
    hintCount: 0,
    pendingBlocks: null,
  };
}

/** Numbers as words — the robot must speak "three", never "3". */
const WORDS = [
  "zero", "one", "two", "three", "four", "five",
  "six", "seven", "eight", "nine", "ten",
];

export function numberWord(n: number): string {
  return WORDS[n] ?? String(n);
}

export function plural(n: number, singular: string, pluralForm: string): string {
  return n === 1 ? singular : pluralForm;
}
