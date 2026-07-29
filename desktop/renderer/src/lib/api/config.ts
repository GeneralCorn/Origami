declare global {
  interface Window {
    origami?: {
      backendUrl: string;
      authToken: string;
      platform: string;
      setTitleBarTheme: (color: string, symbolColor: string) => void;
    };
  }
}

// The main process discovers the sidecar's port at launch and hands both
// the URL and the per-launch token to the renderer through the preload
// bridge. The fallback keeps `vite dev` usable in a plain browser against
// a manually started backend.
export const API_URL = window.origami?.backendUrl || "http://127.0.0.1:8000";

const AUTH_TOKEN = window.origami?.authToken || "";

export function authHeaders(): Record<string, string> {
  return AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {};
}

/** Append the token as a query parameter, for URLs the browser loads itself. */
export function withToken(url: string): string {
  if (!AUTH_TOKEN) {
    return url;
  }
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}token=${encodeURIComponent(AUTH_TOKEN)}`;
}

export function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  return fetch(input, {
    ...init,
    headers: { ...authHeaders(), ...init.headers },
  });
}
