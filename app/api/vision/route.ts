/**
 * What the computer-vision system talks to.
 *
 *   POST /api/vision  {"detected_blocks": 2}   <- the CV process calls this
 *   GET  /api/vision                           <- the page polls this
 *
 * State lives on globalThis, NOT in a module-level variable: Turbopack
 * re-evaluates modules on dev recompiles, which would silently reset the count
 * mid-session. globalThis survives that.
 */

interface VisionState {
  detected_blocks: number;
  seq: number;
  at: number;
}

const store = globalThis as typeof globalThis & { __vision?: VisionState };

function current(): VisionState {
  store.__vision ??= { detected_blocks: 0, seq: 0, at: Date.now() };
  return store.__vision;
}

export async function GET() {
  return Response.json(current(), { headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const count = body?.detected_blocks;

  if (typeof count !== "number" || !Number.isFinite(count) || count < 0) {
    return Response.json(
      { error: 'expected {"detected_blocks": <non-negative number>}' },
      { status: 400 },
    );
  }

  const next: VisionState = {
    detected_blocks: Math.round(count),
    seq: current().seq + 1,
    at: Date.now(),
  };
  store.__vision = next;

  console.log(`[VISION] detected blocks: ${next.detected_blocks} (seq ${next.seq})`);
  return Response.json(next, { headers: { "Cache-Control": "no-store" } });
}
