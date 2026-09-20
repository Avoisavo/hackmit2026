const API_ORIGIN = "https://api.elevenlabs.io";

/**
 * Issues the credential the browser needs to open a conversation.
 *
 * `?mode=webrtc` (default) mints a short-lived conversation token.
 * `?mode=websocket` returns a signed URL instead, which is the more forgiving
 * transport on restrictive networks where UDP media flows are dropped.
 *
 * Either way ELEVENLABS_API_KEY stays on the server.
 */
export async function GET(request: Request) {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  const agentId = process.env.ELEVENLABS_AGENT_ID;

  if (!agentId || !apiKey) {
    return Response.json(
      {
        error: `Missing ${!agentId ? "ELEVENLABS_AGENT_ID" : "ELEVENLABS_API_KEY"} in .env.local`,
      },
      { status: 500 }
    );
  }

  const mode =
    new URL(request.url).searchParams.get("mode") === "websocket"
      ? "websocket"
      : "webrtc";

  const endpoint =
    mode === "websocket"
      ? `${API_ORIGIN}/v1/convai/conversation/get-signed-url?agent_id=${encodeURIComponent(agentId)}`
      : `${API_ORIGIN}/v1/convai/conversation/token?agent_id=${encodeURIComponent(agentId)}`;

  const response = await fetch(endpoint, {
    headers: { "xi-api-key": apiKey },
    cache: "no-store",
  });

  if (!response.ok) {
    return Response.json(
      { error: `ElevenLabs returned ${response.status}: ${await response.text()}` },
      { status: response.status }
    );
  }

  const data = (await response.json()) as {
    token?: string;
    signed_url?: string;
  };

  if (mode === "websocket") {
    if (!data.signed_url) {
      return Response.json({ error: "No signed URL returned" }, { status: 502 });
    }
    return Response.json({ signedUrl: data.signed_url });
  }

  if (!data.token) {
    return Response.json({ error: "No conversation token returned" }, { status: 502 });
  }
  return Response.json({ token: data.token });
}
