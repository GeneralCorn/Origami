import { NextRequest } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();

  // Forward the request to FastAPI backend with a timeout
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);

  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeout);
    const message =
      err instanceof Error && err.name === "AbortError"
        ? "Backend request timed out"
        : "Backend request failed";
    return new Response(JSON.stringify({ error: message }), {
      status: 504,
      headers: { "Content-Type": "application/json" },
    });
  }
  clearTimeout(timeout);

  if (!response.ok) {
    return new Response(
      JSON.stringify({ error: "Backend request failed" }),
      { status: response.status, headers: { "Content-Type": "application/json" } }
    );
  }

  // Stream the response back to the client
  return new Response(response.body, {
    status: 200,
    headers: {
      "Content-Type": response.headers.get("Content-Type") || "text/plain",
      "Transfer-Encoding": "chunked",
    },
  });
}
