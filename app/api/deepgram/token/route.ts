import { NextResponse } from "next/server";

/**
 * Mints a short-lived Deepgram bearer token so the browser can open the agent
 * WebSocket without ever seeing DEEPGRAM_API_KEY.
 *
 * The token only has to be valid at the WebSocket handshake — once the socket
 * is open it survives the token expiring, so there is no refresh machinery here.
 */
export async function POST() {
  const apiKey = process.env.DEEPGRAM_API_KEY;

  if (!apiKey) {
    return NextResponse.json(
      { error: "DEEPGRAM_API_KEY is missing. Add it to .env.local and restart `npm run dev`." },
      { status: 500 },
    );
  }

  const res = await fetch("https://api.deepgram.com/v1/auth/grant", {
    method: "POST",
    headers: {
      Authorization: `Token ${apiKey}`,
      "Content-Type": "application/json",
    },
    // Default TTL is 30s. 60 gives a little slack between click and handshake.
    body: JSON.stringify({ ttl_seconds: 60 }),
  });

  if (!res.ok) {
    const detail = await res.text();
    // The usual cause is an API key below Member role — /v1/auth/grant returns
    // FORBIDDEN "Insufficient permissions" for keys that cannot mint tokens.
    return NextResponse.json(
      { error: "Deepgram auth/grant failed", status: res.status, detail },
      { status: 502 },
    );
  }

  const { access_token, expires_in } = await res.json();

  return NextResponse.json(
    { access_token, expires_in },
    { headers: { "Cache-Control": "no-store" } },
  );
}
