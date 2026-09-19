const API_ORIGIN = "https://api.elevenlabs.io";

/**
 * Mints a short-lived WebRTC conversation token for the configured agent.
 *
 * This keeps ELEVENLABS_API_KEY on the server. It is only required when the
 * agent has authentication enabled in the ElevenLabs dashboard; a public agent
 * connects straight from the browser with just the agent id.
 */
export async function GET() {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  const agentId = process.env.ELEVENLABS_AGENT_ID;

  if (!agentId) {
    return Response.json(
      { error: "ELEVENLABS_AGENT_ID is not set in .env.local" },
      { status: 500 }
    );
  }

  if (!apiKey) {
    return Response.json(
      { error: "ELEVENLABS_API_KEY is not set in .env.local" },
      { status: 500 }
    );
  }

  const response = await fetch(
    `${API_ORIGIN}/v1/convai/conversation/token?agent_id=${encodeURIComponent(agentId)}`,
    { headers: { "xi-api-key": apiKey }, cache: "no-store" }
  );

  if (!response.ok) {
    const detail = await response.text();
    return Response.json(
      { error: `ElevenLabs returned ${response.status}: ${detail}` },
      { status: response.status }
    );
  }

  const data = (await response.json()) as { token?: string };

  if (!data.token) {
    return Response.json(
      { error: "ElevenLabs did not return a conversation token" },
      { status: 502 }
    );
  }

  return Response.json({ token: data.token });
}
