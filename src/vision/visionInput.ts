/**
 * Bridge for the camera / object-detection system.
 *
 * Two ways in, both landing on the same callback:
 *   1. The real CV process POSTs to /api/vision. The page polls for changes.
 *   2. A developer calls window.updateBlockCount(2) in the console, or clicks a
 *      mock button. No network at all.
 */

export type BlockCountHandler = (count: number) => void;

declare global {
  interface Window {
    updateBlockCount?: (count: number) => void;
  }
}

export class VisionInput {
  private timer: ReturnType<typeof setInterval> | null = null;
  private lastSeen: number | null = null;

  constructor(
    private readonly onCount: BlockCountHandler,
    private readonly pollMs = 400,
  ) {}

  start() {
    // Mock path — available immediately, works with zero backend.
    window.updateBlockCount = (count: number) => this.emit(count, "mock");

    // Real path — poll the endpoint the CV system writes to.
    this.timer = setInterval(async () => {
      try {
        const res = await fetch("/api/vision", { cache: "no-store" });
        if (!res.ok) return;
        const { detected_blocks, seq } = await res.json();
        if (typeof detected_blocks !== "number") return;
        // seq changes on every POST, so a re-post of the same count still counts
        // as a fresh reading. The reducer decides whether it is actionable.
        if (this.lastSeen === null) {
          // First poll is a baseline. A reading the CV system posted before the
          // page loaded is stale and must not fire as if it just happened.
          this.lastSeen = seq;
          return;
        }
        if (seq !== this.lastSeen) {
          this.lastSeen = seq;
          this.emit(detected_blocks, "camera");
        }
      } catch {
        // Dev-server restarts cause transient failures. Keep polling.
      }
    }, this.pollMs);
  }

  private emit(count: number, source: string) {
    console.log(`[VISION] detected blocks: ${count} (${source})`);
    this.onCount(count);
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    delete window.updateBlockCount;
  }
}
