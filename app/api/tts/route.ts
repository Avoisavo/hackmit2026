/**
 * Text -> speech, streamed straight through to the browser.
 *
 * A GET (not POST) so an <audio> element can point its src here and get native
 * progressive playback with no MediaSource code. Keys stay server-side.
 */

const MAX_TEXT = 800;

export async function GET(request: Request) {
  const url = new URL(request.url);
  const text = (url.searchParams.get("text") ?? "").slice(0, MAX_TEXT);
  const provider = url.searchParams.get("provider") ?? "elevenlabs";

  if (!text) return new Response("missing ?text", { status: 400 });

  const upstream =
    provider === "deepgram" ? await speakDeepgram(text) : await speakElevenLabs(text);

  if (!upstream.ok) {
    const detail = await upstream.text();
    return new Response(`TTS failed (${provider}): ${upstream.status} ${detail}`, {
      status: 502,
    });
  }

  // Pipe the upstream stream through untouched — never buffer the whole file.
  return new Response(upstream.body, {
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "audio/mpeg",
      "Cache-Control": "no-store",
    },
  });
}

async function speakElevenLabs(text: string) {
  const key = process.env.ELEVENLABS_API_KEY;
  // Legacy default voices expire and are not available on new accounts, so the
  // voice id is configurable rather than hardcoded.
  const voiceId = process.env.ELEVENLABS_VOICE_ID;

  if (!key || !voiceId) {
    return new Response("ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID missing from .env.local", {
      status: 500,
    });
  }

  return fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}/stream?output_format=mp3_22050_32`,
    {
      method: "POST",
      headers: { "xi-api-key": key, "Content-Type": "application/json" },
      // flash_v2_5 measured ~224ms to first byte. Omitting model_id silently
      // falls back to multilingual_v2, which is ~5x slower.
      body: JSON.stringify({ text, model_id: "eleven_flash_v2_5" }),
      cache: "no-store",
    },
  );
}

async function speakDeepgram(text: string) {
  const key = process.env.DEEPGRAM_API_KEY;
  if (!key) return new Response("DEEPGRAM_API_KEY missing", { status: 500 });

  return fetch("https://api.deepgram.com/v2/speak?model=flux-gemma-en", {
    method: "POST",
    headers: { Authorization: `Token ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    cache: "no-store",
  });
}
